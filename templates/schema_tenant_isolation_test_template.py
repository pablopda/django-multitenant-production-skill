"""
Starter tests for schema-per-tenant Django apps using django-tenants.
Adapt model imports, URLs, and factories before committing.

Every test below fails on purpose until you implement it, so an unfinished
isolation test can never be mistaken for a passing one. Replace each
self.fail(...) guard with real assertions.
"""

from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import tenant_context

# from customers.models import Client, Domain
# from app.models import Project


class TenantIsolationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client_a = TenantClient(self.tenant)
        # TODO: create tenant_b and seed data with tenant_context(tenant_b), e.g.:
        #   with tenant_context(self.tenant_b):
        #       Project.objects.create(name="tenant B project")

    def test_list_endpoint_does_not_include_other_tenant_data(self):
        self.fail("TODO: wire real fixtures/URLs/models, then delete this line.")
        # Reference shape once implemented (uncomment `from app.models import Project`
        # and create self.tenant_b in setUp first):
        with tenant_context(self.tenant):
            project_a = Project.objects.create(name="tenant A project")
        with tenant_context(self.tenant_b):
            project_b = Project.objects.create(name="tenant B project")
        response = self.client_a.get(reverse("your-list-url-name"))
        self.assertEqual(response.status_code, 200)
        # Compare id sets, not substrings: substring checks on stringified JSON are
        # both flaky (small ids appear inside timestamps) and vacuously passable.
        ids = {row["id"] for row in response.json()["results"]}
        self.assertIn(project_a.id, ids)
        self.assertNotIn(project_b.id, ids)

    def test_retrieve_other_tenant_object_denied(self):
        self.fail("TODO: request a tenant B object id from the tenant A client and "
                  "assert the response status is 403 or 404 (prefer 404: a 403 on a "
                  "guessed foreign pk confirms the object exists — an existence oracle).")

    def test_update_other_tenant_object_denied(self):
        self.fail("TODO: PATCH a tenant B object id from the tenant A client, assert "
                  "403/404, then re-read tenant B's row in tenant_context(self.tenant_b) "
                  "and assert it is unchanged.")

    def test_delete_other_tenant_object_denied(self):
        self.fail("TODO: DELETE a tenant B object id from the tenant A client, assert "
                  "403/404, then assert the row still exists in tenant B's schema.")

    def test_background_task_uses_tenant_context(self):
        self.fail("TODO: run the background task for tenant A and assert tenant B data "
                  "is unchanged (the task must enter tenant_context, never trust a bare id).")
