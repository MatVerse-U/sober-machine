from __future__ import annotations

from typing import Mapping

from .core import BrokerError, require_git_sha, require_sha256


REQUIRED_SNAPSHOT_FIELDS = (
    "base_commit_sha",
    "head_commit_sha_before_execution",
    "staged_diff_sha256",
    "worktree_tree_sha256",
    "policy_digest",
    "actor_id",
)


def verify_snapshot(release: Mapping[str, str], observed: Mapping[str, str]) -> None:
    """Reject any drift between Cassandra release and the privileged worktree.

    `observed` must be collected by the privileged executor immediately before its
    first effect. The Kilo worktree is never accepted as an observation source.
    """
    for field in REQUIRED_SNAPSHOT_FIELDS:
        expected = release.get(field)
        actual = observed.get(field)
        if not isinstance(expected, str) or not isinstance(actual, str):
            raise BrokerError(f"missing snapshot field: {field}")
        if expected != actual:
            raise BrokerError(f"snapshot_drift:{field}")
    require_git_sha(release["base_commit_sha"], "base_commit_sha")
    require_git_sha(release["head_commit_sha_before_execution"], "head_commit_sha_before_execution")
    require_sha256(release["staged_diff_sha256"], "staged_diff_sha256")
    require_sha256(release["worktree_tree_sha256"], "worktree_tree_sha256")
    require_sha256(release["policy_digest"], "policy_digest")
