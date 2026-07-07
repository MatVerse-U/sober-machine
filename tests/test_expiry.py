from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from omega_broker.nonce_registry import NonceRegistry, NonceStateError


class ExpiryTests(unittest.TestCase):
    def test_expired_release_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = NonceRegistry(Path(temp) / "nonce.json")
            registry.register(
                nonce="nonce-expired",
                release_id="release-expired",
                expires_at="2000-01-01T00:00:00Z",
            )
            with self.assertRaisesRegex(NonceStateError, "release_expired"):
                registry.reserve("nonce-expired", "release-expired")


if __name__ == "__main__":
    unittest.main()
