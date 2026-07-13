# Architecture Decision Guide

## Contents

- Required inputs
- Decision matrix
- Production default
- Tenant-count bands
- Tenant identity resolution
- Shared schema guardrails
- Schema-per-tenant guardrails
- ADR questions

Use this guide before writing code. Multi-tenancy is an architecture decision, not a package-selection decision.

## Required inputs

Capture these facts in the ADR:

- number of tenants expected now, at 12 months, and at 36 months
- tenant data volume and largest-tenant skew
- regulatory/compliance requirements
- custom domain requirement
- user model: one account per tenant, or one global user across many tenants
- reporting requirements: per-tenant only, cross-tenant analytics, admin/global dashboards
- backup/restore needs: all tenants together, individual tenant point-in-time restore, legal hold
- data residency or per-tenant encryption needs
- expected background jobs and imports/exports
- API exposure and third-party integrations
- support/admin impersonation requirements
- operational team size and database expertise

## Decision matrix

| Model | Best when | Strengths | Costs/Risks | Default verdict |
|---|---|---|---|---|
| Database per tenant | enterprise isolation, regulated data, few tenants, custom DB maintenance | strongest isolation, simple restore, per-tenant DB tuning | expensive ops, many connections, migrations across DBs | Use for high-compliance tiers |
| Schema per tenant | B2B SaaS on PostgreSQL, moderate tenant count, custom domains, per-tenant logical restore (with public-schema coupling caveats, see references/08) | good isolation, one DB, familiar Django code with `django-tenants` | schema migrations across tenants, cross-tenant analytics complexity | Recommended default |
| Shared schema with tenant key | high tenant count, low isolation needs, Citus/distributed Postgres, cheaper ops | simple migrations, efficient common schema, easier analytics | cross-tenant leak risk if filters fail, all code must be tenant-aware | Use only with strong guardrails |
| Hybrid | different enterprise tiers or regulatory classes | right isolation per customer tier | complex ops and testing matrix | Use intentionally, not accidentally |
| Deployment per tenant | bespoke enterprise, on-prem, private cloud | strongest app/runtime isolation | high cost, version sprawl | Use for strategic accounts only |

## Production default

For new Django SaaS on PostgreSQL, use schema-per-tenant with `django-tenants` unless facts justify shared schema or stronger isolation. `django-pgschemas` (1.2.0, Django 5.2/6.0, Python 3.12+) is an actively maintained schema-per-tenant alternative with static/dynamic tenant separation and parallel management commands; evaluate it when its stricter public-schema philosophy or higher Python floor fits the project.

Add `django-tenant-users` if one human identity must access multiple tenants with different roles/permissions.

Use shared-schema only when the team commits to strict tenant-aware query patterns, tests, and database constraints.

## Tenant-count bands

"Moderate" vs "very high" tenant count is about `tables × tenants`, not row count:

- **Schema-per-tenant is comfortable into the low thousands of schemas.** Each tenant gets a full copy of every `TENANT_APPS` table, so the PostgreSQL catalog, `pg_dump`, autovacuum pressure, and `migrate_schemas` time all scale with `schemas × tables`.
- **Beyond roughly 5,000–10,000 schemas, or with high tenant churn**, migration time (`O(schemas)`), backup duration, and catalog bloat dominate, and per-schema monitoring gets unwieldy. Prefer shared-schema with `tenant_id` (optionally Citus) at that scale.
- A handful of very large tenants is fine for schema-per-tenant; a very large *number* of tenants is the real constraint. If most tenants are tiny or transient, per-schema overhead is pure cost — lean shared-schema.

These bands are rules of thumb; validate against the project's table count and migration cadence before committing.

## Tenant identity resolution

Choose one primary tenant locator and document it.

### Subdomain or custom domain

Examples: `acme.example.com`, `app.acme.com`.

Good for B2B SaaS and `django-tenants` because domain maps naturally to tenant/schema.

Requirements:

- tenant/domain table in public schema
- verified custom domain ownership flow
- primary domain flag
- protection against dangling domains and takeover
- canonical redirects where appropriate
- local development domain strategy such as `.localhost`

### Path prefix

Example: `example.com/t/acme/`.

Use when subdomains are unavailable. Be stricter with URL reversing, middleware, static files, and public/tenant URL separation.

### Session/workspace switcher

Example: user logs in and selects active organization.

Good for global users across many tenants. Validate selected tenant against membership on every switch and before storing active tenant in session.

### Token claim

Use in APIs only if the tenant claim is issued by a trusted identity provider or your backend and is validated against current membership. Never trust raw `X-Tenant-ID` headers from clients.

### Single API domain with `django-tenants`

`TenantMainMiddleware` resolves the tenant from the hostname only. An API-first design that serves every tenant from one domain (`api.example.com`) with the tenant carried in a JWT — very common for DRF SaaS — cannot use the stock middleware, which would resolve the wrong tenant (or 404) from the shared host. Instead:

1. Authenticate the request first.
2. Validate the token's tenant claim against the user's current membership.
3. Only then activate the schema explicitly with `schema_context(schema_name)` / `tenant_context(tenant)`, or via a `TenantMainMiddleware` subclass that overrides tenant resolution.

Never derive the schema directly from an unvalidated claim — that is the API equivalent of trusting an `X-Tenant-ID` header.

## Shared schema guardrails

Shared schema must include:

- tenant FK/tenant ID on every tenant-owned table
- tenant-aware managers/querysets
- tenant-scoped unique constraints
- tenant-aware foreign keys or composite constraints where feasible
- query tests for list, retrieve, update, delete, bulk actions, exports
- admin restrictions
- no raw global `objects` manager usage in application code
- optional PostgreSQL row-level security for high-risk data

## Schema-per-tenant guardrails

Schema-per-tenant must include:

- `django_tenants.postgresql_backend`
- tenant middleware at the top of middleware
- `TenantSyncRouter`
- tenant and domain models inheriting the correct mixins
- correct `SHARED_APPS`, `TENANT_APPS`, `INSTALLED_APPS`
- `TENANT_MODEL`, `TENANT_DOMAIN_MODEL`
- tenant migration workflow
- tenant-aware cache/file/logging behavior
- explicit task/command tenant context
- tests using `TenantTestCase`, `TenantClient`, `schema_context`, or `tenant_context`

## ADR questions

Answer these in the ADR:

1. What is the chosen tenancy model?
2. What alternatives were rejected and why?
3. How is tenant context resolved?
4. How does auth bind users to tenants?
5. How are permissions scoped per tenant?
6. How are migrations run safely?
7. How are background jobs scoped?
8. How are cache/session/storage keys isolated?
9. How is tenant offboarding handled?
10. How are cross-tenant admin/support workflows controlled and audited?
11. What tests prove isolation?
12. What operational runbooks are required?
