# MatVerse deployment recovery runbook

This runbook captures the failed Kilo deployment recovery flow for the Sober Machine repository.

## Failed deployment targets

The recovery script tracks these failed Kilo app repositories:

| App | Repository |
| --- | --- |
| `grand-glade-3216` | `https://builder.kiloapps.io/apps/9efe016d-e4dc-4e98-8fc1-b08877b0b71c.git` |
| `steep-mark-0331` | `https://builder.kiloapps.io/apps/643bb676-af06-4954-bb29-0d17c03f7a53.git` |
| `iqg` | `https://builder.kiloapps.io/apps/8b002d74-5bee-4b7f-b470-f20aacf7ee47.git` |
| `entidade-organismo-mnb` | `https://builder.kiloapps.io/apps/c121d611-b534-4909-a686-03ba69a7c7f7.git` |
| `failhard` | `https://builder.kiloapps.io/apps/71f2efd0-8874-4258-8f92-2c17b0728cb0.git` |
| `smok` | `https://builder.kiloapps.io/apps/2edee707-1813-42df-aeaf-78f5e5366e79.git` |

## Debug commands

Run the recovery script against one app first:

```bash
python3 scripts/fix_failed_deployments.py --app entidade-organismo-mnb
```

Reuse a clone while iterating locally:

```bash
python3 scripts/fix_failed_deployments.py --app entidade-organismo-mnb --keep-existing --build-timeout 600
```

Inspect Docker build logs manually from a cloned recovery repo:

```bash
cd tmp_recovery/entidade-organismo-mnb
docker build --progress=plain --no-cache -t debug-entidade-organismo-mnb . 2>&1 | tee build.log
```

Find dependency references without recursive grep:

```bash
rg -n "pip install|npm install|pnpm install|yarn install|requirements|package.json|ModuleNotFoundError|Cannot find module" .
```

## What the script fixes automatically

- Missing `requirements.txt` when Python import errors indicate an absent dependency manifest.
- Non-executable `entrypoint.sh` or `start.sh` when build logs contain permission errors.
- Memory-heavy Python Docker builds by adding `--no-cache-dir` or replacing the Dockerfile with a multi-stage Python image when logs show OOM-like failures.
- Dockerfiles without any Python baseline by creating a minimal Gunicorn-based fallback Dockerfile.

## Benchmarking before and after

Use Docker's plain progress output plus `/usr/bin/time` to compare elapsed time and peak memory:

```bash
/usr/bin/time -v docker build --progress=plain --no-cache -t before-fix . 2>&1 | tee before.log
/usr/bin/time -v docker build --progress=plain -t after-fix . 2>&1 | tee after.log
```

Prioritize these metrics:

1. Build exit status.
2. Total elapsed wall-clock time.
3. Maximum resident set size from `/usr/bin/time -v`.
4. Final image size from `docker images`.
5. Rebuild time with cache enabled.
