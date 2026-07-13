#!/usr/bin/env python3
"""PreToolUse hook (Bash): ask before a bare `manage.py migrate` in a schema-per-tenant
project (SKILL.md rule 8 made mechanical).

Uses permissionDecision "ask" rather than "deny": legitimate edge cases exist (a
non-tenant DATABASES alias, public-schema bootstrap), so the user decides — the hook
just makes sure the decision is conscious.

Silent when: no baseline marker, project is not schema-per-tenant, or the command is
not a bare migrate.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

# manage.py migrate / django-admin migrate, but not migrate_schemas and not --help.
BARE_MIGRATE = re.compile(r"(?:manage\.py|django-admin)\s+migrate(?!\w|_schemas)\b")


def main() -> int:
    try:
        payload = _common.read_stdin_json()
        if payload.get("tool_name") not in (None, "Bash"):
            return 0
        command = (payload.get("tool_input") or {}).get("command") or ""
        if not BARE_MIGRATE.search(command) or "--help" in command:
            return 0

        project = _common.project_dir(payload)
        baseline = _common.load_baseline(project)
        if baseline is None:
            return 0
        if baseline.get("facts", {}).get("tenancy_mode") != "schema-per-tenant":
            return 0

        _common.emit({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": (
                    "Schema-per-tenant project: verify which `migrate` this runs. When django-tenants "
                    "wins command resolution it aliases `migrate` to `migrate_schemas` (migrating ALL "
                    "tenant schemas — heavy for a hotfix); when it does not, a bare `migrate` bypasses "
                    "tenant schemas entirely. Prefer explicit `migrate_schemas` "
                    "(django-multitenant-production skill, rule 8). Approve only if this is intentional."
                ),
            }
        })
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
