from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import (
    BrokerError,
    canonical_json,
    normalized_relative_path,
    require_git_sha,
    require_repository,
    require_safe_branch,
    require_sha256,
    sha256_hex,
)


DEFAULT_PROTECTED_PATHS = (
    ".git/**",
    ".github/**",
    ".gitlab/**",
    "**/.env",
    "**/.env.*",
    "**/*secret*",
    "**/*credential*",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa",
    "**/authorized_keys",
    "Dockerfile",
    "**/Dockerfile",
    "compose*.yml",
    "**/compose*.yml",
)
ACTOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,127}$")


@dataclass(frozen=True)
class Policy:
    version: str
    repositories: dict[str, str]
    permitted_path_globs: tuple[str, ...]
    protected_path_globs: tuple[str, ...]
    release_ttl_seconds: int
    branch_prefix: str = "kilo/"
    permitted_operation: str = "git.open_draft_pr"

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        try:
            policy = cls(
                version=str(raw["version"]),
                repositories=dict(raw["repositories"]),
                permitted_path_globs=tuple(raw["permitted_path_globs"]),
                protected_path_globs=tuple(raw.get("protected_path_globs", DEFAULT_PROTECTED_PATHS)),
                release_ttl_seconds=int(raw.get("release_ttl_seconds", 600)),
                branch_prefix=str(raw.get("branch_prefix", "kilo/")),
                permitted_operation=str(raw.get("permitted_operation", "git.open_draft_pr")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BrokerError("invalid policy document") from exc
        # Zero is permitted only to make expiration behavior testable; production policy must use a positive TTL.
        if not policy.version or policy.release_ttl_seconds < 0 or policy.release_ttl_seconds > 3600:
            raise BrokerError("policy release_ttl_seconds must be between 0 and 3600")
        if not policy.repositories or not policy.permitted_path_globs:
            raise BrokerError("policy must define repositories and permitted_path_globs")
        for repository, origin in policy.repositories.items():
            require_repository(repository)
            if origin != f"https://github.com/{repository}.git":
                raise BrokerError("policy origins must be canonical GitHub HTTPS URLs")
        return policy

    @property
    def digest(self) -> str:
        return sha256_hex(canonical_json({
            "version": self.version,
            "repositories": self.repositories,
            "permitted_path_globs": self.permitted_path_globs,
            "protected_path_globs": self.protected_path_globs,
            "release_ttl_seconds": self.release_ttl_seconds,
            "branch_prefix": self.branch_prefix,
            "permitted_operation": self.permitted_operation,
        }))

    def validate_path(self, path: str) -> str:
        normalized = normalized_relative_path(path)
        if any(fnmatch.fnmatchcase(normalized, pattern) for pattern in self.protected_path_globs):
            raise BrokerError(f"protected path is prohibited: {normalized}")
        if not any(fnmatch.fnmatchcase(normalized, pattern) for pattern in self.permitted_path_globs):
            raise BrokerError(f"path is outside the policy allowlist: {normalized}")
        return normalized

    def validate_proposal(self, proposal: dict[str, Any]) -> None:
        repository = require_repository(proposal.get("repository"))
        if repository not in self.repositories:
            raise BrokerError("repository is not allowlisted")
        if proposal.get("remote_origin") != self.repositories[repository]:
            raise BrokerError("remote origin is not canonical for the repository")
        if proposal.get("base_branch") != "main":
            raise BrokerError("only main may be used as the pull-request base")
        branch = require_safe_branch(proposal.get("session_branch"))
        task_id = proposal.get("task_id")
        if not isinstance(task_id, str) or not task_id or branch != f"{self.branch_prefix}{task_id}":
            raise BrokerError("session branch must be exactly kilo/<task_id>")
        actor_id = proposal.get("actor_id")
        if not isinstance(actor_id, str) or not ACTOR_RE.fullmatch(actor_id):
            raise BrokerError("actor_id must be a stable bounded identifier")
        require_git_sha(proposal.get("base_commit_sha"), "base_commit_sha")
        require_git_sha(proposal.get("head_commit_sha_before_execution"), "head_commit_sha_before_execution")
        if proposal["head_commit_sha_before_execution"] != proposal["base_commit_sha"]:
            raise BrokerError("head_commit_sha_before_execution must equal the clean base commit")
        require_sha256(proposal.get("patch_sha256"), "patch_sha256")
        require_sha256(proposal.get("staged_diff_sha256"), "staged_diff_sha256")
        require_sha256(proposal.get("worktree_tree_sha256"), "worktree_tree_sha256")
        if proposal.get("operation") != self.permitted_operation:
            raise BrokerError("operation is not permitted")
        allowed_paths = proposal.get("allowed_paths")
        artifacts = proposal.get("artifact_hashes")
        if not isinstance(allowed_paths, list) or not allowed_paths:
            raise BrokerError("proposal must contain at least one allowed path")
        if not isinstance(artifacts, list) or not artifacts:
            raise BrokerError("proposal must contain at least one artifact hash")
        path_set = {self.validate_path(path) for path in allowed_paths}
        artifact_paths: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise BrokerError("artifact hash entries must be objects")
            path = self.validate_path(artifact.get("path"))
            require_sha256(artifact.get("sha256"), f"artifact hash for {path}")
            artifact_paths.add(path)
        if path_set != artifact_paths:
            raise BrokerError("allowed_paths and artifact_hashes must name the same exact files")

    def validate_release(self, body: dict[str, Any]) -> None:
        self.validate_proposal(body)
        if body.get("policy_version") != self.version or body.get("policy_digest") != self.digest:
            raise BrokerError("release policy identity does not match the active policy")
        if body.get("release_schema") != "matverse.cassandra.release.v1":
            raise BrokerError("unsupported release schema")
        if not isinstance(body.get("nonce"), str) or len(body["nonce"]) < 32:
            raise BrokerError("release nonce is missing or too short")
