from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any

from .core import BrokerError, iso_utc, parse_utc, utc_now


class NonceStateError(BrokerError):
    """Machine-readable failure for a consumed or unavailable release nonce."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NonceRegistry:
    """Single-use release state protected with an OS advisory file lock.

    State transitions are exactly:
    UNUSED -> RESERVED -> EXECUTING -> EXECUTED | UNKNOWN

    The registry file must be owned by the privileged omega account and stored
    outside the Kilo worktree. A stale process can never move a terminal state.
    """

    _ALLOWED = {
        "UNUSED": {"RESERVED"},
        "RESERVED": {"EXECUTING"},
        "EXECUTING": {"EXECUTED", "UNKNOWN"},
        "EXECUTED": set(),
        "UNKNOWN": set(),
    }

    def __init__(self, registry_path: str | Path) -> None:
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.registry_path.with_suffix(self.registry_path.suffix + ".lock")
        if not self.registry_path.exists():
            self.registry_path.write_text("{}\n", encoding="utf-8")
            os.chmod(self.registry_path, 0o600)
        if not self.lock_path.exists():
            self.lock_path.touch(mode=0o600)
            os.chmod(self.lock_path, 0o600)

    def register(self, *, nonce: str, release_id: str, expires_at: str) -> dict[str, Any]:
        if not nonce or not release_id:
            raise BrokerError("nonce and release_id are required")
        parse_utc(expires_at)
        with self._locked() as entries:
            if nonce in entries:
                existing = entries[nonce]
                if existing["release_id"] != release_id:
                    raise NonceStateError("nonce_collision")
                return existing
            entry = {
                "nonce": nonce,
                "release_id": release_id,
                "expires_at": expires_at,
                "state": "UNUSED",
                "updated_at": iso_utc(),
            }
            entries[nonce] = entry
            return entry

    def reserve(self, nonce: str, release_id: str) -> dict[str, Any]:
        return self._transition(nonce, release_id, "RESERVED")

    def start_execution(self, nonce: str, release_id: str) -> dict[str, Any]:
        return self._transition(nonce, release_id, "EXECUTING")

    def mark_executed(self, nonce: str, release_id: str) -> dict[str, Any]:
        return self._transition(nonce, release_id, "EXECUTED")

    def mark_unknown(self, nonce: str, release_id: str) -> dict[str, Any]:
        return self._transition(nonce, release_id, "UNKNOWN")

    def get(self, nonce: str) -> dict[str, Any]:
        with self._locked() as entries:
            if nonce not in entries:
                raise NonceStateError("nonce_not_found")
            return dict(entries[nonce])

    def _transition(self, nonce: str, release_id: str, target: str) -> dict[str, Any]:
        with self._locked() as entries:
            entry = entries.get(nonce)
            if entry is None:
                raise NonceStateError("nonce_not_found")
            if entry.get("release_id") != release_id:
                raise NonceStateError("nonce_release_mismatch")
            current = entry.get("state")
            if current == "UNUSED" and parse_utc(entry["expires_at"]) <= utc_now():
                raise NonceStateError("release_expired")
            if target not in self._ALLOWED.get(current, set()):
                code = "nonce_already_reserved" if current in {"RESERVED", "EXECUTING", "EXECUTED", "UNKNOWN"} else "invalid_nonce_transition"
                raise NonceStateError(code)
            entry["state"] = target
            entry["updated_at"] = iso_utc()
            entries[nonce] = entry
            return dict(entry)

    def _load_unlocked(self) -> dict[str, Any]:
        try:
            value = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise BrokerError("nonce registry is malformed") from exc
        if not isinstance(value, dict):
            raise BrokerError("nonce registry must be a JSON object")
        return value

    def _persist_unlocked(self, entries: dict[str, Any]) -> None:
        temporary = self.registry_path.with_suffix(self.registry_path.suffix + ".tmp")
        temporary.write_text(json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.registry_path)

    class _LockedEntries:
        def __init__(self, parent: "NonceRegistry") -> None:
            self.parent = parent
            self.handle: Any = None
            self.entries: dict[str, Any] | None = None

        def __enter__(self) -> dict[str, Any]:
            self.handle = open(self.parent.lock_path, "a+", encoding="utf-8")
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
            self.entries = self.parent._load_unlocked()
            return self.entries

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            try:
                if exc_type is None and self.entries is not None:
                    self.parent._persist_unlocked(self.entries)
            finally:
                if self.handle is not None:
                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
                    self.handle.close()

    def _locked(self) -> "NonceRegistry._LockedEntries":
        return self._LockedEntries(self)
