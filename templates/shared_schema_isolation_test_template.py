"""
Starter tests for shared-schema Django apps using tenant_id/organization/workspace scoping.
Adapt fixtures, client tenant helper, URLs, and model imports before committing.
"""

import pytest

# from app.models import Project


@pytest.mark.django_db
def test_list_endpoint_excludes_other_tenant_data(api_client, tenant_a, tenant_b, user_a, project_a, project_b):
    api_client.force_authenticate(user_a)
    # TODO: set tenant context for tenant_a. Example: api_client.headers["Host"] = tenant_a domain
    response = api_client.get("/api/TODO/")
    assert response.status_code == 200
    body = response.json()
    assert str(project_a.id) in str(body)
    assert str(project_b.id) not in str(body)


@pytest.mark.django_db
def test_retrieve_other_tenant_object_is_denied(api_client, tenant_a, tenant_b, user_a, project_b):
    api_client.force_authenticate(user_a)
    # TODO: set tenant context for tenant_a
    response = api_client.get(f"/api/TODO/{project_b.id}/")
    assert response.status_code in {403, 404}


@pytest.mark.django_db
def test_create_ignores_or_rejects_posted_tenant_id(api_client, tenant_a, tenant_b, user_a):
    api_client.force_authenticate(user_a)
    # TODO: set tenant context for tenant_a
    response = api_client.post("/api/TODO/", {"name": "x", "tenant": tenant_b.id}, format="json")
    assert response.status_code in {201, 400, 403}
    if response.status_code == 201:
        created_id = response.json()["id"]
        # created = Project.objects.get(pk=created_id)
        # assert created.tenant_id == tenant_a.id
