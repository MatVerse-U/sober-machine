from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from typing import Any

from .core import BrokerError, b64url_decode, canonical_json, iso_utc, require_sha256, sha256_hex, utc_now
from .crypto import Ed25519Signer, Ed25519Verifier
from .nonce_registry import NonceRegistry
from .policy import Policy
from .store import EventStore


class BrokerService:
    """Cassandra functions. This class never invokes Git, GitHub, Zenodo or HF."""

    def __init__(
        self,
        *,
        store: EventStore,
        policy: Policy,
        cassandra_signer: Ed25519Signer,
        human_verifiers: dict[str, Ed25519Verifier],
        nonce_registry: NonceRegistry,
    ) -> None:
        self.store = store
        self.policy = policy
        self.cassandra_signer = cassandra_signer
        self.human_verifiers = human_verifiers
        self.nonce_registry = nonce_registry

    def cassandra_propose(self, proposal: dict[str, Any]) -> dict[str, Any]:
        self.policy.validate_proposal(proposal)
        patch = b64url_decode(proposal.get("patch_b64"))
        if sha256_hex(patch) != proposal.get("patch_sha256"):
            raise BrokerError("patch bytes do not match patch_sha256")
        if not isinstance(proposal.get("title"), str) or not proposal["title"].strip() or len(proposal["title"]) > 160:
            raise BrokerError("proposal title is required and must be at most 160 characters")
        proposal_body = {key: value for key, value in proposal.items() if key != "proposal_hash"}
        proposal_hash = sha256_hex(canonical_json(proposal_body))
        supplied = proposal.get("proposal_hash")
        if supplied is not None and supplied != proposal_hash:
            raise BrokerError("proposal_hash does not match the canonical proposal body")
        immutable = {**proposal_body, "proposal_hash": proposal_hash}
        return self.store.create_proposal(immutable, proposal_hash)

    def cassandra_record_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        raw = decision.get("decision")
        if raw not in {"SIM", "NAO"}:
            task_id = decision.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise BrokerError("task_id is required even for invalid decision input")
            return self.store.record_decision(task_id, {"task_id": task_id, "decision": raw}, "INPUT_INVALID")
        required = {"decision_id", "task_id", "proposal_hash", "decision", "human_key_id", "issued_at", "signature"}
        if not required.issubset(decision):
            raise BrokerError("signed human decision is incomplete")
        verifier = self.human_verifiers.get(str(decision["human_key_id"]))
        if verifier is None:
            raise BrokerError("human signer is not authorized")
        body = {key: decision[key] for key in required - {"signature"}}
        verifier.verify_json(body, str(decision["signature"]))
        proposal = self.store.get_proposal(str(decision["task_id"]))
        if decision["proposal_hash"] != proposal["proposal_hash"]:
            raise BrokerError("decision does not bind to the immutable proposal hash")
        status = "HUMAN_GRANTED" if raw == "SIM" else "HUMAN_DENIED"
        return self.store.record_decision(str(decision["task_id"]), decision, status)

    def cassandra_release(self, task_id: str) -> dict[str, Any]:
        proposal_record = self.store.get_proposal(task_id)
        decision_record = self.store.get_decision(task_id)
        if decision_record["status"] != "HUMAN_GRANTED":
            raise BrokerError("Cassandra refuses release unless a signed HUMAN_GRANTED decision exists")
        proposal = proposal_record["proposal"]
        self.policy.validate_proposal(proposal)
        now = utc_now()
        release_body = {
            "release_schema": "matverse.cassandra.release.v1",
            "release_id": str(uuid.uuid4()),
            "task_id": task_id,
            "proposal_hash": proposal_record["proposal_hash"],
            "decision_receipt_hash": self._latest_receipt_hash(task_id),
            "policy_version": self.policy.version,
            "policy_digest": self.policy.digest,
            "repository": proposal["repository"],
            "remote_origin": proposal["remote_origin"],
            "base_branch": proposal["base_branch"],
            "session_branch": proposal["session_branch"],
            "base_commit_sha": proposal["base_commit_sha"],
            "head_commit_sha_before_execution": proposal["head_commit_sha_before_execution"],
            "worktree_tree_sha256": proposal["worktree_tree_sha256"],
            "actor_id": proposal["actor_id"],
            "operation": proposal["operation"],
            "allowed_paths": proposal["allowed_paths"],
            "artifact_hashes": proposal["artifact_hashes"],
            "patch_sha256": proposal["patch_sha256"],
            "staged_diff_sha256": proposal["staged_diff_sha256"],
            "nonce": secrets.token_urlsafe(32),
            "not_before": iso_utc(now),
            "expires_at": iso_utc(now + timedelta(seconds=self.policy.release_ttl_seconds)),
            "issued_at": iso_utc(now),
        }
        self.policy.validate_release(release_body)
        scope_digest = sha256_hex(canonical_json(release_body))
        signed_body = {**release_body, "scope_digest": scope_digest}
        signature = self.cassandra_signer.sign_json(signed_body)
        issued = self.store.issue_release(signed_body, scope_digest, signature)
        # A crash after issuance but before register is fail-closed: Ω cannot reserve an unregistered nonce.
        self.nonce_registry.register(
            nonce=signed_body["nonce"],
            release_id=signed_body["release_id"],
            expires_at=signed_body["expires_at"],
        )
        return issued

    def _latest_receipt_hash(self, task_id: str) -> str:
        errors = self.store.verify_task_chain(task_id, Ed25519Verifier.from_pem_bytes(self.cassandra_signer.public_pem()))
        if errors:
            raise BrokerError("receipt chain failed verification before release: " + "; ".join(errors))
        import sqlite3

        conn = sqlite3.connect(self.store.database_path)
        try:
            row = conn.execute(
                "SELECT digest FROM receipts WHERE task_id=? ORDER BY sequence DESC LIMIT 1", (task_id,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise BrokerError("decision receipt is missing")
        require_sha256(str(row[0]), "decision_receipt_hash")
        return str(row[0])
