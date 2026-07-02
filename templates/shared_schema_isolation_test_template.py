"""
Starter tests for shared-schema Django apps using tenant_id/organization/workspace scoping.
Adapt fixtures, client tenant helper, URLs, and model imports before committing.

Every test below fails on purpose until you implement it, so an unfinished
isolation test can never be mistaken for a passing one. Replace each
pytest.fail(...) guard with real assertions.
"""

import pytest

# from app.models import Project


@pytest.mark.django_db
def test_list_endpoint_excludes_other_tenant_data(api_client, tenant_a, tenant_b, user_a, project_a, project_b):
    pytest.fail("TODO: wire real fixtures/URLs, then delete this line.")
    api_client.force_authenticate(user_a)
    # Route the request to tenant A. For domain-resolved tenants (django-tenants):
    api_client.defaults["HTTP_HOST"] = tenant_a.get_primary_domain().domain
    response = api_client.get("/api/TODO/")
    assert response.status_code == 200
    body = response.json()
    # Compare id sets, not substrings: `str(project_b.id) not in str(body)` is both
    # flaky (small ids appear inside timestamps) and vacuously passable. Use body["results"]
    # for a paginated DRF response, or body directly if the endpoint is unpaginated.
    ids = {item["id"] for item in body["results"]}
    assert project_a.id in ids
    assert project_b.id not in ids


@pytest.mark.django_db
def test_retrieve_other_tenant_object_is_denied(api_client, tenant_a, tenant_b, user_a, project_b):
    pytest.fail("TODO: wire real fixtures/URLs, then delete this line.")
    api_client.force_authenticate(user_a)
    api_client.defaults["HTTP_HOST"] = tenant_a.get_primary_domain().domain
    response = api_client.get(f"/api/TODO/{project_b.id}/")
    assert response.status_code in {403, 404}


@pytest.mark.django_db
def test_create_ignores_or_rejects_posted_tenant_id(api_client, tenant_a, tenant_b, user_a):
    pytest.fail("TODO: wire real fixtures/URLs and import your model, then delete this line.")
    from app.models import Project  # TODO: point at your tenant-owned model

    api_client.force_authenticate(user_a)
    api_client.defaults["HTTP_HOST"] = tenant_a.get_primary_domain().domain
    response = api_client.post("/api/TODO/", {"name": "x", "tenant": tenant_b.id}, format="json")
    assert response.status_code in {201, 400, 403}
    if response.status_code == 201:
        created_id = response.json()["id"]
        created = Project.objects.get(pk=created_id)
        assert created.tenant_id == tenant_a.id
