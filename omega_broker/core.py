from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any


class BrokerError(RuntimeError):
    """A fail-closed policy or execution error."""


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SAFE_BRANCH_RE = re.compile(r"^kilo/[a-z0-9][a-z0-9._/-]{0,119}$")
SAFE_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def canonical_json(value: Any) -> bytes:
    """Stable UTF-8 serialization used for hashes and signatures."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(value: bytes | str) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime | None = None) -> str:
    instant = value or utc_now()
    return instant.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise BrokerError("timestamp must be UTC ISO-8601 ending in Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError as exc:
        raise BrokerError("invalid ISO-8601 timestamp") from exc


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise BrokerError("base64url value is required")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:  # pragma: no cover - implementation detail varies
        raise BrokerError("invalid base64url data") from exc


def normalized_relative_path(value: str) -> str:
    """Reject absolute paths, traversal, empty names and platform separators."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise BrokerError("path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise BrokerError("path traversal is prohibited")
    normalized = str(path)
    if normalized in {"", "."}:
        raise BrokerError("path must name a file")
    return normalized


def require_sha256(value: str, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise BrokerError(f"{label} must be a lowercase SHA-256 digest")
    return value


def require_git_sha(value: str, label: str) -> str:
    if not isinstance(value, str) or not GIT_SHA_RE.fullmatch(value):
        raise BrokerError(f"{label} must be a 40- or 64-character lowercase Git SHA")
    return value


def require_safe_branch(value: str) -> str:
    if not isinstance(value, str) or value in {"main", "master"} or not SAFE_BRANCH_RE.fullmatch(value):
        raise BrokerError("session branch must match kilo/<safe-name> and cannot target main/master")
    return value


def require_repository(value: str) -> str:
    if not isinstance(value, str) or not SAFE_REPOSITORY_RE.fullmatch(value):
        raise BrokerError("repository must use owner/repository form")
    return value
