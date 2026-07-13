#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write): incremental tenant-isolation audit.

After a .py edit in a project the SessionStart hook marked as multi-tenant, re-run
tenant_static_audit and surface only NEW Critical/High findings for the edited file,
as non-blocking additionalContext. The baseline is then refreshed, so each regression
is reported exactly once instead of nagging on every subsequent edit.

Silent when: not a .py file, no baseline marker (not a multi-tenant repo), no new
Critical/High findings, or anything at all goes wrong.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _common  # noqa: E402

MAX_REPORTED = 3


def main() -> int:
    try:
        payload = _common.read_stdin_json()
        tool_input = payload.get("tool_input") or {}
        file_path = tool_input.get("file_path") or ""
        if not file_path.endswith(".py"):
            return 0

        project = _common.project_dir(payload)
        baseline = _common.load_baseline(project)
        if baseline is None:
            return 0  # SessionStart did not mark this repo as multi-tenant.

        try:
            rel = os.path.relpath(file_path, project)
        except ValueError:
            return 0
        if rel.startswith(".."):
            return 0  # Edited file lives outside the project.

        audit_script = _common.plugin_root() / "scripts" / "tenant_static_audit.py"
        result = subprocess.run(
            [sys.executable, str(audit_script), "--root", str(project), "--format", "json"],
            capture_output=True,
            text=True,
            timeout=25,
        )
        if result.returncode not in (0, 1):
            return 0
        report = json.loads(result.stdout)

        known = {_common.finding_key(f) for f in baseline.get("findings", [])}
        fresh = [
            f for f in report.get("findings", [])
            if f.get("path") == rel
            and f.get("severity") in {"Critical", "High"}
            and _common.finding_key(f) not in known
        ]

        # Refresh the baseline either way: a reported finding is reported once, and
        # fixed findings drop out so they re-report if they ever come back.
        _common.baseline_path(project).write_text(result.stdout, encoding="utf-8")

        if not fresh:
            return 0

        lines = [
            f"- [{f.get('severity')}] {f.get('rule')} at {f.get('path')}:{f.get('line')}: "
            f"{f.get('message')} Fix: {f.get('recommendation')}"
            for f in fresh[:MAX_REPORTED]
        ]
        if len(fresh) > MAX_REPORTED:
            lines.append(f"- ...and {len(fresh) - MAX_REPORTED} more new finding(s) in this file.")
        context = (
            "Tenant-isolation audit found NEW finding(s) introduced by this edit "
            "(django-multitenant-production skill):\n" + "\n".join(lines) +
            "\nAddress them or explain why the pattern is safe here."
        )
        _common.emit({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": context,
            }
        })
        return 0
    except Exception:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
