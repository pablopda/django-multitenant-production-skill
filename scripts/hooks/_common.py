"""Shared helpers for the plugin hook scripts. Standard library only.

Design rules for every hook in this directory:
- NEVER break the user's session: any unexpected error must end in a silent exit 0.
- Stay silent outside multi-tenant Django projects (the SessionStart baseline is the
  gate for the other hooks).
- Prefer additionalContext/ask over blocking.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The audit baseline JSON doubles as the "this project is multi-tenant" marker.
BASELINE_PREFIX = "audit-baseline-"

# Stack entries from tenant_static_audit that justify hook activity. The
# "custom or unknown tenant implementation" fallback is deliberately excluded:
# it triggers on generic words like "account" and would make the hooks noisy
# in ordinary Django repos.
STRONG_STACK_MARKERS = (
    "django-tenants",
    "django-pgschemas",
    "django-tenant-users",
    "django-multitenant",
    "django-tenant-schemas",
)


def read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def plugin_root() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env:
        return Path(env)
    # scripts/hooks/_common.py -> repo root
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        base = Path(env)
    else:
        # Per-user fallback: a fixed world-shared /tmp path would collide across users
        # (second user's writes fail EACCES and silently disable the hooks) and expose
        # audit evidence to other accounts.
        try:
            user = getpass.getuser()
        except Exception:
            user = str(os.getuid()) if hasattr(os, "getuid") else "user"
        base = Path(tempfile.gettempdir()) / f"claude-dmtp-hook-data-{user}"
    base.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    return base


def project_dir(payload: dict) -> Path:
    # CLAUDE_PROJECT_DIR first: it is stable for the whole session, while the payload
    # cwd drifts with `cd` — a drifted cwd changes the project hash and silently
    # disarms the baseline-gated hooks.
    for candidate in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if candidate:
            return Path(candidate)
    return Path.cwd()


def project_key(project: Path) -> str:
    return hashlib.sha256(str(project.resolve()).encode("utf-8")).hexdigest()[:12]


def baseline_path(project: Path) -> Path:
    return data_dir() / f"{BASELINE_PREFIX}{project_key(project)}.json"


def load_baseline(project: Path) -> dict | None:
    path = baseline_path(project)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def finding_key(finding: dict) -> tuple:
    # Line numbers shift on every edit; (path, rule, evidence) survives reflows so a
    # pre-existing finding is not re-reported after unrelated edits to the same file.
    return (finding.get("path"), finding.get("rule"), finding.get("evidence"))


def run_audit(project: Path, timeout: int = 25):
    """Run tenant_static_audit against `project`. Returns (raw_stdout, parsed_report)
    or None on any failure (missing script, bad exit, timeout, unparseable output)."""
    audit_script = plugin_root() / "scripts" / "tenant_static_audit.py"
    if not audit_script.is_file():
        return None
    result = subprocess.run(
        [sys.executable, str(audit_script), "--root", str(project), "--format", "json"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode not in (0, 1):
        return None
    try:
        return result.stdout, json.loads(result.stdout)
    except ValueError:
        return None


def write_baseline(project: Path, report: dict) -> None:
    """Atomically replace the baseline (concurrent hook runs must not interleave)."""
    path = baseline_path(project)
    tmp = path.with_suffix(f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(report), encoding="utf-8")
    os.replace(tmp, path)


def emit(payload: dict) -> None:
    print(json.dumps(payload))
