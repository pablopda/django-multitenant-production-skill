# Production Operations Runbook

## Contents

- Provisioning
- Migrations
- Backups and restore
- Tenant offboarding
- Data subject requests (GDPR)
- Observability
- Incident response
- Performance
- Secrets and configuration
- Support tooling

A multi-tenant app is not production-ready until operations are designed.

## Provisioning

Provisioning should be idempotent and stateful:

- requested
- validating domain/payment/owner
- creating tenant record
- creating schema/database/defaults
- active
- failed_retryable
- failed_manual

Record failures and allow safe retry. Do not expose a tenant as active until database, domain, owner, and default permissions are consistent.

If tenants bring custom domains, automate TLS certificate issuance/renewal for those domains as part of provisioning (and revocation at offboarding) — manual certificates do not scale past a handful of tenants.

## Migrations

Before deploy:

- list tenant count and largest tenants
- estimate migration time
- decide serial vs parallel execution: `migrate_schemas --executor multiprocessing`, tuned via `TENANT_MULTIPROCESSING_MAX_PROCESSES`/`TENANT_MULTIPROCESSING_CHUNKS`. Parallelism multiplies DB connections — size the pool and `max_connections` for it.
- set connection pool limits
- test migration on staging copy with multiple tenants
- define rollback/backout
- communicate downtime or degraded mode if required

Lock safety:

- create indexes with `CREATE INDEX CONCURRENTLY` (requires `atomic = False` migrations)
- add NOT NULL via nullable column + backfill + validate constraint, not a single rewriting ALTER
- keep deploy-time migrations additive-only; ship destructive changes in a later release
- run batched backfills as separate steps, never inside DDL migrations
- set `lock_timeout`/`statement_timeout` during DDL so a blocked ALTER fails fast instead of queueing traffic behind it
- an ALTER that takes ACCESS EXCLUSIVE, repeated serially across thousands of schemas, is a long rolling degradation — plan the window accordingly

During deploy:

- track per-tenant migration status
- log schema/tenant and migration name
- stop on critical errors unless intentionally configured otherwise
- alert on failed tenant migrations

After deploy:

- verify tenant app health across representative tenants
- verify background jobs resumed with tenant context
- verify support/admin can inspect migration status

## Backups and restore

Document:

- full database backup cadence
- per-tenant restore capability
- tenant file/blob backup strategy
- retention and legal hold
- test restore cadence

Schema-per-tenant can simplify per-tenant logical backup/restore, but shared tables, public user tables, and files still need coordinated restore.

Per-tenant restore (schema-per-tenant):

```bash
pg_dump -Fc -n <schema> dbname > tenant.dump
pg_restore --schema=<schema> -d dbname tenant.dump
```

Caveats:

- FKs into public tables must still resolve after restore
- contenttype/permission IDs drift between schemas — restored rows can point at the wrong types
- verify sequence state after restore; stale sequences cause duplicate-key errors on next insert
- tenant files/blobs must be restored in the same step or references dangle
- the shared public user table cannot be point-in-time restored per tenant

Run a periodic restore rehearsal into a scratch database. An untested restore path is not a restore capability.

## Tenant offboarding

Use staged offboarding:

1. suspend access
2. export data if contract requires
3. retention/legal hold window
4. anonymize or delete tenant data
5. remove domains and revoke tokens
6. delete files/blobs according to policy
7. drop schema/database only after backup and approval
8. audit all steps

Avoid default physical schema drop on simple model delete.

## Data subject requests (GDPR)

Right to erasure is per person, not per tenant. Support per-user erasure/anonymization inside a live tenant, not only tenant offboarding.

- with `django-tenant-users`, the user row lives in the public schema plus per-tenant permission rows in N tenant schemas — erasure must touch all of them
- preserve audit integrity: anonymize actor identifiers in audit rows rather than deleting them
- erased data persists in backups: state a backup-expiry window and a no-restore-then-reprocess policy (on restore, re-apply erasures logged since the backup)
- support per-user export for portability, scoped to the requesting tenant
- if tenants are pinned to regions (ADR input in references/01), erasure/export tooling must follow the tenant's region

## Observability

Logs should include:

- tenant ID or schema name
- domain if relevant
- actor ID
- request ID/trace ID
- privileged action marker

Metrics to consider:

- requests by tenant
- error rate by tenant
- migration duration by tenant
- task failures by tenant
- storage usage by tenant
- DB size by tenant/schema
- noisy-neighbor indicators

Cardinality trap: tenant-ID metric labels explode at thousands of tenants. Cap tenant-labelled metrics to top-N tenants; use logs/columnar analytics for the long tail.

Alerts for cross-tenant anomalies — named signals:

- spike in 403/404-by-tenant on object endpoints (enumeration or scoping regression)
- canary tenant with synthetic probes asserting its data never appears in other tenants' responses
- row counts returned under mismatched tenant context in privileged report paths

## Incident response

For suspected cross-tenant leak:

1. preserve logs and audit events
2. identify affected tenant(s), endpoints, and actors
3. disable affected endpoint/task if needed
4. rotate exposed credentials/tokens
5. patch and add regression tests
6. review cache/CDN/file links for residual exposure
7. create post-incident remediation tasks

## Performance

Schema-per-tenant:

- **connection pooler mode is a correctness constraint, not a tuning knob:** `SET search_path` isolation requires session-mode pooling (or no external pooler, relying on `CONN_MAX_AGE`). Transaction- or statement-mode PgBouncer can run queries under the wrong tenant's schema — silent cross-tenant leakage. Verify pooler mode before every deploy (see references/03).
- many schemas can slow migrations and introspection
- search path updates can add overhead
- connection pool and migration parallelism need limits
- cross-tenant analytics need explicit aggregation strategy

Shared schema:

- every hot query needs tenant-leading indexes
- largest tenants can dominate table bloat
- noisy-neighbor risk is higher
- partitioning/Citus/RLS should be considered based on scale and risk

## Secrets and configuration

If tenant-specific credentials exist:

- store encrypted
- scope access by tenant
- rotate per tenant
- avoid logging
- ensure backups are protected

## Support tooling

Build internal tooling for:

- tenant lookup by domain, ID, owner email
- schema/database health
- migration status
- safe tenant suspension/reactivation
- audited support impersonation
- read-only tenant diagnostics
