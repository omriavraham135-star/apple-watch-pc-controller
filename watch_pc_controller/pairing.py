"""Pairing: a device proves once that it was let in, then carries a token.

The PC shows a six-digit code; a device that types it in within two minutes
gets a long random token. Only a hash of each token is kept on disk, so the
file is useless to whoever reads it.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional

CODE_TTL_SECONDS = 120
MAX_CODE_ATTEMPTS = 5
MAX_NAME_LENGTH = 40


class PairingError(Exception):
    """The code was missing, expired, wrong or already used."""


@dataclass
class Device:
    id: str
    name: str
    token_hash: str
    paired_at: float
    last_seen: float


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PairingStore:
    def __init__(self, path: str, clock: Callable[[], float] = time.time):
        self._path = path
        self._clock = clock
        self._lock = threading.Lock()
        self._code: Optional[str] = None
        self._code_expires = 0.0
        self._attempts = 0
        self._devices: dict[str, Device] = self._load()

    # ------------------------------------------------------------- codes

    def create_code(self) -> str:
        with self._lock:
            self._code = f"{secrets.randbelow(10 ** 6):06d}"
            self._code_expires = self._clock() + CODE_TTL_SECONDS
            self._attempts = 0
            return self._code

    def redeem(self, code: str, device_name: str) -> str:
        with self._lock:
            now = self._clock()
            if self._code is None or now > self._code_expires:
                self._code = None
                raise PairingError("no active code")
            self._attempts += 1
            if not hmac.compare_digest((code or "").strip(), self._code):
                if self._attempts >= MAX_CODE_ATTEMPTS:
                    self._code = None          # too many guesses: this code is burned
                raise PairingError("wrong code")
            self._code = None                   # a code pairs exactly one device
            token = secrets.token_urlsafe(32)
            name = (device_name or "device").strip()[:MAX_NAME_LENGTH] or "device"
            device = Device(
                id=secrets.token_hex(4),
                name=name,
                token_hash=_hash(token),
                paired_at=now,
                last_seen=now,
            )
            self._devices[device.id] = device
            self._save()
            return token

    # ------------------------------------------------------------- tokens

    def verify(self, token: Optional[str]) -> Optional[Device]:
        if not token:
            return None
        wanted = _hash(token)
        with self._lock:
            for device in self._devices.values():
                if hmac.compare_digest(device.token_hash, wanted):
                    device.last_seen = self._clock()
                    return device
        return None

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            if self._devices.pop(device_id, None) is None:
                return False
            self._save()
            return True

    def list_devices(self) -> list[dict]:
        with self._lock:
            return [
                {"id": d.id, "name": d.name, "paired_at": d.paired_at, "last_seen": d.last_seen}
                for d in sorted(self._devices.values(), key=lambda d: d.paired_at)
            ]

    # ------------------------------------------------------------- disk

    def _load(self) -> dict[str, Device]:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                rows = json.load(f)
            return {row["id"]: Device(**row) for row in rows}
        except FileNotFoundError:
            return {}
        except (ValueError, TypeError, KeyError):
            # A damaged file must not stop the server from starting; the
            # devices simply pair again.
            return {}

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([asdict(d) for d in self._devices.values()], f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)
