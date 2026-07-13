# Testing and Validation Playbook

## Contents

- Test pyramid
- Required tenant fixtures
- Schema-per-tenant tests
- pytest fixtures for django-tenants
- Shared-schema tests
- API validation checklist
- Admin validation checklist
- Async validation checklist
- Cache/session validation checklist
- File validation checklist
- Migration validation checklist
- Static audit command
- Acceptance language

Multi-tenant testing must prove negative cases. A happy-path test in one tenant is not enough.

## Test pyramid

1. Unit tests for tenant resolvers, membership checks, managers/querysets, upload paths, cache keys.
2. Integration tests for APIs/admin/tasks/commands using two or more tenants.
3. Migration tests on multiple schemas or shared-schema data sets.
4. End-to-end tests for onboarding, switching tenant, inviting users, exports/downloads, and offboarding.
5. Security regression tests for every tenant-isolation bug fixed.

## Required tenant fixtures

Every test suite should be able to create:

- tenant A
- tenant B
- user member of tenant A only
- user member of tenant B only
- user member of both tenants with different roles
- tenant admin
- platform admin/support user
- tenant-owned records in both tenants with overlapping names/slugs/external IDs

## Schema-per-tenant tests

Use package utilities when available:

```python
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

class TenantIsolationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantClient(self.tenant)

    def test_tenant_endpoint_uses_current_schema(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
```

For cross-tenant cases, create a second tenant and use `tenant_context` to seed its data.

## pytest fixtures for django-tenants

Schema creation per test is expensive: each tenant save triggers `migrate_schemas` for that schema. Standard pattern: override pytest-django's `django_db_setup` to provision tenant A/B schemas once per session, then wrap per-test data in `schema_context`/`tenant_context`.

```python
# conftest.py — sketch, adapt tenant/domain models and domains to your project
import pytest
from customers.models import Client, Domain  # your tenant/domain models

def _make_tenant(schema_name, domain):
    tenant, _ = Client.objects.get_or_create(schema_name=schema_name, defaults={"name": schema_name})
    Domain.objects.get_or_create(tenant=tenant, domain=domain, is_primary=True)
    return tenant

@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    # Provision both schemas once per session (auto_create_schema runs the migrations).
    with django_db_blocker.unblock():
        _make_tenant("tenant_a", "tenant-a.example.com")
        _make_tenant("tenant_b", "tenant-b.example.com")

@pytest.fixture(scope="session")
def tenant_a(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        return Client.objects.get(schema_name="tenant_a")

# tenant_b: same pattern

@pytest.fixture
def tenant_client(tenant_a):
    from django_tenants.test.client import TenantClient
    return TenantClient(tenant_a)  # or set api_client.defaults["HTTP_HOST"] to the tenant domain
```

Seed per-test data inside `schema_context(tenant_a.schema_name)` / `tenant_context(tenant_a)` so it lands in the right schema. Shared-schema mode needs none of this: plain factories with a tenant FK suffice.

## Shared-schema tests

Every tenant-owned API/viewset needs negative cases:

```python
def test_user_cannot_retrieve_other_tenant_object(api_client, tenant_a, tenant_b, user_a, project_b):
    api_client.force_authenticate(user_a)
    # Route the request to tenant A. For domain-resolved tenants:
    api_client.defaults["HTTP_HOST"] = "tenant-a.example.com"
    # For session- or header-resolved tenants, call your project's tenant-selection
    # helper instead (project-defined; there is no set_tenant on Django/DRF test clients).
    response = api_client.get(f"/api/projects/{project_b.pk}/")
    assert response.status_code in {403, 404}
```

See templates/shared_schema_isolation_test_template.py for starter tests; its `route_to_tenant()` helper is the place to plug in whichever mechanism (host, session, header) your middleware implements.

## API validation checklist

For each tenant-owned endpoint:

- list excludes other tenant rows
- retrieve denies other tenant row ID
- create assigns current tenant and ignores/rejects posted tenant ID
- update/patch denies other tenant row ID
- delete denies other tenant row ID
- bulk operations filter by tenant
- export/import scoped by tenant
- serializer does not expose tenant internals unless intended

## Admin validation checklist

- tenant admin sees only own tenant rows
- tenant admin cannot create object assigned to other tenant
- tenant admin bulk action is tenant-scoped
- platform admin path is separate and audited
- tenant deletion/renaming requires confirmation

## Async validation checklist

- Celery task includes tenant ID/schema
- task sets context before ORM calls
- task cannot mutate object from another tenant if passed mismatched tenant/object IDs
- scheduled jobs iterate all active tenants intentionally
- retries preserve tenant context
- task teardown clears tenant context; the next task on the same worker starts clean

## Cache/session validation checklist

- same cache key name under tenant A and B stores separate values
- switching active tenant invalidates/reloads tenant-specific permission cache
- suspended/deleted membership prevents session reuse
- rate limits/quotas are tenant-scoped where required
- request without tenant context (anonymous, or immediately after a tenant-A request on the same worker/thread) sees no leftover tenant — regression test for thread-local/contextvar leaks (see references/04 middleware caveat)

## File validation checklist

- tenant A upload path includes tenant A identifier
- tenant B cannot download tenant A file by ID/path
- signed URL generation validates tenant membership
- file deletion/offboarding affects only intended tenant files

## Migration validation checklist

For schema-per-tenant:

- `migrate_schemas --shared` works on clean database
- `migrate_schemas --schema=<test_tenant>` works
- full `migrate_schemas` works on at least two tenants
- data migration runs inside tenant context
- failed tenant migration is observable and recoverable

For shared schema:

- new tenant columns are non-null or backfilled safely
- unique constraints include tenant
- indexes support tenant-scoped queries
- data backfill does not mix tenants

## Static audit command

From repository root, run:

```bash
python path/to/skill/scripts/tenant_static_audit.py --root .
```

Treat findings as prompts for manual review. The script is conservative and can produce false positives.

## Acceptance language

Use these phrases in validation reports:

- “Verified by test” only when a test exists and was run or clearly present.
- “Likely safe” only when code pattern is clearly tenant-scoped but not executed.
- “Not proven” when tests are missing.
- “Release blocker” for Critical/High issues affecting tenant isolation.
