from __future__ import annotations

import unittest

from omega_broker.core import BrokerError
from omega_broker.snapshot import verify_snapshot


class SnapshotTests(unittest.TestCase):
    def test_drift_is_blocked(self) -> None:
        release = {
            "base_commit_sha": "a" * 40,
            "head_commit_sha_before_execution": "a" * 40,
            "staged_diff_sha256": "b" * 64,
            "worktree_tree_sha256": "c" * 64,
            "policy_digest": "d" * 64,
            "actor_id": "gpt-kilo/operator-1",
        }
        observed = dict(release)
        verify_snapshot(release, observed)
        observed["worktree_tree_sha256"] = "e" * 64
        with self.assertRaises(BrokerError):
            verify_snapshot(release, observed)


if __name__ == "__main__":
    unittest.main()
