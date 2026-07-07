from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .core import BrokerError, canonical_json, iso_utc, sha256_hex
from .crypto import Ed25519Signer, Ed25519Verifier


class EventStore:
    """Broker-owned receipts and immutable release records.

    Release liveness is intentionally not stored here. `NonceRegistry`, protected
    by `flock`, is the only authority for UNUSED -> RESERVED -> EXECUTING ->
    EXECUTED | UNKNOWN transitions.
    """

    def __init__(self, database_path: str | Path, receipt_signer: Ed25519Signer) -> None:
        self.database_path = Path(database_path)
        self.receipt_signer = receipt_signer
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS proposals (
                    task_id TEXT PRIMARY KEY,
                    proposal_json TEXT NOT NULL,
                    proposal_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    task_id TEXT PRIMARY KEY REFERENCES proposals(task_id),
                    decision_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('HUMAN_GRANTED','HUMAN_DENIED','INPUT_INVALID')),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS releases (
                    release_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES proposals(task_id),
                    release_json TEXT NOT NULL,
                    scope_digest TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    nonce TEXT NOT NULL UNIQUE,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    execution_json TEXT
                );
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    release_id TEXT,
                    sequence INTEGER NOT NULL,
                    body_json TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    signature TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(task_id, sequence)
                );
                """
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    @staticmethod
    def _loads(value: str) -> dict[str, Any]:
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise BrokerError("stored JSON object is malformed")
        return parsed

    def _append_receipt_tx(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str,
        event: str,
        data: dict[str, Any],
        release_id: str | None = None,
    ) -> dict[str, Any]:
        previous = conn.execute(
            "SELECT sequence, digest FROM receipts WHERE task_id=? ORDER BY sequence DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        sequence = 1 if previous is None else int(previous["sequence"]) + 1
        previous_hash = "0" * 64 if previous is None else str(previous["digest"])
        body = {
            "receipt_schema": "matverse.receipt.v1",
            "receipt_id": str(uuid.uuid4()),
            "task_id": task_id,
            "release_id": release_id,
            "sequence": sequence,
            "event": event,
            "data": data,
            "previous_hash": previous_hash,
            "created_at": iso_utc(),
        }
        digest = sha256_hex(canonical_json(body))
        signature = self.receipt_signer.sign_json({"digest": digest, "body": body})
        conn.execute(
            "INSERT INTO receipts(receipt_id,task_id,release_id,sequence,body_json,digest,signature,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (body["receipt_id"], task_id, release_id, sequence, json.dumps(body, separators=(",", ":")), digest, signature, body["created_at"]),
        )
        return {**body, "digest": digest, "signature": signature}

    def create_proposal(self, proposal: dict[str, Any], proposal_hash: str) -> dict[str, Any]:
        task_id = proposal["task_id"]
        with self._transaction() as conn:
            existing = conn.execute("SELECT proposal_hash FROM proposals WHERE task_id=?", (task_id,)).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO proposals(task_id,proposal_json,proposal_hash,created_at) VALUES(?,?,?,?)",
                    (task_id, json.dumps(proposal, separators=(",", ":")), proposal_hash, iso_utc()),
                )
                self._append_receipt_tx(conn, task_id=task_id, event="PROPOSED", data={"proposal_hash": proposal_hash})
            elif existing["proposal_hash"] != proposal_hash:
                raise BrokerError("task_id already belongs to a different immutable proposal")
        return self.get_proposal(task_id)

    def get_proposal(self, task_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT proposal_json,proposal_hash,created_at FROM proposals WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise BrokerError("proposal not found")
        return {"proposal": self._loads(str(row["proposal_json"])), "proposal_hash": row["proposal_hash"], "created_at": row["created_at"]}

    def record_decision(self, task_id: str, decision: dict[str, Any], status: str) -> dict[str, Any]:
        with self._transaction() as conn:
            if conn.execute("SELECT 1 FROM proposals WHERE task_id=?", (task_id,)).fetchone() is None:
                raise BrokerError("proposal not found")
            if conn.execute("SELECT 1 FROM decisions WHERE task_id=?", (task_id,)).fetchone() is not None:
                raise BrokerError("a human decision was already recorded for this task")
            conn.execute(
                "INSERT INTO decisions(task_id,decision_json,status,created_at) VALUES(?,?,?,?)",
                (task_id, json.dumps(decision, separators=(",", ":")), status, iso_utc()),
            )
            return self._append_receipt_tx(conn, task_id=task_id, event=status, data={"decision_id": decision.get("decision_id")})

    def get_decision(self, task_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT decision_json,status,created_at FROM decisions WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise BrokerError("human decision not found")
        return {"decision": self._loads(str(row["decision_json"])), "status": row["status"], "created_at": row["created_at"]}

    def issue_release(self, release_body: dict[str, Any], scope_digest: str, signature: str) -> dict[str, Any]:
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO releases(release_id,task_id,release_json,scope_digest,signature,nonce,issued_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",
                (release_body["release_id"], release_body["task_id"], json.dumps(release_body, separators=(",", ":")), scope_digest, signature, release_body["nonce"], release_body["issued_at"], release_body["expires_at"]),
            )
            self._append_receipt_tx(
                conn,
                task_id=release_body["task_id"],
                release_id=release_body["release_id"],
                event="CASSANDRA_RELEASED",
                data={"scope_digest": scope_digest, "expires_at": release_body["expires_at"]},
            )
        return self.get_release(release_body["release_id"])

    def get_release(self, release_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM releases WHERE release_id=?", (release_id,)).fetchone()
        if row is None:
            raise BrokerError("release not found")
        return {
            "body": self._loads(str(row["release_json"])),
            "scope_digest": row["scope_digest"],
            "signature": row["signature"],
            "execution": None if row["execution_json"] is None else self._loads(str(row["execution_json"])),
        }

    def append_omega_receipt(self, release_id: str, event: str, data: dict[str, Any]) -> dict[str, Any]:
        if event not in {"OMEGA_RESERVED", "OMEGA_EXECUTING", "OMEGA_EXECUTED", "OMEGA_UNKNOWN", "OMEGA_BLOCKED"}:
            raise BrokerError("invalid omega receipt event")
        with self._transaction() as conn:
            row = conn.execute("SELECT task_id FROM releases WHERE release_id=?", (release_id,)).fetchone()
            if row is None:
                raise BrokerError("release not found")
            if event in {"OMEGA_EXECUTED", "OMEGA_UNKNOWN", "OMEGA_BLOCKED"}:
                conn.execute("UPDATE releases SET execution_json=? WHERE release_id=?", (json.dumps(data, separators=(",", ":")), release_id))
            return self._append_receipt_tx(conn, task_id=row["task_id"], release_id=release_id, event=event, data=data)

    def latest_receipt_hash(self, task_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute("SELECT digest FROM receipts WHERE task_id=? ORDER BY sequence DESC LIMIT 1", (task_id,)).fetchone()
        if row is None:
            raise BrokerError("receipt is missing")
        return str(row["digest"])

    def verify_task_chain(self, task_id: str, verifier: Ed25519Verifier) -> list[str]:
        errors: list[str] = []
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM receipts WHERE task_id=? ORDER BY sequence ASC", (task_id,)).fetchall()
        expected_previous = "0" * 64
        expected_sequence = 1
        for row in rows:
            body = self._loads(str(row["body_json"]))
            if int(row["sequence"]) != expected_sequence or body.get("sequence") != expected_sequence:
                errors.append(f"sequence mismatch at receipt {row['receipt_id']}")
            if body.get("previous_hash") != expected_previous:
                errors.append(f"previous hash mismatch at receipt {row['receipt_id']}")
            digest = sha256_hex(canonical_json(body))
            if digest != row["digest"]:
                errors.append(f"digest mismatch at receipt {row['receipt_id']}")
            try:
                verifier.verify_json({"digest": digest, "body": body}, str(row["signature"]))
            except BrokerError:
                errors.append(f"signature mismatch at receipt {row['receipt_id']}")
            expected_previous = str(row["digest"])
            expected_sequence += 1
        return errors
