"""Tests for the plugin packaging and the three hook scripts.

Hook scripts are exercised end-to-end via subprocess with a JSON payload on stdin and
CLAUDE_PLUGIN_ROOT/CLAUDE_PLUGIN_DATA pointed at temp dirs, mirroring how Claude Code
invokes them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_static_audit import build_django_tenants_fixture
from tests.util import REPO_ROOT, SKILL_MD, parse_frontmatter, write_fixture

HOOKS_DIR = REPO_ROOT / "scripts" / "hooks"


def run_hook(script: str, payload: dict, data_dir: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO_ROOT)
    env["CLAUDE_PLUGIN_DATA"] = data_dir
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def baseline_files(data_dir: str) -> list:
    return sorted(Path(data_dir).glob("audit-baseline-*.json"))


class PluginPackagingTests(unittest.TestCase):
    def test_plugin_manifest_is_valid_and_consistent(self):
        manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        frontmatter = parse_frontmatter(SKILL_MD.read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], frontmatter["name"],
                         "plugin name must match the skill name")
        self.assertEqual(manifest["version"], frontmatter["metadata"]["version"],
                         "plugin version must match SKILL.md metadata.version")
        self.assertTrue(manifest.get("description"))

    def test_marketplace_manifest_is_valid(self):
        marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertTrue(marketplace.get("name"))
        self.assertIn("owner", marketplace)
        plugins = marketplace.get("plugins", [])
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["name"], "django-multitenant-production")
        self.assertEqual(plugins[0]["source"], "./")

    def test_hooks_manifest_references_existing_executable_scripts(self):
        hooks = json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        events = hooks["hooks"]
        self.assertEqual(set(events), {"SessionStart", "PostToolUse", "PreToolUse"})
        for entries in events.values():
            for entry in entries:
                for handler in entry["hooks"]:
                    self.assertEqual(handler["type"], "command")
                    self.assertIn("timeout", handler)
                    command = handler["command"]
                    self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)
                    script_rel = command.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].rstrip('"')
                    script = REPO_ROOT / script_rel
                    self.assertTrue(script.is_file(), f"hook script missing: {script_rel}")
                    self.assertTrue(os.access(script, os.X_OK), f"hook script not executable: {script_rel}")


class SessionStartHookTests(unittest.TestCase):
    def test_multi_tenant_project_gets_context_and_baseline(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as data:
            build_django_tenants_fixture(Path(project))
            result = run_hook("session_start_tenancy.py", {"hook_event_name": "SessionStart", "cwd": project}, data)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            context = output["hookSpecificOutput"]["additionalContext"]
            self.assertIn("django-multitenant-production", context)
            self.assertIn("migrate_schemas", context)
            self.assertEqual(len(baseline_files(data)), 1)
            baseline = json.loads(baseline_files(data)[0].read_text(encoding="utf-8"))
            self.assertEqual(baseline["facts"]["tenancy_mode"], "schema-per-tenant")

    def test_ordinary_project_stays_silent(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as data:
            write_fixture(Path(project), "app/views.py", "def index(request):\n    return None\n")
            result = run_hook("session_start_tenancy.py", {"cwd": project}, data)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "")
            self.assertEqual(baseline_files(data), [])

    def test_never_crashes_on_garbage_stdin(self):
        with tempfile.TemporaryDirectory() as data:
            env = dict(os.environ)
            env["CLAUDE_PLUGIN_DATA"] = data
            result = subprocess.run(
                [sys.executable, str(HOOKS_DIR / "session_start_tenancy.py")],
                input="not json at all {",
                capture_output=True, text=True, env=env, timeout=60,
            )
            self.assertEqual(result.returncode, 0)


class AuditOnEditHookTests(unittest.TestCase):
    def test_new_high_finding_is_reported_once(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as data:
            root = Path(project)
            build_django_tenants_fixture(root)
            run_hook("session_start_tenancy.py", {"cwd": project}, data)
            self.assertEqual(len(baseline_files(data)), 1)

            # Introduce a regression the audit flags High even in schema mode:
            # a Celery task touching the ORM with no tenant context.
            bad = write_fixture(root, "shop/tasks.py", """\
                from celery import shared_task

                from .models import Product


                @shared_task
                def refresh(product_id):
                    return Product.objects.get(pk=product_id).name
            """)
            payload = {"tool_name": "Edit", "tool_input": {"file_path": str(bad)}, "cwd": project}
            first = run_hook("audit_on_edit.py", payload, data)
            self.assertEqual(first.returncode, 0, first.stderr)
            context = json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("ASYNC-NO-TENANT-CONTEXT", context)

            # Baseline was refreshed: the same finding must not be re-reported.
            second = run_hook("audit_on_edit.py", payload, data)
            self.assertEqual(second.stdout.strip(), "", "finding must be reported exactly once")

    def test_silent_without_baseline_marker(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as data:
            root = Path(project)
            bad = write_fixture(root, "app/views.py", "from .models import X\n\ndef v(request, pk):\n    return X.objects.get(pk=pk)\n")
            result = run_hook("audit_on_edit.py", {"tool_input": {"file_path": str(bad)}, "cwd": project}, data)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")

    def test_unreported_findings_in_other_files_are_not_absorbed(self):
        # A finding introduced outside the Edit/Write hooks (e.g. a file created via
        # Bash) must still be reported the first time ITS file is edited — an edit to
        # an unrelated file in between must not silently absorb it into the baseline.
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as data:
            root = Path(project)
            build_django_tenants_fixture(root)
            run_hook("session_start_tenancy.py", {"cwd": project}, data)

            bad = write_fixture(root, "shop/tasks.py", """\
                from celery import shared_task

                from .models import Product


                @shared_task
                def refresh(product_id):
                    return Product.objects.get(pk=product_id).name
            """)
            unrelated = write_fixture(root, "shop/other.py", "VALUE = 1\n")

            first = run_hook(
                "audit_on_edit.py",
                {"tool_input": {"file_path": str(unrelated)}, "cwd": project},
                data,
            )
            self.assertEqual(first.stdout.strip(), "", "unrelated edit must not report tasks.py")

            second = run_hook(
                "audit_on_edit.py",
                {"tool_input": {"file_path": str(bad)}, "cwd": project},
                data,
            )
            self.assertTrue(second.stdout.strip(), "the finding must still be reported for its own file")
            context = json.loads(second.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("ASYNC-NO-TENANT-CONTEXT", context)

    def test_silent_for_non_python_files(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as data:
            result = run_hook("audit_on_edit.py", {"tool_input": {"file_path": f"{project}/notes.md"}, "cwd": project}, data)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "")


class GuardMigrateHookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The fixture and baseline are read-only for every test here: provision once.
        cls._project = tempfile.TemporaryDirectory()
        cls._data = tempfile.TemporaryDirectory()
        build_django_tenants_fixture(Path(cls._project.name))
        run_hook("session_start_tenancy.py", {"cwd": cls._project.name}, cls._data.name)

    @classmethod
    def tearDownClass(cls):
        cls._project.cleanup()
        cls._data.cleanup()

    def guard(self, command: str) -> subprocess.CompletedProcess:
        payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": self._project.name}
        return run_hook("guard_migrate.py", payload, self._data.name)

    def test_bare_migrate_asks(self):
        result = self.guard("python manage.py migrate")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "ask")
        self.assertIn("migrate_schemas", output["permissionDecisionReason"])

    def test_migrate_schemas_is_allowed_silently(self):
        result = self.guard("python manage.py migrate_schemas --shared")
        self.assertEqual(result.stdout.strip(), "")

    def test_unrelated_commands_are_silent(self):
        result = self.guard("python manage.py makemigrations")
        self.assertEqual(result.stdout.strip(), "")

    def test_silent_without_marker(self):
        with tempfile.TemporaryDirectory() as other_project, tempfile.TemporaryDirectory() as other_data:
            payload = {"tool_name": "Bash", "tool_input": {"command": "python manage.py migrate"}, "cwd": other_project}
            result = run_hook("guard_migrate.py", payload, other_data)
            self.assertEqual(result.stdout.strip(), "")
