"""Regression tests for defects found in the v1.1.0 audit script by hands-on QA and
code review: crash paths, false positives/negatives, and heuristics that ignored the
detected tenancy model."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.test_static_audit import build_django_tenants_fixture, build_shared_schema_fixture
from tests.util import load_script, write_fixture

audit = load_script("tenant_static_audit")


def rules_at(findings, filename):
    return {f.rule for f in findings if f.path.endswith(filename)}


class SchemaModeHeuristicsTests(unittest.TestCase):
    """SKILL.md: in schema-per-tenant projects, bare ORM calls in request-path code are
    idiomatic and must NOT be flagged; outside-request code keeps the strict rules."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        build_django_tenants_fixture(cls.root)
        # Idiomatic in-request django-tenants code: middleware set the search_path.
        write_fixture(cls.root, "shop/views.py", """\
            from django.shortcuts import get_object_or_404

            from .models import Product


            def product_list(request):
                return list(Product.objects.filter(price__gt=0))


            def product_detail(request, pk):
                return get_object_or_404(Product, pk=pk)
        """)
        cls.facts, cls.findings = audit.audit_project(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_idiomatic_request_orm_is_not_flagged_in_schema_mode(self):
        self.assertEqual(self.facts.tenancy_mode, "schema-per-tenant")
        noisy = rules_at(self.findings, "shop/views.py") & {
            "GET-OBJECT-OR-404-UNSCOPED",
            "ORM-UNSCOPED-HIGH-RISK",
            "ORM-FILTER-NO-TENANT-HINT",
            "DRF-GLOBAL-QUERYSET",
            "DRF-QUERYSET-ASSIGNMENT",
        }
        self.assertFalse(noisy, f"idiomatic django-tenants view code flagged: {noisy}")

    def test_tenancy_flag_overrides_detection(self):
        _, findings = audit.audit_project(self.root, tenancy="shared")
        self.assertIn("GET-OBJECT-OR-404-UNSCOPED", rules_at(findings, "shop/views.py"))


class CrashRobustnessTests(unittest.TestCase):
    def test_dangling_symlink_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "app/ok.py", "x = 1\n")
            os.symlink("/nonexistent/target.py", root / "app" / "dangling.py")
            facts, findings = audit.audit_project(root)  # must not raise
            self.assertGreaterEqual(facts.python_files_scanned, 1)

    def test_nul_bytes_degrade_to_syntax_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "weird.py").write_bytes("x = 1\n".encode("utf-16"))
            _, findings = audit.audit_project(root)  # must not raise
            self.assertIn("PY-SYNTAX-SKIP", {f.rule for f in findings})

    def test_utf8_bom_files_are_still_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "views.py").write_bytes(
                b"\xef\xbb\xbf" + b"from .models import Invoice\n\n\ndef v(request, pk):\n    return Invoice.objects.get(pk=pk)\n"
            )
            _, findings = audit.audit_project(root)
            rules = {f.rule for f in findings}
            self.assertNotIn("PY-SYNTAX-SKIP", rules, "BOM must be stripped, not kill AST checks")
            self.assertIn("ORM-UNSCOPED-HIGH-RISK", rules)


