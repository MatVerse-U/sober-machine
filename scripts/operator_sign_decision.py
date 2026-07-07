#!/usr/bin/env python3
"""Create a signed human decision outside the Kilo agent environment."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from omega_broker.core import iso_utc
from omega_broker.crypto import Ed25519Signer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--decision", required=True, choices=("SIM", "NAO"))
    parser.add_argument("--human-key-id", required=True)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    body = {
        "decision_id": str(uuid.uuid4()),
        "task_id": proposal["task_id"],
        "proposal_hash": proposal["proposal_hash"],
        "decision": args.decision,
        "human_key_id": args.human_key_id,
        "issued_at": iso_utc(),
    }
    signer = Ed25519Signer.from_pem_file(args.private_key)
    artifact = {**body, "signature": signer.sign_json(body)}
    args.out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.out.chmod(0o600)


if __name__ == "__main__":
    main()
