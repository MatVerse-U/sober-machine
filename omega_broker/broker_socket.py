from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from .core import BrokerError
from .crypto import Ed25519Verifier
from .service import BrokerService


class BrokerSocketServer:
    """Line-delimited local RPC for the unprivileged MCP relay.

    Run this only as the omega account. The socket directory and broker state must
    be outside the Kilo worktree. This dispatcher never accepts arbitrary commands.
    """

    def __init__(self, socket_path: str | Path, service: BrokerService) -> None:
        self.socket_path = Path(socket_path)
        self.service = service

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        method = request.get("method")
        params = request.get("params")
        if not isinstance(method, str) or not isinstance(params, dict):
            raise BrokerError("invalid broker request")
        if method == "cassandra_propose":
            return self.service.cassandra_propose(params["proposal"])
        if method == "cassandra_record_decision":
            return self.service.cassandra_record_decision(params["decision"])
        if method == "cassandra_release":
            return self.service.cassandra_release(params["task_id"])
        if method == "verify_receipts":
            verifier = Ed25519Verifier.from_pem_bytes(self.service.cassandra_signer.public_pem())
            errors = self.service.store.verify_task_chain(params["task_id"], verifier)
            return {"status": "PASS" if not errors else "BLOCK", "errors": errors}
        if method == "omega_execute":
            # Effects stay blocked until a separately deployed omega adapter has
            # collected a trusted clean-clone snapshot and is registered here.
            return {"status": "HOLD", "code": "privileged_effect_adapter_not_deployed"}
        raise BrokerError("broker method is not allowlisted")

    def serve_forever(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists():
            self.socket_path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.socket_path))
            server.listen(16)
            while True:
                connection, _ = server.accept()
                with connection:
                    request_line = b""
                    while not request_line.endswith(b"\n"):
                        chunk = connection.recv(65536)
                        if not chunk:
                            break
                        request_line += chunk
                    try:
                        request = json.loads(request_line.decode("utf-8"))
                        result = self.dispatch(request)
                        reply = {"status": "OK", "result": result}
                    except (BrokerError, KeyError, TypeError, json.JSONDecodeError) as exc:
                        reply = {"status": "BLOCK", "error": str(exc)}
                    connection.sendall(json.dumps(reply, separators=(",", ":")).encode("utf-8") + b"\n")
