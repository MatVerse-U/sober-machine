#!/usr/bin/env python3
"""Privileged Cassandra CLI. It has no Git or publishing capability."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from omega_broker.crypto import Ed25519Signer, Ed25519Verifier
from omega_broker.policy import Policy
from omega_broker.service import BrokerService
from omega_broker.store import EventStore


def service_from_env() -> BrokerService:
    required = {
        "MATVERSE_BROKER_DB",
        "MATVERSE_POLICY_PATH",
        "MATVERSE_CASSANDRA_PRIVATE_KEY",
        "MATVERSE_OPERATOR_KEY_ID",
        "MATVERSE_OPERATOR_PUBLIC_KEY",
    }
    missing = sorted(name for name in required if not os.environ.get(name))
    if missing:
        raise SystemExit("missing required environment: " + ", ".join(missing))
    signer = Ed25519Signer.from_pem_file(os.environ["MATVERSE_CASSANDRA_PRIVATE_KEY"])
    return BrokerService(
        store=EventStore(os.environ["MATVERSE_BROKER_DB"], signer),
        policy=Policy.load(os.environ["MATVERSE_POLICY_PATH"]),
        cassandra_signer=signer,
        human_verifiers={
            os.environ["MATVERSE_OPERATOR_KEY_ID"]: Ed25519Verifier.from_pem_file(
                os.environ["MATVERSE_OPERATOR_PUBLIC_KEY"]
            )
        },
    )


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("JSON input must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    propose = sub.add_parser("propose")
    propose.add_argument("proposal", type=Path)
    decide = sub.add_parser("record-decision")
    decide.add_argument("decision", type=Path)
    release = sub.add_parser("release")
    release.add_argument("task_id")
    verify = sub.add_parser("verify")
    verify.add_argument("task_id")
    args = parser.parse_args()
    service = service_from_env()

    if args.command == "propose":
        result = service.cassandra_propose(load_json(args.proposal))
    elif args.command == "record-decision":
        result = service.cassandra_record_decision(load_json(args.decision))
    elif args.command == "release":
        result = service.cassandra_release(args.task_id)
    else:
        verifier = Ed25519Verifier.from_pem_bytes(service.cassandra_signer.public_pem())
        errors = service.store.verify_task_chain(args.task_id, verifier)
        result = {"status": "PASS" if not errors else "BLOCK", "errors": errors}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
