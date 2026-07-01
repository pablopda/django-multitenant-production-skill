# Testing and Validation Playbook

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

## Shared-schema tests

Every tenant-owned API/viewset needs negative cases:

```python
def test_user_cannot_retrieve_other_tenant_object(api_client, tenant_a, tenant_b, user_a, project_b):
    api_client.force_authenticate(user_a)
    api_client.set_tenant(tenant_a)
    response = api_client.get(f"/api/projects/{project_b.pk}/")
    assert response.status_code in {403, 404}
```

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

## Cache/session validation checklist

- same cache key name under tenant A and B stores separate values
- switching active tenant invalidates/reloads tenant-specific permission cache
- suspended/deleted membership prevents session reuse
- rate limits/quotas are tenant-scoped where required

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
