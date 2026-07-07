# Ω Broker Boundary

A script in the same writable Kilo worktree is not a security boundary. This repository therefore separates the agent plane from the privileged execution plane.

## Required trust boundary

- Kilo may create a proposal and an immutable patch bundle only.
- A human signs `SIM` or `NAO` on a separate operator device.
- Cassandra revalidates the signed proposal and mints a short-lived, single-use release.
- Ω executes only a valid Cassandra release through a privileged service account.
- The Kilo account has no GitHub, Zenodo, Hugging Face, deployment, shell-root, Docker-socket, or signing-key credential.

## Release lifecycle

`ISSUED -> RESERVED -> EXECUTED | FAILED | UNKNOWN | BLOCKED`

Reservation must be atomic before any external effect. `UNKNOWN` requires manual reconciliation and may never be retried automatically.

## Deployment invariants

1. The broker database and private keys live outside the Kilo worktree.
2. The broker runs as a dedicated `omega` OS account.
3. Kilo has no write access to broker code, broker state, keys, Git credential helper, Docker socket, or the privileged execution worktree.
4. GitHub uses a minimal GitHub App or service credential that cannot bypass `main` protection.
5. The GitHub protected branch requires PRs and human review; direct pushes and force-pushes are disabled.
6. The privileged executor works from a clean clone and accepts only the signed patch, base commit, branch, path set, artifact hashes, and policy digest in the release.
7. Receipts are append-only in broker-owned storage and are hash chained and signed.

## Kilo Cloud

Kilo Cloud must remain a proposal producer unless it can be proven that the session has no write-capable GitHub credential and cannot access the privileged broker filesystem. A Kilo profile or prompt alone is not an enforcement mechanism.
