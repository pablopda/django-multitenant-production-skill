#!/usr/bin/env python3
"""SessionStart hook: detect a multi-tenant Django project, inject tenancy context,
and snapshot a tenant_static_audit baseline for the edit-time hook.

Silent (exit 0, no output) in projects without a recognized multi-tenant stack.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

SCHEMA_RULES = (
    "use migrate_schemas (never an un-audited bare migrate); "
    "session-mode pooling only (transaction-mode PgBouncer silently leaks across schemas); "
    "Celery tasks and management commands need explicit tenant/schema context; "
    "cache keys and upload paths must be tenant-scoped"
)
SHARED_RULES = (
    "every tenant-owned query must be tenant-scoped (no bare Model.objects in app code); "
    "add tenant-scoped unique constraints; never trust client-supplied tenant ids; "
    "cache keys and upload paths must be tenant-scoped"
)


def main() -> int:
    try:
        payload = _common.read_stdin_json()
        project = _common.project_dir(payload)
        if not project.is_dir():
            return 0

        audit_script = _common.plugin_root() / "scripts" / "tenant_static_audit.py"
        if not audit_script.is_file():
            return 0

        result = subprocess.run(
            [sys.executable, str(audit_script), "--root", str(project), "--format", "json"],
            capture_output=True,
            text=True,
            timeout=25,
        )
        if result.returncode not in (0, 1):
            return 0
        report = json.loads(result.stdout)
        stack = report.get("facts", {}).get("detected_stack", [])
        packages = report.get("facts", {}).get("packages", {})

        strong = any(
            any(marker in entry for marker in _common.STRONG_STACK_MARKERS)
            for entry in stack
        ) or any(marker in packages for marker in _common.STRONG_STACK_MARKERS)
        if not strong:
            # Not a (recognized) multi-tenant project: leave no marker so the other
            # hooks stay silent too, and drop any stale baseline.
            try:
                _common.baseline_path(project).unlink()
            except OSError:
                pass
            return 0

        _common.baseline_path(project).write_text(result.stdout, encoding="utf-8")

        tenancy_mode = report.get("facts", {}).get("tenancy_mode", "")
        schema_mode = tenancy_mode == "schema-per-tenant"
        stack_desc = "; ".join(stack) if stack else "multi-tenant Django"
        rules = SCHEMA_RULES if schema_mode else SHARED_RULES
        context = (
            f"This project is a multi-tenant Django app ({stack_desc}). "
            "The django-multitenant-production skill applies to ANY change touching models, views, "
            "admin, tasks, caching, storage, sessions, or migrations — load it for tenancy-relevant work. "
            f"Hard rules: {rules}. "
            "Cross-tenant negative tests are release blockers for tenant-owned features."
        )
        _common.emit({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        })
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
