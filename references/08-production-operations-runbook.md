# Production Operations Runbook

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

## Migrations

Before deploy:

- list tenant count and largest tenants
- estimate migration time
- decide serial vs parallel execution
- set connection pool limits
- test migration on staging copy with multiple tenants
- define rollback/backout
- communicate downtime or degraded mode if required

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
