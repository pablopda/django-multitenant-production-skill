# Migration Playbook: Single-Tenant to Multi-Tenant

## Contents

- Migration principles
- Phase 0: Discovery
- Phase 1: Choose architecture
- Phase 2A: Schema-per-tenant migration
- Phase 2B: Shared-schema migration
- Phase 3: Auth and permissions
- Phase 4: Files and cache
- Phase 5: Background jobs and integrations
- Phase 6: Production rollout
- Exit criteria

Use when converting an existing Django app to multi-tenancy.

## Migration principles

- Back up before every destructive step.
- Do not migrate all code paths at once without test coverage.
- Add tenant isolation tests before or alongside code changes.
- Prefer a strangler/vertical-slice approach: one tenant-owned domain at a time.
- Maintain a rollback path until production validation passes.

## Phase 0: Discovery

Inventory:

- models and tables
- auth/user assumptions
- admin usage
- APIs and exports
- Celery tasks and cron jobs
- management commands
- file/media storage
- cache/session keys
- integrations/webhooks
- reports/analytics
- data migrations

Classify each model/table:

- global/platform data
- tenant-owned data
- tenant membership/auth data
- cross-tenant reporting/analytics data
- audit/log data

## Phase 1: Choose architecture

Create ADR. Decide:

- schema-per-tenant, shared schema, DB-per-tenant, or hybrid
- tenant locator
- user model
- membership/permissions
- migration rollout plan

## Phase 2A: Schema-per-tenant migration

Typical path:

1. introduce tenant app with tenant/domain models
2. split `SHARED_APPS` and `TENANT_APPS`
3. configure `django-tenants`
4. create public tenant
5. move tenant-owned apps to tenant schemas
6. migrate public schema and tenant schema(s)
7. load existing data into first tenant schema (highest-risk step — see below)
8. update URLs/domains
9. add tests
10. repeat for additional tenants/imports

Step 7 data load in detail:

- **Cutover:** maintenance freeze (stop writes, dump, load, verify, flip routing) or dual-write with a verification window (write old+new, compare per-table row counts/checksums, cut reads last). Freeze is simpler; use dual-write only when downtime is unacceptable.
- **PK/sequence collisions** when consolidating multiple ex-single-tenant databases: assign non-overlapping ID offset ranges per source, or issue new UUIDs plus an old-to-new mapping table for FK rewrite. Either way, reset sequences (`setval`) after load.
- **Contenttypes trap:** ContentType PKs differ per schema/database, so naive `dumpdata`/`loaddata` silently corrupts GenericForeignKey and permission rows. Use `dumpdata --natural-foreign --natural-primary` and exclude `contenttypes` and `auth.permission`, or remap IDs in a data migration.

Risks:

- auth tables in wrong schema — verify the `SHARED_APPS`/`TENANT_APPS` split against references/03 before the first migrate; inspect the actual schemas
- contenttypes/permissions mismatch — exclude both from data loads (natural keys, see above); let `migrate_schemas` recreate them per schema
- migrations not idempotent — run full `migrate_schemas` twice on a staging copy; the second run must be a no-op
- data migrations assuming public schema — wrap in `schema_context`/tenant iteration and test on at least two schemas
- file paths still global — audit `upload_to`/storage keys for a tenant prefix before cutover (Phase 4)

## Phase 2B: Shared-schema migration

Typical path:

1. create tenant model
2. add nullable tenant FK to tenant-owned tables
3. backfill tenant ID
4. add tenant-scoped indexes
5. update managers/querysets/views/tasks/admin
6. add tenant-scoped unique constraints
7. make tenant FK non-null
8. block direct global managers in app code
9. add cross-tenant tests

Risks:

- unique constraints not including tenant
- stale endpoints still using global `.objects`
- posted tenant ID accepted from clients
- background jobs missing tenant context

## Phase 3: Auth and permissions

Decide whether to:

- keep users per tenant
- introduce global users with memberships
- use `django-tenant-users`
- integrate SSO per tenant

Migrate carefully:

- map old users to tenant memberships
- deduplicate emails if global users
- preserve password reset/security state
- preserve audit history
- test tenant switching and permissions

## Phase 4: Files and cache

- rewrite upload paths or add compatibility layer
- migrate existing media to tenant-prefixed paths if needed
- update download authorization
- prefix cache keys by tenant
- invalidate old global cache keys

## Phase 5: Background jobs and integrations

- update Celery task signatures to include tenant context
- add idempotency keys including tenant
- update webhooks to map integration to tenant
- update scheduled jobs to iterate tenants
- add tests for mismatched tenant/object IDs

## Phase 6: Production rollout

- run migration rehearsal on staging copy
- prepare tenant-by-tenant validation script
- deploy behind feature flag where possible
- monitor logs by tenant/schema
- have rollback/backout
- keep old exports/backups until confidence window closes

## Exit criteria

Migration is complete only when:

- every tenant-owned model is classified and isolated
- APIs/admin/tasks/commands are tenant-aware
- cache/files are tenant-aware
- auth/membership is tenant-scoped
- cross-tenant tests pass
- migration runbook and rollback are documented
- operators can provision, suspend, restore, and offboard tenants
