# Tenant Isolation Security Checklist

Use this as a security review checklist. Cross-tenant leakage is a critical class of defect.

## Tenant context

- Tenant context is established early in middleware or routing.
- Tenant context is validated against authenticated actor where applicable.
- Unknown, inactive, or suspended tenants fail closed.
- Tenant context is cleared after request/task execution.
- Client-supplied tenant IDs are never trusted without server-side validation.
- Tenant identifiers in URLs are non-authoritative unless validated.
- Hostname-resolved tenancy never runs with `ALLOWED_HOSTS = ['*']` — hosts are validated against the Domain table or an explicit suffix allowlist. Wildcard hosts enable Host-header cache/password-reset poisoning, especially on the public schema with `SHOW_PUBLIC_IF_NO_TENANT_FOUND` enabled.
- `CSRF_TRUSTED_ORIGINS` is derived per tenant.
- Password-reset and other absolute URLs are built from the tenant's canonical domain, not the raw request Host.

## Database access

- Schema-per-tenant projects set search path before tenant queries.
- Shared-schema projects scope all tenant-owned rows by tenant.
- Raw SQL includes tenant/schema safeguards.
- Bulk update/delete operations are tenant-scoped.
- Cross-tenant platform queries are isolated in explicit privileged modules.
- Database constraints enforce tenant-scoped uniqueness.
- Optional RLS is considered for high-risk shared-schema tables (see references/04, Row-Level Security defense in depth — ENABLE+FORCE, GUC-based policy).

## IDOR prevention

- Retrieve/update/delete by `pk` is scoped by tenant first.
- URLs containing object IDs cannot access another tenant's object.
- Exports, imports, attachments, and webhooks are tenant-scoped.
- Error responses do not leak existence of other-tenant resources beyond intended 404/403 semantics.
- Prefer 404 for cross-tenant object IDs (DRF returns it automatically when `get_object()` derives from a tenant-scoped `get_queryset()`); a 403 on a guessed foreign PK is itself an existence oracle.

## Auth and permissions

- Membership is tenant-scoped.
- Roles/permissions can differ per tenant.
- Tenant switching validates membership.
- Staff/admin privileges are separated between platform and tenant.
- Invitation, owner transfer, and account recovery are tenant-aware.
- Support impersonation is time-bound, justified, and audited.

## API security

- API tokens are tenant-bound or explicitly platform-level.
- Webhooks include tenant context and signature verification.
- Rate limits and quotas are tenant-aware where required.
- Batch endpoints validate every object belongs to the current tenant.
- GraphQL resolvers and dataloaders are tenant-aware.

## Cache and sessions

- Cache keys for tenant data include tenant/schema.
- Permission/feature-flag caches are tenant-scoped.
- Session active tenant is validated and refreshed after membership changes.
- Session store and the user table live in the same scope (both `SHARED_APPS` or both `TENANT_APPS`), and `SESSION_COOKIE_DOMAIN` does not span tenant subdomains — otherwise a session's `user_id` PK can resolve to a different tenant's user.
- CDN/cache headers do not expose tenant-specific data publicly.
- Global cache entries are intentionally public and documented.

## Files and blob storage

- Tenant-owned files are stored under tenant-prefixed paths or tenant-specific buckets/containers.
- Download endpoints check tenant access before returning files or signed URLs.
- Signed URL policies include tenant/resource authorization.
- Uploaded filenames are sanitized.
- Deletion/offboarding handles retention and legal hold.

## Async, queues, and schedulers

- Task payload includes tenant ID/schema and object ID.
- Worker sets tenant context before ORM access.
- Scheduled jobs iterate tenants intentionally.
- Queue names or routing are isolated if one tenant can affect another.
- Retries are idempotent and tenant-scoped.

## Observability and audit

- Logs include tenant/schema/domain for tenant requests.
- Audit events include tenant, actor, action, target, timestamp, IP/user agent where appropriate.
- Sensitive tenant data is not logged.
- Alerts exist for cross-tenant access anomalies.
- Support/admin actions are especially visible.

## Onboarding and offboarding

- Tenant provisioning is idempotent.
- Domains are verified before use.
- Failed provisioning does not leave active partial tenants.
- Tenant suspension blocks access without deleting data.
- Tenant deletion is two-phase and reversible where business requires.
- Physical schema/database/file deletion requires confirmation and backups.

## Security release blockers

Block release for:

- any confirmed cross-tenant data access
- unvalidated tenant switching
- tenant-owned endpoints with global querysets
- tasks/commands touching tenant data without tenant context
- shared cache/file paths that can leak tenant data
- missing cross-tenant negative tests for changed tenant-owned features
