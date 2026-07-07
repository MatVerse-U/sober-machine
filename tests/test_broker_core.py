from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from omega_broker.core import BrokerError, canonical_json, iso_utc, sha256_hex
from omega_broker.crypto import Ed25519Signer, Ed25519Verifier, generate_keypair
from omega_broker.policy import Policy
from omega_broker.service import BrokerService
from omega_broker.store import EventStore


class BrokerCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        cass_private, cass_public = root / "cass-private.pem", root / "cass-public.pem"
        human_private, human_public = root / "human-private.pem", root / "human-public.pem"
        generate_keypair(cass_private, cass_public)
        generate_keypair(human_private, human_public)
        self.cass_signer = Ed25519Signer.from_pem_file(cass_private)
        self.human_signer = Ed25519Signer.from_pem_file(human_private)
        self.human_verifier = Ed25519Verifier.from_pem_file(human_public)
        self.policy_file = root / "policy.json"
        self.policy_file.write_text(
            '''{"version":"v1","repositories":{"MatVerse-U/sober-machine":"https://github.com/MatVerse-U/sober-machine.git"},"permitted_path_globs":["docs/**"],"release_ttl_seconds":600}''',
            encoding="utf-8",
        )
        self.service = BrokerService(
            store=EventStore(root / "broker.sqlite3", self.cass_signer),
            policy=Policy.load(self.policy_file),
            cassandra_signer=self.cass_signer,
            human_verifiers={"operator-1": self.human_verifier},
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _proposal(self) -> dict[str, object]:
        patch = b"diff --git a/docs/demo.md b/docs/demo.md\nnew file mode 100644\n--- /dev/null\n+++ b/docs/demo.md\n@@ -0,0 +1 @@\n+demo\n"
        staged = patch
        body: dict[str, object] = {
            "task_id": "task-demo-1",
            "repository": "MatVerse-U/sober-machine",
            "remote_origin": "https://github.com/MatVerse-U/sober-machine.git",
            "base_branch": "main",
            "session_branch": "kilo/task-demo-1",
            "base_commit_sha": "a" * 40,
            "operation": "git.open_draft_pr",
            "allowed_paths": ["docs/demo.md"],
            "artifact_hashes": [{"path": "docs/demo.md", "sha256": sha256_hex("demo\n")}],
            "patch_b64": base64.urlsafe_b64encode(patch).rstrip(b"=").decode("ascii"),
            "patch_sha256": sha256_hex(patch),
            "staged_diff_sha256": sha256_hex(staged),
            "title": "Add demo documentation",
        }
        body["proposal_hash"] = sha256_hex(canonical_json(body))
        return body

    def test_proposal_requires_exact_hash(self) -> None:
        proposal = self._proposal()
        self.service.cassandra_propose(proposal)
        proposal["title"] = "tampered"
        with self.assertRaises(BrokerError):
            self.service.cassandra_propose(proposal)

    def test_release_requires_signed_human_grant_and_is_single_use(self) -> None:
        proposal = self._proposal()
        self.service.cassandra_propose(proposal)
        body = {
            "decision_id": "decision-demo-1",
            "task_id": proposal["task_id"],
            "proposal_hash": proposal["proposal_hash"],
            "decision": "SIM",
            "human_key_id": "operator-1",
            "issued_at": iso_utc(),
        }
        self.service.cassandra_record_decision({**body, "signature": self.human_signer.sign_json(body)})
        release = self.service.cassandra_release("task-demo-1")
        first = self.service.store.reserve_release(release["body"]["release_id"])
        self.assertEqual(first["status"], "RESERVED")
        with self.assertRaises(BrokerError):
            self.service.store.reserve_release(release["body"]["release_id"])

    def test_bad_human_signature_is_rejected(self) -> None:
        proposal = self._proposal()
        self.service.cassandra_propose(proposal)
        body = {
            "decision_id": "decision-demo-2",
            "task_id": proposal["task_id"],
            "proposal_hash": proposal["proposal_hash"],
            "decision": "SIM",
            "human_key_id": "operator-1",
            "issued_at": iso_utc(),
        }
        with self.assertRaises(BrokerError):
            self.service.cassandra_record_decision({**body, "signature": "not-a-valid-signature"})


if __name__ == "__main__":
    unittest.main()
