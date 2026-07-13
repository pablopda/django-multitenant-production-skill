"""Behavioral tests for scripts/tenant_static_audit.py.

Two synthetic fixture projects are built per test run:

- a shared-schema project seeded with the classic isolation bugs the skill's
  code-review heuristics call out (each seeded bug must be caught), plus one
  correctly-scoped file (which must NOT produce High/Critical noise);
- a django-tenants project with settings mistakes (router missing, middleware
  order, fail-open public fallback).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.util import SCRIPTS_DIR, load_script, write_fixture

audit = load_script("tenant_static_audit")

AUDIT_SCRIPT = SCRIPTS_DIR / "tenant_static_audit.py"


def build_shared_schema_fixture(root: Path) -> None:
    write_fixture(root, "requirements.txt", """\
        Django==5.2.3
        djangorestframework==3.16.0
        celery==5.5.0
    """)
    # Tenant-owned model with a global unique and a global upload path.
    write_fixture(root, "app/models.py", """\
        from django.db import models


        class Invoice(models.Model):
            tenant = models.ForeignKey("accounts.Tenant", on_delete=models.CASCADE)
            number = models.CharField(max_length=32, unique=True)
            contract = models.FileField(upload_to="contracts/")
    """)
    # High-risk view file: unscoped get, unscoped get_object_or_404, raw SQL.
    # Deliberately free of vocabulary words near the calls so heuristics must fire.
    write_fixture(root, "app/views.py", """\
        from django.db import connection
        from django.shortcuts import get_object_or_404

        from .models import Invoice


        def invoice_detail(request, pk):
            invoice = Invoice.objects.get(pk=pk)
            return invoice


        def invoice_lookup(request, pk):
            invoice = get_object_or_404(Invoice, pk=pk)
            return invoice


        def raw_report(request):
            cursor = connection.cursor()
            cursor.execute("SELECT id FROM app_invoice")
            return cursor.fetchall()
    """)
    # DRF viewset with a class-level global queryset.
    write_fixture(root, "app/api.py", """\
        from rest_framework.viewsets import ModelViewSet

        from .models import Invoice
        from .serializers import InvoiceSerializer


        class InvoiceViewSet(ModelViewSet):
            serializer_class = InvoiceSerializer
            queryset = Invoice.objects.all()
    """)
    # Celery task with only an object id and a static cache key.
    write_fixture(root, "app/tasks.py", """\
        from celery import shared_task
        from django.core.cache import cache

        from .models import Invoice


        @shared_task
        def send_invoice(invoice_id):
            invoice = Invoice.objects.get(pk=invoice_id)
            cache.set("dashboard_stats", invoice.number)
            return invoice.pk
    """)
    # Management command touching the ORM with no tenant context.
    write_fixture(root, "app/management/commands/report.py", """\
        from django.core.management.base import BaseCommand

        from app.models import Invoice


        class Command(BaseCommand):
            def handle(self, *args, **options):
                for invoice in Invoice.objects.all():
                    self.stdout.write(str(invoice.pk))
    """)
    # Client-controlled tenant id flowing into a query.
    write_fixture(root, "app/exports.py", """\
        from .models import Invoice


        def export_invoices(request):
            return list(Invoice.objects.filter(tenant_id=request.GET.get("t")))
    """)
    # Correctly scoped view: must not be flagged High/Critical.
    write_fixture(root, "app/safe_views.py", """\
        from django.shortcuts import get_object_or_404

        from .models import Invoice


        def invoice_detail(request, pk):
            queryset = Invoice.objects.filter(tenant=request.tenant)
            return get_object_or_404(queryset, pk=pk)
    """)


def build_django_tenants_fixture(root: Path) -> None:
    write_fixture(root, "requirements.txt", """\
        Django==5.2.3
        django-tenants==3.10.1
    """)
    # Settings with: no DATABASE_ROUTERS, tenant middleware third, fail-open fallback.
    write_fixture(root, "config/settings.py", """\
        INSTALLED_APPS = ["django_tenants", "customers"]

        DATABASES = {
            "default": {"ENGINE": "django_tenants.postgresql_backend"},
        }

        MIDDLEWARE = [
            "django.middleware.security.SecurityMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django_tenants.middleware.main.TenantMainMiddleware",
        ]

        SHARED_APPS = ["django_tenants", "customers"]
        TENANT_APPS = ["app"]
        TENANT_MODEL = "customers.Client"
        TENANT_DOMAIN_MODEL = "customers.Domain"
        ROOT_URLCONF = "config.urls"
        WSGI_APPLICATION = "config.wsgi.application"
        SHOW_PUBLIC_IF_NO_TENANT_FOUND = True
    """)
    write_fixture(root, "tests/test_isolation.py", """\
        from django_tenants.test.cases import TenantTestCase


        class IsolationTests(TenantTestCase):
            def test_schema_set(self):
                assert self.tenant.schema_name
    """)


class SharedSchemaFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        build_shared_schema_fixture(cls.root)
        cls.facts, cls.findings = audit.audit_project(cls.root)
        cls.rules = {f.rule for f in cls.findings}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def rules_for(self, filename: str) -> set:
        return {f.rule for f in self.findings if f.path.endswith(filename)}

    def test_seeded_bugs_are_all_detected(self):
        expected = {
            "ORM-UNSCOPED-HIGH-RISK",          # views.py Invoice.objects.get(pk=pk)
            "GET-OBJECT-OR-404-UNSCOPED",      # views.py get_object_or_404(Invoice, pk=pk)
            "RAW-SQL",                          # views.py cursor.execute
            "DRF-QUERYSET-ASSIGNMENT",          # api.py queryset = Invoice.objects.all()
            "ASYNC-NO-TENANT-CONTEXT",          # tasks.py shared_task without context
            "CACHE-GLOBAL-KEY",                 # tasks.py cache.set("dashboard_stats", ...)
            "COMMAND-NO-TENANT-CONTEXT",        # management command
            "FILE-UPLOAD-GLOBAL-PATH",          # models.py upload_to="contracts/"
            "SHARED-GLOBAL-UNIQUE",             # models.py unique=True on tenant-owned model
            "REQUEST-SOURCED-TENANT-ID",        # exports.py tenant_id=request.GET.get(...)
            "TESTS-NOT-DETECTED",               # no test files at all
        }
        missing = expected - self.rules
        self.assertFalse(missing, f"seeded bugs not detected: {sorted(missing)}")

    def test_safe_file_has_no_high_findings(self):
        noisy = [
            f for f in self.findings
            if f.path.endswith("safe_views.py") and f.severity in {"Critical", "High"}
        ]
        self.assertFalse(noisy, f"false positives on correctly scoped code: {noisy}")

    def test_facts_reflect_fixture(self):
        self.assertEqual(self.facts.test_files_scanned, 0)
        self.assertGreaterEqual(self.facts.python_files_scanned, 6)
        self.assertTrue(self.facts.detected_stack)


class DjangoTenantsFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        build_django_tenants_fixture(cls.root)
        cls.facts, cls.findings = audit.audit_project(cls.root)
        cls.rules = {f.rule for f in cls.findings}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_detects_django_tenants_stack_and_settings(self):
        self.assertTrue(any("django-tenants" in s for s in self.facts.detected_stack))
        self.assertIn("config/settings.py", self.facts.settings_files)

    def test_missing_router_is_flagged(self):
        router_findings = [
            f for f in self.findings
            if f.rule == "DT-SETTINGS-MISSING" and "router" in f.message.lower()
        ]
        self.assertTrue(router_findings, "missing TenantSyncRouter must be flagged")

    def test_middleware_order_is_flagged(self):
        self.assertIn("DT-MIDDLEWARE-ORDER", self.rules)

    def test_public_fallback_is_flagged(self):
        self.assertIn("DT-PUBLIC-FALLBACK", self.rules)


class UnitTests(unittest.TestCase):
    def test_parse_requirements_line(self):
        self.assertEqual(audit.parse_requirements_line("Django==5.2.3"), ("django", "==5.2.3"))
        self.assertEqual(
            audit.parse_requirements_line("django-tenants[psycopg]>=3.10"),
            ("django-tenants", ">=3.10"),
        )
        self.assertIsNone(audit.parse_requirements_line("# comment"))
        self.assertIsNone(audit.parse_requirements_line("-r base.txt"))
        self.assertIsNone(audit.parse_requirements_line(""))

    def test_detect_stack_ignores_celery_integration_package(self):
        # tenant_schemas_celery is the *recommended* integration; it must not
        # trigger the legacy django-tenant-schemas detection.
        stack = audit.detect_stack({}, "import tenant_schemas_celery")
        self.assertFalse(any("legacy" in s for s in stack))
        stack = audit.detect_stack({}, "from tenant_schemas.utils import x")
        self.assertTrue(any("legacy" in s for s in stack))

    def test_infer_tenant_terms_from_tenant_model_setting(self):
        terms = audit.infer_tenant_terms(
            'TENANT_MODEL = "customers.Client"', audit.DEFAULT_TENANT_TERMS
        )
        self.assertIn("client", terms)

    def test_build_vocab_falls_back_to_defaults(self):
        vocab = audit.build_vocab([])
        self.assertEqual(vocab.terms, audit.DEFAULT_TENANT_TERMS)

    def test_severity_order_is_total(self):
        self.assertEqual(
            sorted(audit.SEVERITY_ORDER, key=audit.SEVERITY_ORDER.get, reverse=True),
            ["Critical", "High", "Medium", "Low", "Info"],
        )


class CliTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(AUDIT_SCRIPT), *argv],
            capture_output=True,
            text=True,
        )

    def test_json_output_parses_and_fail_on_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_shared_schema_fixture(root)
            result = self.run_cli("--root", str(root), "--format", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("facts", payload)
            self.assertIn("findings", payload)
            self.assertTrue(payload["findings"])

            gated = self.run_cli("--root", str(root), "--fail-on", "High")
            self.assertEqual(gated.returncode, 1, "High findings must gate with exit code 1")

    def test_empty_directory_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_cli("--root", tmp, "--fail-on", "Info")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_root_errors(self):
        result = self.run_cli("--root", "/nonexistent/definitely-not-here")
        self.assertEqual(result.returncode, 2)

    def test_syntax_error_file_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "app/broken.py", "def broken(:\n")
            result = self.run_cli("--root", str(root), "--format", "json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(
                any(f["rule"] == "PY-SYNTAX-SKIP" for f in payload["findings"]),
                "unparseable files must be reported, not crash the audit",
            )
