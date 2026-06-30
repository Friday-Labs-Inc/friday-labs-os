"""Durable monotonic nonce floor — replay protection that survives a restart.

The round-1 review (and the post-Phase-4 re-review) flagged that an in-memory
nonce floor resets to zero on a reboot, silently re-opening a replay window. This
store persists the per-source floor to an fsync'd file, written atomically before
the caller ACKs the command. Pure Python (no ROS) so it's shared by the Telemetry
CommandValidator and the Locomotion agent, and unit-tested directly.

`path=None` -> in-memory only (tests / no-persist callers).
"""

import json
import os
import threading


class NonceStore:
    def __init__(self, path: str | None = None):
        self._path = path or None
        # Guards the read-modify-write in commit(): the Telemetry CommandValidator
        # runs on the paho network thread while the issuing path runs on the ROS
        # executor, and commit() replaces the whole dict — without the lock a
        # concurrent commit to a different source would silently lose an update.
        self._lock = threading.Lock()
        self._nonces = self._load()

    def _load(self) -> dict:
        if not self._path:
            return {}
        try:
            with open(self._path) as f:
                return {str(k): int(v) for k, v in json.load(f).items()}
        except (OSError, ValueError):
            return {}

    def last(self, source: str):
        """Highest nonce accepted for `source`, or None if never seen."""
        with self._lock:
            return self._nonces.get(source)

    def commit(self, source: str, nonce: int) -> None:
        """Record `nonce` as the new floor for `source` and persist durably."""
        with self._lock:
            self._nonces = {**self._nonces, source: int(nonce)}   # immutable update
            if self._path:
                self._flush()

    def _flush(self) -> None:
        # Atomic + durable: write a temp file, fsync, rename over the target.
        tmp = self._path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self._nonces, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
