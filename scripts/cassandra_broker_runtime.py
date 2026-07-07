#!/usr/bin/env python3
"""Nonce-aware Cassandra runtime entrypoint for the privileged omega account."""

import os

from omega_broker.crypto import Ed25519Signer, Ed25519Verifier
from omega_broker.nonce_registry import NonceRegistry
from omega_broker.policy import Policy
from omega_broker.service import BrokerService
from omega_broker.store import EventStore


def service_from_environment() -> BrokerService:
    names = (
        "MATVERSE_BROKER_DB",
        "MATVERSE_NONCE_REGISTRY",
        "MATVERSE_POLICY_PATH",
        "MATVERSE_CASSANDRA_PRIVATE_KEY",
        "MATVERSE_OPERATOR_KEY_ID",
        "MATVERSE_OPERATOR_PUBLIC_KEY",
    )
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise RuntimeError("missing environment: " + ", ".join(missing))
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
        nonce_registry=NonceRegistry(os.environ["MATVERSE_NONCE_REGISTRY"]),
    )
