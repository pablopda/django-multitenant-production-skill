# Evaluation Scorecard

## Contents

- Scoring
- Domains
  1. Architecture and tenancy model
  2. Tenant context resolution
  3. Data isolation
  4. Authentication and authorization
  5. APIs and views
  6. Admin
  7. Background jobs, signals, and commands
  8. Cache, sessions, rate limits, and queues
  9. Files, media, static, templates
  10. Migrations and data lifecycle
  11. Observability and audit
  12. Tests
- Verdict rubric

Use this scorecard for existing applications, design reviews, and PR reviews.

## Scoring

Score each domain:

- 0 = absent or unsafe
- 1 = partial, high-risk gaps
- 2 = mostly implemented, some gaps
- 3 = production-ready evidence present

Critical domains: 2 (tenant context resolution), 3 (data isolation), 4 (authentication and authorization), and 12 (tests). A score of 0 in any critical domain means the project is **not production-ready**.

## Domains

### 1. Architecture and tenancy model

Evidence to collect:

- ADR or design doc
- selected model: schema-per-tenant, shared schema, DB-per-tenant, hybrid
- reasons and trade-offs
- expected tenant count and compliance needs

Red flags:

- package chosen without documented business/ops rationale
- mixed models without explicit boundaries
- no offboarding/backups/restore design

### 2. Tenant context resolution

Evidence:

- middleware/resolver order
- domain/session/token validation
- active tenant available on request or connection
- failure behavior when tenant is unknown

Red flags:

- tenant from raw header/query param
- tenant selected after database queries
- unknown tenant falls back to public data unintentionally

### 3. Data isolation

Evidence:

- schema/database separation, or tenant keys and constraints
- managers/querysets
- object lookup patterns
- database-level constraints where applicable
- connection pooler mode for schema-per-tenant: session-mode pooling or no external pooler (`CONN_MAX_AGE`); pooler config documented

Red flags:

- unscoped `.objects.get(pk=...)`
- global `.objects.all()` in tenant endpoints
- raw SQL without schema/tenant binding
- bulk update/delete without tenant filter
- schema-per-tenant Django connections routed through transaction- or statement-mode PgBouncer (search_path leakage — automatic Critical)

### 4. Authentication and authorization

Evidence:

- membership model
- tenant-scoped roles/groups/permissions
- invitation lifecycle
- owner transfer and support impersonation controls

Red flags:

- global `is_staff` used as tenant admin
- global groups for tenant-specific roles
- user can switch tenant without membership check
- permissions checked only in frontend

### 5. APIs and views

Evidence:

- tenant-aware `get_queryset`
- tenant-aware object permissions
- list/retrieve/update/delete negative tests
- import/export scoping

Red flags:

- DRF `queryset = Model.objects.all()` for tenant-owned models
- object-level permission absent for retrieve/update/delete
- export endpoint uses global queryset

### 6. Admin

Evidence:

- tenant-specific admin site or filtered model admins
- support/admin audit logs
- public schema vs tenant schema separation

Red flags:

- public admin can browse tenant data accidentally
- tenant staff can see global auth/users incorrectly
- admin actions do bulk operations without tenant filter

### 7. Background jobs, signals, and commands

Evidence:

- Celery task payloads include tenant context or schema
- tasks use `schema_context`/`tenant_context` or equivalent
- management commands use tenant-aware base classes or explicit iteration
- signals know the active tenant or avoid tenant data

Red flags:

- task receives only object ID
- scheduled job reads all tenant data in current/default schema
- data migration assumes one schema

### 8. Cache, sessions, rate limits, and queues

Evidence:

- tenant-aware cache key function or key prefix
- session active tenant validated
- rate limits scoped by tenant/user as needed
- queue names or payloads include tenant where required

Red flags:

- `cache.set("dashboard_stats", ...)`
- tenant switch changes session without membership validation
- global throttles let one tenant affect others unnecessarily

### 9. Files, media, static, templates

Evidence:

- tenant-prefixed upload paths
- tenant-aware storage backend
- signed URLs or policies include tenant
- tenant-specific static/template strategy if needed

Red flags:

- all uploads stored under one predictable path
- file download by raw file ID/path
- custom tenant templates can override unsafe global templates

### 10. Migrations and data lifecycle

Evidence:

- migration commands and order
- dry run on multiple tenants
- large-tenant performance plan
- backup and rollback plan
- offboarding and retention plan

Red flags:

- not knowing which `migrate` actually runs: django-tenants ships a `migrate` command aliased to `migrate_schemas` when django_tenants wins command resolution (listed first in `INSTALLED_APPS`). An un-aliased `migrate` (django_tenants not winning resolution, or direct `django.core` invocation) bypasses tenant schemas; the aliased one migrates ALL schemas during what was meant as a hotfix
- no test tenant migration
- destructive tenant deletion by default

### 11. Observability and audit

Evidence:

- logs include tenant/schema/domain
- security events include tenant and actor
- metrics by tenant where useful
- error reporting scrubs secrets and tenant data appropriately

Red flags:

- no way to trace cross-tenant incident
- raw tenant secrets in logs
- global support actions unaudited

### 12. Tests

Evidence:

- cross-tenant negative tests
- tenant-specific factories
- task/command tests
- admin/API tests
- migration test strategy

Red flags:

- tests only happy path in one tenant
- no negative cross-tenant read/write tests
- no tests for imports/exports/background jobs

## Verdict rubric

- **Ready**: all critical domains (2, 3, 4, 12) score 3, no Critical/High findings open, validation commands pass.
- **Conditionally ready**: no Critical findings, High findings have specific mitigations and owner/date.
- **Not ready**: any Critical finding, score 0 in any critical domain, or schema-per-tenant connections pooled in transaction/statement mode (automatic Critical).
