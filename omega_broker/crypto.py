from __future__ import annotations

from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .core import BrokerError, b64url_decode, b64url_encode, canonical_json


class Ed25519Signer:
    """Private signing key that must exist only in the privileged broker runtime."""

    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private_key = private_key

    @classmethod
    def from_pem_file(cls, path: str | Path) -> "Ed25519Signer":
        raw = Path(path).read_bytes()
        key = serialization.load_pem_private_key(raw, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise BrokerError("expected an Ed25519 private key")
        return cls(key)

    def sign_json(self, body: object) -> str:
        return b64url_encode(self._private_key.sign(canonical_json(body)))

    def public_pem(self) -> bytes:
        return self._private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )


class Ed25519Verifier:
    """Public verifier safe to distribute to validation-only processes."""

    def __init__(self, public_key: Ed25519PublicKey) -> None:
        self._public_key = public_key

    @classmethod
    def from_pem_file(cls, path: str | Path) -> "Ed25519Verifier":
        raw = Path(path).read_bytes()
        key = serialization.load_pem_public_key(raw)
        if not isinstance(key, Ed25519PublicKey):
            raise BrokerError("expected an Ed25519 public key")
        return cls(key)

    @classmethod
    def from_pem_bytes(cls, raw: bytes) -> "Ed25519Verifier":
        key = serialization.load_pem_public_key(raw)
        if not isinstance(key, Ed25519PublicKey):
            raise BrokerError("expected an Ed25519 public key")
        return cls(key)

    def verify_json(self, body: object, signature: str) -> None:
        try:
            self._public_key.verify(b64url_decode(signature), canonical_json(body))
        except InvalidSignature as exc:
            raise BrokerError("Ed25519 signature verification failed") from exc


def generate_keypair(private_path: str | Path, public_path: str | Path) -> None:
    """Generate a keypair for an operator workstation or privileged broker only."""
    private = Ed25519PrivateKey.generate()
    Path(private_path).write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    Path(public_path).write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
