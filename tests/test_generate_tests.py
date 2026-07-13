"""Behavioral tests for scripts/generate_tenant_isolation_tests.py and templates."""

from __future__ import annotations

import contextlib
import io
import py_compile
import tempfile
import unittest
from pathlib import Path

from tests.util import TEMPLATES_DIR, load_script

generate = load_script("generate_tenant_isolation_tests")


def run_main(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = generate.main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


class GenerateTests(unittest.TestCase):
    def test_both_modes_emit_compilable_failing_tests(self):
        for mode, fail_marker in (("schema", "self.fail("), ("shared", "pytest.fail(")):
            with tempfile.TemporaryDirectory() as tmp:
                code, out, err = run_main("--root", tmp, "--mode", mode)
                self.assertEqual(code, 0, err)
                output = Path(tmp) / "tests" / "test_tenant_isolation.py"
                self.assertTrue(output.exists())
                py_compile.compile(str(output), doraise=True)
                content = output.read_text(encoding="utf-8")
                # Generated tests must fail loudly until implemented: an empty
                # green isolation test is worse than no test.
                self.assertIn(fail_marker, content, f"{mode} template must fail until implemented")

    def test_output_matches_bundled_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_main("--root", tmp, "--mode", "schema")
            output = (Path(tmp) / "tests" / "test_tenant_isolation.py").read_text(encoding="utf-8")
            template = (TEMPLATES_DIR / "schema_tenant_isolation_test_template.py").read_text(encoding="utf-8")
            self.assertEqual(output, template, "generator must copy the single-source-of-truth template")

    def test_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_main("--root", tmp, "--mode", "schema")[0], 0)
            code, _, err = run_main("--root", tmp, "--mode", "shared")
            self.assertEqual(code, 2)
            self.assertIn("--force", err)
            self.assertEqual(run_main("--root", tmp, "--mode", "shared", "--force")[0], 0)

    def test_custom_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_main("--root", tmp, "--mode", "shared", "--output", "app/tests/test_isolation.py")
            self.assertEqual(code, 0, err)
            self.assertTrue((Path(tmp) / "app" / "tests" / "test_isolation.py").exists())


class TemplateTests(unittest.TestCase):
    def test_python_templates_compile(self):
        for name in (
            "schema_tenant_isolation_test_template.py",
            "shared_schema_isolation_test_template.py",
        ):
            py_compile.compile(str(TEMPLATES_DIR / name), doraise=True)

    def test_markdown_templates_have_required_sections(self):
        validation = (TEMPLATES_DIR / "validation-report.md").read_text(encoding="utf-8")
        for section in ("Executive summary", "Detected tenancy model", "Scorecard", "Release decision"):
            self.assertIn(section, validation)
        adr = (TEMPLATES_DIR / "adr-tenancy-decision.md").read_text(encoding="utf-8")
        for section in ("Context", "Decision", "Alternatives considered", "Validation plan", "Consequences"):
            self.assertIn(section, adr)
