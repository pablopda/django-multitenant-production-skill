# ADR: Django Multi-Tenancy Architecture

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded
Owner: <name/team>

## Context

Describe the product, tenant type, expected tenant count, data sensitivity, compliance needs, and operational constraints.

## Decision

Chosen model:

- [ ] Schema-per-tenant with `django-tenants`
- [ ] Schema-per-tenant with `django-tenants` + `django-tenant-users`
- [ ] Shared schema with tenant ID / `django-multitenant`
- [ ] Database-per-tenant
- [ ] Deployment-per-tenant
- [ ] Hybrid

Tenant locator:

- [ ] subdomain/custom domain
- [ ] path prefix
- [ ] session/workspace switcher
- [ ] tenant-bound API token/JWT claim
- [ ] other: ____

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Database per tenant | |
| Schema per tenant | |
| Shared schema | |
| Deployment per tenant | |

## Auth and authorization model

- User identity model:
- Membership model:
- Tenant roles:
- Permission checks:
- Support/admin impersonation:

## Data isolation model

- Database/schema/table strategy:
- Tenant-owned models:
- Global models:
- Constraints/indexes:
- Raw SQL policy:

## Async and scheduled work

- Celery/task tenant context:
- Management command strategy:
- Data migration strategy:

## Cache, sessions, files

- Cache key strategy:
- Session active tenant strategy:
- File/media path strategy:
- CDN/signed URL strategy:

## Operations

- Provisioning:
- Migrations:
- Connection pooling (pooler mode / `CONN_MAX_AGE`; schema-per-tenant requires session-mode pooling):
- Backup/restore:
- Offboarding:
- Observability/audit:

## Validation plan

Required tests:

- [ ] tenant A cannot list tenant B data
- [ ] tenant A cannot retrieve tenant B object by ID
- [ ] tenant A cannot update/delete tenant B object
- [ ] tenant A cache does not return tenant B data
- [ ] tenant A cannot download tenant B file
- [ ] background job cannot cross tenants
- [ ] tenant admin cannot cross tenants
- [ ] migration tested across at least two tenants
- [ ] pooler runs in session mode (or no external pooler) for schema-per-tenant connections

## Consequences

Benefits:

Risks:

Mitigations:

Open questions:
