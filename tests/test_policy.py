from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from omega_broker.core import BrokerError
from omega_broker.policy import Policy


class PolicyTests(unittest.TestCase):
    def _policy(self) -> Policy:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "policy.json"
        path.write_text(json.dumps({
            "version": "v1",
            "repositories": {"MatVerse-U/sober-machine": "https://github.com/MatVerse-U/sober-machine.git"},
            "permitted_path_globs": ["docs/**"],
            "release_ttl_seconds": 600,
        }), encoding="utf-8")
        return Policy.load(path)

    def _proposal(self) -> dict[str, object]:
        return {
            "task_id": "task-1",
            "actor_id": "gpt-kilo/operator-1",
            "repository": "MatVerse-U/sober-machine",
            "remote_origin": "https://github.com/MatVerse-U/sober-machine.git",
            "base_branch": "main",
            "session_branch": "kilo/task-1",
            "base_commit_sha": "a" * 40,
            "head_commit_sha_before_execution": "a" * 40,
            "staged_diff_sha256": "b" * 64,
            "patch_sha256": "c" * 64,
            "worktree_tree_sha256": "d" * 64,
            "operation": "git.open_draft_pr",
            "allowed_paths": ["docs/demo.md"],
            "artifact_hashes": [{"path": "docs/demo.md", "sha256": "e" * 64}],
        }

    def test_foreign_origin_is_blocked(self) -> None:
        proposal = self._proposal()
        proposal["remote_origin"] = "https://example.invalid/foreign.git"
        with self.assertRaises(BrokerError):
            self._policy().validate_proposal(proposal)

    def test_main_and_master_are_blocked(self) -> None:
        for branch in ("main", "master"):
            proposal = self._proposal()
            proposal["session_branch"] = branch
            with self.assertRaises(BrokerError):
                self._policy().validate_proposal(proposal)

    def test_zero_ttl_policy_is_valid_for_expiry_test(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / "policy.json"
        path.write_text(json.dumps({
            "version": "v1",
            "repositories": {"MatVerse-U/sober-machine": "https://github.com/MatVerse-U/sober-machine.git"},
            "permitted_path_globs": ["docs/**"],
            "release_ttl_seconds": 0,
        }), encoding="utf-8")
        self.assertEqual(Policy.load(path).release_ttl_seconds, 0)


if __name__ == "__main__":
    unittest.main()
