"""Mock Command Center — the operator side of the boundary, for demos + tests.

Two subcommands:

  provision   generate an operator Ed25519 keypair; write the private key and a
              rover allowlist (operators.json: {operator_id: public_key_hex}).
  send        build a signed motion command and publish it over MQTT, then print
              the rover's ACK. --mode injects the acceptance-test attacks.

Modes: valid | forged (tamper payload after signing) | expired (past expiry) |
replay (reuse a nonce). Wrong-rover is just --rover with a different id.
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from friday_telemetry import protocol
from friday_telemetry.transport import MqttTransport


def _raw_private(path: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(open(path).read().strip()))


def cmd_provision(args) -> int:
    priv = Ed25519PrivateKey.generate()
    priv_hex = priv.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption()).hex()
    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    open(args.key_file, 'w').write(priv_hex)
    json.dump({args.operator_id: pub_hex}, open(args.allowlist, 'w'))
    print(f'provisioned operator {args.operator_id}')
    print(f'  private key -> {args.key_file}')
    print(f'  allowlist   -> {args.allowlist}')
    return 0


def cmd_send(args) -> int:
    priv = _raw_private(args.key_file)
    now = time.time()
    expires_at = now - 5.0 if args.mode == 'expired' else now + protocol.DEFAULT_EXPIRY_S
    payload = {
        'class': 'motion',
        'type': 1,  # TYPE_VELOCITY
        'linear_velocity': args.linear,
        'angular_velocity': args.angular,
    }
    envelope = protocol.build_envelope(
        rover_id=args.rover, sender_id=args.operator_id, msg_id=args.nonce,
        nonce=args.nonce, issued_at=now, expires_at=expires_at,
        payload=payload, private_key=priv)
    if args.mode == 'forged':
        # Tamper the payload AFTER signing -> signature no longer matches.
        envelope['payload'] = {**payload, 'linear_velocity': args.linear + 9.0}

    transport = MqttTransport(host=args.host, port=args.port,
                              client_id=f'cc-{args.operator_id}-{args.nonce}')
    acks = []

    def _read_ack(raw):
        # ACKs are plain CBOR, or a signed envelope when the rover holds a key;
        # unwrap the envelope to its payload so either form prints cleanly.
        msg = cbor2.loads(raw)
        return msg.get('payload', msg) if isinstance(msg, dict) else msg

    transport.subscribe(f'mark1/{args.rover}/ack/#', lambda t, p: acks.append(_read_ack(p)))
    transport.connect()
    time.sleep(0.3)
    transport.publish(f'mark1/{args.rover}/cmd/motion', protocol.encode(envelope))
    print(f'sent mode={args.mode} rover={args.rover} operator={args.operator_id} '
          f'nonce={args.nonce} v={args.linear} w={args.angular}')
    deadline = time.time() + 2.0
    while not acks and time.time() < deadline:
        time.sleep(0.05)
    transport.disconnect()
    if acks:
        print(f'ACK: {acks[0]}')
    else:
        print('ACK: (none received)')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='mock_command_center')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('provision')
    p.add_argument('--operator-id', default='OP-001')
    p.add_argument('--key-file', required=True)
    p.add_argument('--allowlist', required=True)
    p.set_defaults(func=cmd_provision)

    s = sub.add_parser('send')
    s.add_argument('--rover', default='MARK1-001')
    s.add_argument('--host', default='127.0.0.1')
    s.add_argument('--port', type=int, default=1883)
    s.add_argument('--operator-id', default='OP-001')
    s.add_argument('--key-file', required=True)
    s.add_argument('--nonce', type=int, required=True)
    s.add_argument('--linear', type=float, default=0.5)
    s.add_argument('--angular', type=float, default=0.3)
    s.add_argument('--mode', choices=['valid', 'forged', 'expired', 'replay'], default='valid')
    s.set_defaults(func=cmd_send)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
