# MATVERSE_PR_OPERATOR — restricted profile

STATUS: HOLD. Do not enable until the MCP transport and privileged broker are independently tested.

The operator profile has no shell. `bash`, `sh`, `zsh`, `fish`, `git`, `gh`, `curl`, `wget`, package managers, Docker, deployment, filesystem write and arbitrary process tools are not allowlisted.

The only allowed tools are:

1. `cassandra_propose`
2. `cassandra_record_decision`
3. `cassandra_release`
4. `omega_execute`
5. `verify_receipts`

## Intended Kilo profile configuration

```json
{
  "name": "MATVERSE_PR_OPERATOR",
  "control_mode": "MCP_ONLY",
  "allowed_tools": [
    "cassandra_propose",
    "cassandra_record_decision",
    "cassandra_release",
    "omega_execute",
    "verify_receipts"
  ],
  "denied_tools": [
    "bash", "shell", "terminal", "git", "gh", "edit", "delete",
    "webfetch", "websearch", "docker", "deploy", "mcp_admin"
  ],
  "environment": {
    "PATH": "/opt/matverse-mcp/bin",
    "MATVERSE_CONTROL_MODE": "MCP_ONLY",
    "MATVERSE_BROKER_SOCKET": "/run/omega-broker/broker.sock"
  }
}
```

This document is not itself enforcement. The Kilo runtime must apply the equivalent permissions, the `kilo` account must not possess a GitHub credential, and the MCP process must have no writable access to broker state or keys.
