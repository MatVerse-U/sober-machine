# MatVerse Ω Boundary Status

## STATUS: HOLD

The repository contains a draft Cassandra broker, signed release primitive, `flock`-guarded nonce lifecycle and append-only receipt chain. It is not approved for any external effect yet.

The intended path is:

`MMNB -> Cassandra release -> Ω execution boundary -> external effect -> receipt -> MMNB`

Kilo is a proposal producer only. It has no authority to run shell commands, Git, GitHub CLI, deployment, Zenodo or Hugging Face publication.

## MCP boundary

The intended MCP surface contains exactly five tools:

- `cassandra_propose`
- `cassandra_record_decision`
- `cassandra_release`
- `omega_execute`
- `verify_receipts`

Read `docs/OMEGA_BOUNDARY.md`, `docs/MATVERSE_PR_OPERATOR_PROFILE.md`, and `deploy/OMEGA_DEPLOYMENT.md` before enabling any Kilo profile.

## Missing proof before PASS

1. Real MCP STDIO transport verified against a Kilo client.
2. Privileged adapter deployed outside the Kilo worktree and account.
3. Main-branch protection and no-bypass GitHub service identity verified.
4. Concurrency, drift, expiry, restricted-profile and disposable-repository end-to-end tests passed with captured outputs.
