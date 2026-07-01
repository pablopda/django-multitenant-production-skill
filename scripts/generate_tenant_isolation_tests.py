#!/usr/bin/env python3
"""Generate starter tenant-isolation test templates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

SCHEMA_TEMPLATE = '''\
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
        response = self.client_a.get(reverse("TODO-list-url-name"))
        assert response.status_code == 200
        assert "TODO-other-tenant-marker" not in response.content.decode()

    def test_retrieve_other_tenant_object_denied(self):
        # TODO: request tenant B object ID from tenant A client and assert 403 or 404.
        pass

    def test_background_task_uses_tenant_context(self):
        # TODO: call task with tenant A and assert tenant B data unchanged.
        pass
'''

SHARED_TEMPLATE = '''\
"""
Starter tests for shared-schema Django apps using tenant_id/organization/workspace scoping.
Adapt fixtures, client tenant helper, URLs, and model imports before committing.
"""

import pytest

# from app.models import Project


@pytest.mark.django_db
def test_list_endpoint_excludes_other_tenant_data(api_client, tenant_a, tenant_b, user_a, project_a, project_b):
    api_client.force_authenticate(user_a)
    # TODO: set tenant context for tenant_a.
    response = api_client.get("/api/TODO/")
    assert response.status_code == 200
    body = response.json()
    assert str(project_a.id) in str(body)
    assert str(project_b.id) not in str(body)


@pytest.mark.django_db
def test_retrieve_other_tenant_object_is_denied(api_client, tenant_a, tenant_b, user_a, project_b):
    api_client.force_authenticate(user_a)
    # TODO: set tenant context for tenant_a.
    response = api_client.get(f"/api/TODO/{project_b.id}/")
    assert response.status_code in {403, 404}


@pytest.mark.django_db
def test_create_ignores_or_rejects_posted_tenant_id(api_client, tenant_a, tenant_b, user_a):
    api_client.force_authenticate(user_a)
    # TODO: set tenant context for tenant_a.
    response = api_client.post("/api/TODO/", {"name": "x", "tenant": tenant_b.id}, format="json")
    assert response.status_code in {201, 400, 403}
    if response.status_code == 201:
        created_id = response.json()["id"]
        # created = Project.objects.get(pk=created_id)
        # assert created.tenant_id == tenant_a.id
'''


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate starter tenant-isolation test template.")
    parser.add_argument("--root", default=".", help="Project root. Default: current directory.")
    parser.add_argument("--mode", choices={"schema", "shared"}, required=True, help="Tenancy model test template.")
    parser.add_argument("--output", default="tests/test_tenant_isolation.py", help="Output file path relative to root.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing file.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    output = root / args.output
    if output.exists() and not args.force:
        print(f"error: output exists; use --force to overwrite: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(SCHEMA_TEMPLATE if args.mode == "schema" else SHARED_TEMPLATE, encoding="utf-8")
    print(f"wrote: {output}")
    print("Review TODOs, wire real fixtures/URLs/models, then add the test to CI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
