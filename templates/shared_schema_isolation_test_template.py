"""
Starter tests for shared-schema Django apps using tenant_id/organization/workspace scoping.
Adapt fixtures, tenant routing, URLs, and model imports before committing.

Until the fixtures below exist, pytest reports fixture-resolution ERRORS; once they are
wired, each test fails on the pytest.fail(...) guard until you implement it. Either way
an unfinished isolation test can never be mistaken for a passing one.

Fixture sketch (move into your conftest.py and adapt):

    import pytest
    from rest_framework.test import APIClient

    @pytest.fixture
    def api_client():
        return APIClient()

    @pytest.fixture
    def tenant_a(db):
        return Tenant.objects.create(name="tenant-a", slug="tenant-a")

    @pytest.fixture
    def tenant_b(db):
        return Tenant.objects.create(name="tenant-b", slug="tenant-b")

    @pytest.fixture
    def user_a(db, tenant_a):
        user = User.objects.create_user("user-a@example.com")
        Membership.objects.create(tenant=tenant_a, user=user, role="member", is_active=True)
        return user

    @pytest.fixture
    def project_a(db, tenant_a):
        return Project.objects.create(tenant=tenant_a, name="project-a")

    @pytest.fixture
    def project_b(db, tenant_b):
        return Project.objects.create(tenant=tenant_b, name="project-b")

Tenant routing: shared-schema apps resolve the tenant from the authenticated membership,
a session value, or a validated header/path — pick the ONE mechanism your middleware
actually implements and use it consistently below:

    # session-based active tenant (workspace switcher):
    #   session = api_client.session; session["tenant_id"] = tenant_a.pk; session.save()
    # validated header (your middleware must check membership!):
    #   api_client.defaults["HTTP_X_ORGANIZATION"] = str(tenant_a.pk)
    # domain-routed tenants only (django-tenants-style Domain model):
    #   api_client.defaults["HTTP_HOST"] = tenant_a.get_primary_domain().domain
"""

import pytest

# from app.models import Project


def route_to_tenant(api_client, tenant):
    """Route subsequent requests to `tenant`. Replace with your project's mechanism
    (see module docstring) — there is no universal API for this."""
    raise NotImplementedError("wire your tenant routing here")


@pytest.mark.django_db
def test_list_endpoint_excludes_other_tenant_data(api_client, tenant_a, tenant_b, user_a, project_a, project_b):
    pytest.fail("TODO: wire real fixtures/URLs and route_to_tenant, then delete this line.")
    api_client.force_authenticate(user_a)
    route_to_tenant(api_client, tenant_a)
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
    route_to_tenant(api_client, tenant_a)
    response = api_client.get(f"/api/TODO/{project_b.id}/")
    # Prefer 404 over 403: a 403 on a guessed foreign pk confirms the object exists in
    # another tenant (existence oracle). DRF returns 404 automatically when get_object()
    # derives from a tenant-scoped get_queryset().
    assert response.status_code in {403, 404}


@pytest.mark.django_db
def test_update_other_tenant_object_is_denied(api_client, tenant_a, tenant_b, user_a, project_b):
    pytest.fail("TODO: wire real fixtures/URLs, then delete this line.")
    api_client.force_authenticate(user_a)
    route_to_tenant(api_client, tenant_a)
    response = api_client.patch(f"/api/TODO/{project_b.id}/", {"name": "hijacked"}, format="json")
    assert response.status_code in {403, 404}
    project_b.refresh_from_db()
    assert project_b.name != "hijacked"


@pytest.mark.django_db
def test_delete_other_tenant_object_is_denied(api_client, tenant_a, tenant_b, user_a, project_b):
    pytest.fail("TODO: wire real fixtures/URLs and import your model, then delete this line.")
    from app.models import Project  # TODO: point at your tenant-owned model

    api_client.force_authenticate(user_a)
    route_to_tenant(api_client, tenant_a)
    response = api_client.delete(f"/api/TODO/{project_b.id}/")
    assert response.status_code in {403, 404}
    assert Project.objects.filter(pk=project_b.id).exists()


@pytest.mark.django_db
def test_create_ignores_or_rejects_posted_tenant_id(api_client, tenant_a, tenant_b, user_a):
    pytest.fail("TODO: wire real fixtures/URLs and import your model, then delete this line.")
    from app.models import Project  # TODO: point at your tenant-owned model

    api_client.force_authenticate(user_a)
    route_to_tenant(api_client, tenant_a)
    response = api_client.post("/api/TODO/", {"name": "x", "tenant": tenant_b.id}, format="json")
    assert response.status_code in {201, 400, 403}
    if response.status_code == 201:
        created_id = response.json()["id"]
        created = Project.objects.get(pk=created_id)
        assert created.tenant_id == tenant_a.id
