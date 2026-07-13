"""Behavioral tests for scripts/scaffold_django_tenants_app.py."""

from __future__ import annotations

import contextlib
import io
import py_compile
import tempfile
import unittest
from pathlib import Path

from tests.util import load_script

scaffold = load_script("scaffold_django_tenants_app")

EXPECTED_FILES = (
    "__init__.py",
    "apps.py",
    "models.py",
    "admin.py",
    "migrations/__init__.py",
    "management/__init__.py",
    "management/commands/__init__.py",
    "management/commands/provision_tenant.py",
    "tests/__init__.py",
    "tests/test_tenant_smoke.py",
    "settings_django_tenants_snippet.py",
)


def run_main(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = scaffold.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


class ScaffoldTests(unittest.TestCase):
    def test_default_scaffold_compiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_main(
                "--root", tmp, "--app", "customers",
                "--tenant-model", "Client", "--domain-model", "Domain",
            )
            self.assertEqual(code, 0, err)
            app_dir = Path(tmp) / "customers"
            for rel in EXPECTED_FILES:
                path = app_dir / rel
                self.assertTrue(path.exists(), f"missing scaffold file: {rel}")
                if path.suffix == ".py":
                    py_compile.compile(str(path), doraise=True)

            snippet = (app_dir / "settings_django_tenants_snippet.py").read_text(encoding="utf-8")
            self.assertIn('TENANT_MODEL = "customers.Client"', snippet)
            self.assertIn('TENANT_DOMAIN_MODEL = "customers.Domain"', snippet)

    def test_dotted_app_path_uses_last_segment_as_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_main("--root", tmp, "--app", "platform.tenants")
            self.assertEqual(code, 0, err)
            app_dir = Path(tmp) / "platform" / "tenants"
            self.assertTrue((app_dir / "models.py").exists())
            snippet = (app_dir / "settings_django_tenants_snippet.py").read_text(encoding="utf-8")
            # Django app labels come from the last dotted segment only.
            self.assertIn('TENANT_MODEL = "tenants.Client"', snippet)
            self.assertNotIn('TENANT_MODEL = "platform.tenants', snippet)
            apps_py = (app_dir / "apps.py").read_text(encoding="utf-8")
            self.assertIn('name = "platform.tenants"', apps_py)

    def test_existing_files_are_skipped_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_main("--root", tmp, "--app", "customers")
            models = Path(tmp) / "customers" / "models.py"
            models.write_text("# sentinel\n", encoding="utf-8")

            code, out, _ = run_main("--root", tmp, "--app", "customers")
            self.assertEqual(code, 0)
            self.assertIn("skip existing", out)
            self.assertEqual(models.read_text(encoding="utf-8"), "# sentinel\n")

            code, out, _ = run_main("--root", tmp, "--app", "customers", "--force")
            self.assertEqual(code, 0)
            self.assertNotEqual(models.read_text(encoding="utf-8"), "# sentinel\n")

    def test_invalid_identifiers_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for argv in (
                ("--root", tmp, "--app", "9bad"),
                ("--root", tmp, "--app", "ok", "--tenant-model", "Bad-Name"),
                ("--root", tmp, "--app", "ok", "--domain-model", "also bad"),
                # Python keywords pass an identifier regex but generate unparseable code.
                ("--root", tmp, "--app", "ok", "--tenant-model", "class"),
                ("--root", tmp, "--app", "global.tenants"),
                ("--root", tmp, "--app", "ok", "--domain-model", "True"),
            ):
                code, _, err = run_main(*argv)
                self.assertEqual(code, 2, f"should reject {argv}: {err}")

    def test_identical_tenant_and_domain_models_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_main(
                "--root", tmp, "--app", "customers",
                "--tenant-model", "Domain", "--domain-model", "Domain",
            )
            self.assertEqual(code, 2)
            self.assertIn("different", err)

    def test_dotted_app_creates_regular_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_main("--root", tmp, "--app", "apps.tenants")
            self.assertEqual(code, 0, err)
            self.assertTrue((Path(tmp) / "apps" / "__init__.py").exists(),
                            "intermediate dirs must be regular packages, not namespace packages")

    def test_rerun_prints_skip_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_main("--root", tmp, "--app", "customers")
            code, out, _ = run_main("--root", tmp, "--app", "customers")
            self.assertEqual(code, 0)
            self.assertIn("skipped", out)
            self.assertIn("--force", out)

    def test_provision_command_validates_schema_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_main("--root", tmp, "--app", "customers")
            command = (
                Path(tmp) / "customers" / "management" / "commands" / "provision_tenant.py"
            ).read_text(encoding="utf-8")
            self.assertIn("pg_", command, "must guard against pg_-prefixed schema names")
            self.assertIn("CommandError", command)
            # The comment explaining WHY there is no transaction may mention the
            # decorator; an actual decorator line must not exist.
            self.assertNotRegex(command, r"(?m)^\s*@transaction\.atomic",
                                "schema creation must not be wrapped in an outer transaction")
