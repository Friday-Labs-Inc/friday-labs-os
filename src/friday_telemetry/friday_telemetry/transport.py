"""Transport for the Command Center boundary: an MQTT-class pub/sub link.

`MqttTransport` is the real link (paho-mqtt). Production runs MQTT 5 over TLS 1.3
with mutual-TLS client certs (pass `tls=`); the command-authority security is
app-layer (Ed25519/CBOR, see protocol.py) and independent of the MQTT version.
`LoopbackTransport` is an in-process, broker-less stand-in for unit tests.
"""

from __future__ import annotations

import abc

import paho.mqtt.client as mqtt


class Transport(abc.ABC):
    """Minimal pub/sub. Callbacks receive (topic: str, payload: bytes)."""

    @abc.abstractmethod
    def connect(self) -> None: ...

    @abc.abstractmethod
    def publish(self, topic: str, payload: bytes) -> None: ...

    @abc.abstractmethod
    def subscribe(self, topic_filter: str, callback) -> None: ...

    @abc.abstractmethod
    def disconnect(self) -> None: ...


def _new_client(client_id: str):
    # Works across paho 1.6 (Ubuntu 24.04) and 2.x.
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


class MqttTransport(Transport):
    def __init__(self, host="127.0.0.1", port=1883, client_id="", tls=None):
        self._host = host
        self._port = port
        self._subs = {}                      # topic_filter -> callback
        self._client = _new_client(client_id)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        if tls:                              # production mTLS: {ca_certs, certfile, keyfile}
            self._client.tls_set(**tls)

    def _on_connect(self, client, userdata, flags, rc, *args):
        for topic_filter in self._subs:
            client.subscribe(topic_filter, qos=1)

    def _on_message(self, client, userdata, msg):
        for topic_filter, callback in list(self._subs.items()):
            if mqtt.topic_matches_sub(topic_filter, msg.topic):
                callback(msg.topic, msg.payload)

    def connect(self) -> None:
        self._client.connect(self._host, self._port, keepalive=30)
        self._client.loop_start()

    def publish(self, topic: str, payload: bytes) -> None:
        self._client.publish(topic, payload, qos=1)

    def subscribe(self, topic_filter: str, callback) -> None:
        self._subs[topic_filter] = callback
        try:
            self._client.subscribe(topic_filter, qos=1)
        except Exception:                    # not connected yet -> handled on_connect
            pass

    def disconnect(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass


class LoopbackTransport(Transport):
    """In-process transport for tests — no broker, no network."""

    def __init__(self):
        self._subs = []                      # list of (topic_filter, callback)

    def connect(self) -> None:
        pass

    def publish(self, topic: str, payload: bytes) -> None:
        for topic_filter, callback in list(self._subs):
            if mqtt.topic_matches_sub(topic_filter, topic):
                callback(topic, payload)

    def subscribe(self, topic_filter: str, callback) -> None:
        self._subs.append((topic_filter, callback))

    def disconnect(self) -> None:
        pass