class SettingsTests(unittest.TestCase):
    def test_split_settings_are_aggregated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "requirements.txt", "django-tenants==3.10.2\n")
            write_fixture(root, "config/settings/base.py", """\
                INSTALLED_APPS = ["django_tenants", "customers"]
                DATABASE_ROUTERS = ("django_tenants.routers.TenantSyncRouter",)
                MIDDLEWARE = [
                    "django_tenants.middleware.main.TenantMainMiddleware",
                    "django.middleware.security.SecurityMiddleware",
                ]
                SHARED_APPS = ["django_tenants", "customers"]
                TENANT_APPS = ["app"]
                TENANT_MODEL = "customers.Client"
                TENANT_DOMAIN_MODEL = "customers.Domain"
                ROOT_URLCONF = "config.urls"
            """)
            write_fixture(root, "config/settings/production.py", """\
                from .base import *  # noqa

                DATABASES = {"default": {"ENGINE": "django_tenants.postgresql_backend"}}
            """)
            write_fixture(root, "tests/test_isolation.py", "from django_tenants.test.cases import TenantTestCase\n")
            _, findings = audit.audit_project(root)
            missing = [f for f in findings if f.rule == "DT-SETTINGS-MISSING"]
            self.assertFalse(missing, f"split settings produced false missing-settings findings: {missing}")

    def test_middleware_order_check_survives_paren_in_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "config/settings.py", """\
                INSTALLED_APPS = ["django_tenants"]
                DATABASES = {"default": {"ENGINE": "django_tenants.postgresql_backend"}}
                MIDDLEWARE = [
                    "django.middleware.security.SecurityMiddleware",
                    "whitenoise.middleware.WhiteNoiseMiddleware",  # static files (prod)
                    "django_tenants.middleware.main.TenantMainMiddleware",
                ]
            """)
            _, findings = audit.audit_project(root)
            self.assertIn(
                "DT-MIDDLEWARE-ORDER",
                {f.rule for f in findings},
                "a ')' inside a comment must not disable the order check",
            )


class DetectionTests(unittest.TestCase):
    def test_app_tests_py_counts_as_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "app/models.py", """\
                from django.db import models


                class Invoice(models.Model):
                    tenant = models.ForeignKey("accounts.Tenant", on_delete=models.CASCADE)
            """)
            write_fixture(root, "app/tests.py", """\
                def test_isolation(tenant_a, tenant_b):
                    assert tenant_a != tenant_b
            """)
            facts, findings = audit.audit_project(root)
            self.assertEqual(facts.test_files_scanned, 1)
            rules = {f.rule for f in findings}
            self.assertNotIn("TESTS-NOT-DETECTED", rules)
            self.assertNotIn("TENANT-TESTS-NOT-DETECTED", rules)

    def test_custom_tenant_term_recognized_in_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "requirements.txt", "django-multitenant==4.1.1\n")
            write_fixture(root, "app/models.py", """\
                from django.db import models


                class Project(models.Model):
                    workspace = models.ForeignKey("core.Workspace", on_delete=models.CASCADE)
            """)
            write_fixture(root, "tests/test_isolation.py", """\
                def test_cross_workspace_denied(workspace_a, workspace_b):
                    assert workspace_a != workspace_b
            """)
            facts, findings = audit.audit_project(root, tenant_terms=["workspace"])
            self.assertTrue(facts.tenant_terms_in_tests)
            self.assertNotIn("TENANT-TESTS-NOT-DETECTED", {f.rule for f in findings})

    def test_pipfile_and_requirements_dir_are_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "Pipfile", '[packages]\ndjango-tenants = "*"\n')
            packages = audit.collect_package_facts(root)
            self.assertIn("django-tenants", packages)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, "requirements/production.txt", "django-tenant-schemas==1.12.0\n")
            packages = audit.collect_package_facts(root)
            self.assertEqual(packages.get("django-tenant-schemas"), "==1.12.0")
            _, findings = audit.audit_project(root)
            self.assertIn("LEGACY-TENANT-SCHEMAS", {f.rule for f in findings})

    def test_high_risk_matching_uses_boundaries(self):
        root = Path("/repo")
        self.assertFalse(audit.is_high_risk_file(Path("/repo/app/therapist.py"), root))
        self.assertTrue(audit.is_high_risk_file(Path("/repo/app/views/detail.py"), root))
        self.assertTrue(audit.is_high_risk_file(Path("/repo/app/invoice_views.py"), root))
        self.assertTrue(audit.is_high_risk_file(Path("/repo/app/signals.py"), root))


class SeverityAndPrecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp.name)
        build_shared_schema_fixture(cls.root)
        _, cls.findings = audit.audit_project(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def severity_of(self, rule):
        return {f.severity for f in self.findings if f.rule == rule}

    def test_severities_match_skill_severity_model(self):
        # SKILL.md: client-controlled tenant id => tenant impersonation => Critical;
        # shared cache/file keys => High.
        self.assertEqual(self.severity_of("REQUEST-SOURCED-TENANT-ID"), {"Critical"})
        self.assertEqual(self.severity_of("CACHE-GLOBAL-KEY"), {"High"})
        self.assertEqual(self.severity_of("FILE-UPLOAD-GLOBAL-PATH"), {"High"})

    def test_drf_queryset_line_produces_single_finding(self):
        api_findings = [
            f for f in self.findings
            if f.path.endswith("api.py") and f.rule in {
                "DRF-QUERYSET-ASSIGNMENT", "DRF-GLOBAL-QUERYSET",
                "ORM-UNSCOPED-HIGH-RISK", "ORM-FILTER-NO-TENANT-HINT",
            }
        ]
        self.assertEqual(len(api_findings), 1, f"expected one deduped finding, got: {api_findings}")
        self.assertEqual(api_findings[0].rule, "DRF-QUERYSET-ASSIGNMENT")


class ClientSourcedPrecisionTests(unittest.TestCase):
    def audit_file(self, rel, content):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fixture(root, rel, content)
            _, findings = audit.audit_project(root)
            return {f.rule for f in findings if f.path.endswith(Path(rel).name)}

    def test_request_get_host_is_not_client_sourced(self):
        rules = self.audit_file("app/host_views.py", """\
            from .models import TenantModel


            def resolve(request):
                return TenantModel.objects.get(schema_name=request.get_host().split(".")[0])
        """)
        self.assertNotIn("REQUEST-SOURCED-TENANT-ID", rules)

    def test_task_kwargs_are_not_client_sourced(self):
        rules = self.audit_file("app/billing_tasks.py", """\
            from celery import shared_task

            from .models import Item


            @shared_task
            def process(**kwargs):
                return list(Item.objects.filter(tenant_id=kwargs["tenant_id"]))
        """)
        self.assertNotIn("REQUEST-SOURCED-TENANT-ID", rules)

    def test_view_kwargs_are_client_sourced(self):
        rules = self.audit_file("app/kw_views.py", """\
            from .models import Invoice


            def export(request, **kwargs):
                return list(Invoice.objects.filter(tenant_id=kwargs["tenant_id"]))
        """)
        self.assertIn("REQUEST-SOURCED-TENANT-ID", rules)

    def test_word_boundary_hints_do_not_suppress_findings(self):
        # 'forgot' contains 'org'; with substring matching it suppressed ORM findings.
        rules = self.audit_file("app/report_views.py", """\
            from .models import Invoice


            def report(request):
                send_forgot_password_email(request.user)
                return list(Invoice.objects.filter(status="open"))
        """)
        self.assertIn("ORM-FILTER-NO-TENANT-HINT", rules)

    def test_annotated_queryset_assignment_is_flagged(self):
        rules = self.audit_file("app/typed_api.py", """\
            from rest_framework.viewsets import ModelViewSet

            from .models import Invoice


            class InvoiceViewSet(ModelViewSet):
                queryset: "QuerySet" = Invoice.objects.all()
        """)
        self.assertIn("DRF-QUERYSET-ASSIGNMENT", rules)

    def test_unhinted_task_file_is_still_checked(self):
        # services/sync.py has no high-risk filename hint; the @shared_task marker alone
        # must trigger the async check.
        rules = self.audit_file("services/sync.py", """\
            from celery import shared_task

            from app.models import Invoice


            @shared_task
            def sync_invoices():
                Invoice.objects.filter(status="pending").update(synced=True)
        """)
        self.assertIn("ASYNC-NO-TENANT-CONTEXT", rules)
