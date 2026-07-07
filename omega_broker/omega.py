from __future__ import annotations

from typing import Any

from .core import BrokerError
from .crypto import Ed25519Verifier
from .nonce_registry import NonceRegistry
from .policy import Policy
from .snapshot import verify_snapshot
from .store import EventStore


class OmegaLifecycle:
    """Coordinates the non-bypassable release lifecycle.

    This object validates and transitions a release only. The actual effect adapter
    must be a separately deployed process under the privileged omega account.
    """

    def __init__(
        self,
        *,
        store: EventStore,
        policy: Policy,
        nonce_registry: NonceRegistry,
        cassandra_verifier: Ed25519Verifier,
    ) -> None:
        self.store = store
        self.policy = policy
        self.nonce_registry = nonce_registry
        self.cassandra_verifier = cassandra_verifier

    def reserve(self, release_id: str) -> dict[str, Any]:
        release = self.store.get_release(release_id)
        body = release["body"]
        self._validate_static(release)
        state = self.nonce_registry.reserve(body["nonce"], release_id)
        receipt = self.store.append_omega_receipt(release_id, "OMEGA_RESERVED", {"nonce_state": state["state"]})
        return {"release": release, "nonce": state, "receipt": receipt}

    def begin_execution(self, release_id: str, observed_snapshot: dict[str, str]) -> dict[str, Any]:
        release = self.store.get_release(release_id)
        body = release["body"]
        self._validate_static(release)
        verify_snapshot(body, observed_snapshot)
        state = self.nonce_registry.start_execution(body["nonce"], release_id)
        receipt = self.store.append_omega_receipt(release_id, "OMEGA_EXECUTING", {"nonce_state": state["state"]})
        return {"release": release, "nonce": state, "receipt": receipt}

    def completed(self, release_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        release = self.store.get_release(release_id)
        state = self.nonce_registry.mark_executed(release["body"]["nonce"], release_id)
        receipt = self.store.append_omega_receipt(release_id, "OMEGA_EXECUTED", {"nonce_state": state["state"], **evidence})
        return {"nonce": state, "receipt": receipt}

    def unknown(self, release_id: str, reason: str) -> dict[str, Any]:
        release = self.store.get_release(release_id)
        state = self.nonce_registry.mark_unknown(release["body"]["nonce"], release_id)
        receipt = self.store.append_omega_receipt(release_id, "OMEGA_UNKNOWN", {"nonce_state": state["state"], "reason": reason[:500]})
        return {"nonce": state, "receipt": receipt}

    def _validate_static(self, release: dict[str, Any]) -> None:
        body = release["body"]
        self.cassandra_verifier.verify_json(body, str(release["signature"]))
        self.policy.validate_release(body)
        proposal = self.store.get_proposal(body["task_id"])
        if proposal["proposal_hash"] != body["proposal_hash"]:
            raise BrokerError("release is not bound to the immutable proposal")
        decision = self.store.get_decision(body["task_id"])
        if decision["status"] != "HUMAN_GRANTED":
            raise BrokerError("release has no HUMAN_GRANTED decision")
