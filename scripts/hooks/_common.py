"""Shared helpers for the plugin hook scripts. Standard library only.

Design rules for every hook in this directory:
- NEVER break the user's session: any unexpected error must end in a silent exit 0.
- Stay silent outside multi-tenant Django projects (the SessionStart baseline is the
  gate for the other hooks).
- Prefer additionalContext/ask over blocking.
"""

from __future__ import annotations

import hashlib
import json
import os
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
    base = Path(env) if env else Path(tempfile.gettempdir()) / "claude-dmtp-hook-data"
    base.mkdir(parents=True, exist_ok=True)
    return base


def project_dir(payload: dict) -> Path:
    for candidate in (payload.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")):
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


def emit(payload: dict) -> None:
    print(json.dumps(payload))
