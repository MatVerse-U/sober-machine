from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path

from omega_broker.nonce_registry import NonceRegistry, NonceStateError


def reserve_once(path: str, queue: multiprocessing.Queue) -> None:
    registry = NonceRegistry(path)
    try:
        registry.reserve("nonce-1", "release-1")
        queue.put("reserved")
    except NonceStateError as exc:
        queue.put(exc.code)


class NonceRegistryTests(unittest.TestCase):
    def test_two_processes_can_only_reserve_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "nonce.json")
            NonceRegistry(path).register(
                nonce="nonce-1",
                release_id="release-1",
                expires_at="2999-01-01T00:00:00Z",
            )
            queue: multiprocessing.Queue = multiprocessing.Queue()
            first = multiprocessing.Process(target=reserve_once, args=(path, queue))
            second = multiprocessing.Process(target=reserve_once, args=(path, queue))
            first.start()
            second.start()
            first.join(10)
            second.join(10)
            results = sorted([queue.get(timeout=2), queue.get(timeout=2)])
            self.assertEqual(results, ["nonce_already_reserved", "reserved"])


if __name__ == "__main__":
    unittest.main()
