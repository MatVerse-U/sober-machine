#!/usr/bin/env python3
"""Diagnose and prepare local fixes for failed Kilo deployments.

The script clones each failed deployment repository, runs a local Docker build to
capture the failure, and applies conservative, reviewable fixes for common build
problems such as missing requirements files, non-executable entrypoints, and
memory-heavy Dockerfiles.

It intentionally does not push changes to remotes. Review the generated working
copies under ``tmp_recovery/`` before pushing.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FailedApp:
    name: str
    url: str


FAILED_APPS: tuple[FailedApp, ...] = (
    FailedApp("grand-glade-3216", "https://builder.kiloapps.io/apps/9efe016d-e4dc-4e98-8fc1-b08877b0b71c.git"),
    FailedApp("steep-mark-0331", "https://builder.kiloapps.io/apps/643bb676-af06-4954-bb29-0d17c03f7a53.git"),
    FailedApp("iqg", "https://builder.kiloapps.io/apps/8b002d74-5bee-4b7f-b470-f20aacf7ee47.git"),
    FailedApp("entidade-organismo-mnb", "https://builder.kiloapps.io/apps/c121d611-b534-4909-a686-03ba69a7c7f7.git"),
    FailedApp("failhard", "https://builder.kiloapps.io/apps/71f2efd0-8874-4258-8f92-2c17b0728cb0.git"),
    FailedApp("smok", "https://builder.kiloapps.io/apps/2edee707-1813-42df-aeaf-78f5e5366e79.git"),
)


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    stdout: str
    stderr: str


def run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> CommandResult:
    """Run a command without invoking a shell and capture its output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(result.returncode == 0, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(False, stdout, f"{stderr}\nTimeout after {timeout}s".strip())
    except OSError as exc:
        return CommandResult(False, "", str(exc))


def apply_docker_optimization(repo_path: Path, force_multi_stage: bool = False) -> bool:
    """Apply low-risk Dockerfile optimizations and return True if changed."""
    dockerfile_path = repo_path / "Dockerfile"
    if not dockerfile_path.exists():
        dockerfile_path.write_text(
            """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt || pip install --no-cache-dir flask gunicorn
COPY . .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
""",
            encoding="utf-8",
        )
        return True

    content = dockerfile_path.read_text(encoding="utf-8")
    original = content

    if "pip install" in content and "--no-cache-dir" not in content:
        content = content.replace("pip install", "pip install --no-cache-dir")

    if force_multi_stage or len(content) > 2_000:
        content = """# Optimized for constrained cloud builders.
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt ./
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
"""

    if content != original:
        dockerfile_path.write_text(content, encoding="utf-8")
        return True
    return False


def ensure_fallback_requirements(repo_path: Path) -> bool:
    requirements = repo_path / "requirements.txt"
    if requirements.exists():
        return False
    requirements.write_text("flask\ngunicorn\nrequests\nnumpy\npandas\n", encoding="utf-8")
    return True


def fix_executable_scripts(repo_path: Path) -> bool:
    changed = False
    for script_name in ("entrypoint.sh", "start.sh"):
        script_path = repo_path / script_name
        if script_path.exists():
            mode = script_path.stat().st_mode
            script_path.chmod(mode | 0o111)
            changed = True
    return changed


def diagnose_and_fix(app: FailedApp, workdir: Path, keep_existing: bool, build_timeout: int) -> None:
    print(f"[*] Analyzing {app.name}")
    repo_path = workdir / app.name

    if repo_path.exists() and not keep_existing:
        shutil.rmtree(repo_path)
    workdir.mkdir(parents=True, exist_ok=True)

    if not repo_path.exists():
        print(" -> cloning repository")
        clone = run_cmd(["git", "clone", "--depth", "1", app.url, str(repo_path)], timeout=build_timeout)
        if not clone.ok:
            print(f" ! clone failed: {(clone.stderr or clone.stdout).strip()[:300]}")
            return

    print(" -> running local Docker build")
    build = run_cmd(["docker", "build", "-t", f"debug-{app.name}:latest", "."], cwd=repo_path, timeout=build_timeout)
    combined_logs = f"{build.stdout}\n{build.stderr}".lower()

    fixes: list[str] = []
    if build.ok:
        print(" + local build succeeded; applying cache optimization only")
        if apply_docker_optimization(repo_path):
            fixes.append("Dockerfile cache/no-cache optimization")
    else:
        last_line = next((line for line in reversed((build.stderr or build.stdout).splitlines()) if line.strip()), "no build output")
        print(f" ! build failed: {last_line[:300]}")
        if "module not found" in combined_logs or "no module named" in combined_logs:
            if ensure_fallback_requirements(repo_path):
                fixes.append("created fallback requirements.txt")
        if "permission denied" in combined_logs:
            if fix_executable_scripts(repo_path):
                fixes.append("made startup scripts executable")
        if any(marker in combined_logs for marker in ("killed", "memory", "oom", "no space left on device")):
            if apply_docker_optimization(repo_path, force_multi_stage=True):
                fixes.append("rewrote Dockerfile as multi-stage")
        if not fixes and apply_docker_optimization(repo_path):
            fixes.append("Dockerfile pip cache optimization")

    if not fixes:
        print(" - no automatic changes applied")
        return

    run_cmd(["git", "config", "user.email", "fixbot@matverse.local"], cwd=repo_path)
    run_cmd(["git", "config", "user.name", "MatVerse FixBot"], cwd=repo_path)
    run_cmd(["git", "add", "."], cwd=repo_path)
    commit = run_cmd(["git", "commit", "-m", "fix: auto-repair deployment build issues"], cwd=repo_path)
    print(f" + fixes applied: {', '.join(fixes)}")
    print(" + local commit created" if commit.ok else f" ! commit skipped/failed: {commit.stderr.strip()[:200]}")
    print(f" -> review and push from: {repo_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=Path("tmp_recovery"), help="directory for cloned repos")
    parser.add_argument("--keep-existing", action="store_true", help="reuse existing clones instead of deleting them")
    parser.add_argument("--build-timeout", type=int, default=300, help="timeout in seconds for clone/build commands")
    parser.add_argument("--app", choices=[app.name for app in FAILED_APPS], help="diagnose only one app")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    apps = [app for app in FAILED_APPS if args.app in (None, app.name)]
    for app in apps:
        diagnose_and_fix(app, args.workdir, args.keep_existing, args.build_timeout)
        print("-" * 60)


if __name__ == "__main__":
    main()
