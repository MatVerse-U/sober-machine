# Deploying the Ω boundary

This package is deliberately split into an untrusted agent plane and a privileged effect plane.

## Non-negotiable condition

A local script is bypassable whenever the Kilo session can edit it, run arbitrary shell commands as the same Unix user, read its credentials, or access the Docker socket. Do not call the system governed until those conditions are removed materially.

## Accounts and storage

Create two Unix identities:

- `kilo`: proposal-only. No GitHub token, no Git credential helper, no Docker group, no `sudo`, no access to `/etc/omega-broker`, `/var/lib/omega-broker`, or `/run/omega-broker` except the limited broker socket group.
- `omega`: privileged broker and adapter only. Owns the database, Cassandra private key, GitHub App credential helper, clean clones, and execution receipts.

Required permissions:

- `/etc/omega-broker`: `0750 root:omega`
- Cassandra private key: `0400 omega:omega`
- Human public keys: `0444 root:omega`
- `/var/lib/omega-broker`: `0700 omega:omega`
- Kilo source checkout: owned by `kilo`; it must not be used as the execution worktree.

## GitHub enforcement

Use a dedicated GitHub App or service identity restricted to the exact allowlisted repositories. It may create feature branches and draft pull requests only.

On every target repository protect `main` with:

1. pull requests required;
2. human approval required;
3. required checks required;
4. direct pushes disallowed;
5. force-push disabled;
6. branch deletion disabled;
7. no bypass for the Omega service identity.

The Kilo GitHub integration must be read-only or absent. The agent must not receive a PAT, GitHub App private key, deployment key, `gh auth` session, or write-capable remote URL.

## Human decisions

Run `scripts/operator_sign_decision.py` on an operator-controlled machine. The private human decision key is never copied into Kilo, the worktree, a webhook payload, the broker database, or a CI environment.

## Execution adapter

The effect adapter is intentionally not committed as an in-worktree script. It belongs in the separately deployed `omega` service image or host package. Before it creates a commit or PR it must verify:

- Cassandra Ed25519 release signature;
- release state was atomically reserved;
- policy digest, repository, exact remote origin, base commit and session branch;
- immutable patch SHA-256 and staged diff SHA-256;
- exact changed path set and staged file hashes;
- no protected path;
- no main or master target.

It must then produce exactly one draft pull request. Any post-push error is `UNKNOWN`, never retried automatically. Reconciliation is a separate manual operation.

## Kilo Cloud

Kilo Cloud cannot host this boundary safely when it receives a write-capable GitHub integration or broad shell access. In that mode it may produce a patch/proposal only. The privileged broker and effect adapter must run outside the cloud agent.
