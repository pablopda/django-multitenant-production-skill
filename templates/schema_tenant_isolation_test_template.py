"""
Starter tests for schema-per-tenant Django apps using django-tenants.
Adapt model imports, URLs, and factories before committing.
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
        # TODO: create tenant_b and seed data with tenant_context(tenant_b)

    def test_list_endpoint_does_not_include_other_tenant_data(self):
        # TODO: create data in tenant A and tenant B, then assert tenant A response excludes tenant B data.
        response = self.client_a.get(reverse("TODO-list-url-name"))
        assert response.status_code == 200
        assert "TODO-other-tenant-marker" not in response.content.decode()

    def test_retrieve_other_tenant_object_denied(self):
        # TODO: request tenant B object ID from tenant A client and assert 403 or 404.
        pass

    def test_background_task_uses_tenant_context(self):
        # TODO: call task with tenant A and assert tenant B data unchanged.
        pass
