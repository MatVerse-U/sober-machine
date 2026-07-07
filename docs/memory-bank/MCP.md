# MCP Boundary — STATUS: HOLD

The source file `scripts/mcp_stdio_server.mjs` implements newline-delimited JSON-RPC over STDIO with `initialize`, `tools/list` and `tools/call`.

It exposes exactly five names:

- `cassandra_propose`
- `cassandra_record_decision`
- `cassandra_release`
- `omega_execute`
- `verify_receipts`

The process contains no GitHub credential, private signing key, Git executable invocation, or direct publishing operation. `tools/call` forwards only allowlisted names to `MATVERSE_BROKER_SOCKET`, a local broker endpoint owned by the `omega` account. The broker endpoint currently keeps `omega_execute` in HOLD until a separately deployed privileged effect adapter exists.

The intended Kilo command is:

```text
node scripts/mcp_stdio_server.mjs
```

Do not add `bash`, Git, GitHub CLI, package managers, Docker or a generic shell to the profile to make this work. That would destroy the boundary.
