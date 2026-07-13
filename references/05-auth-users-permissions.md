# Auth, Users, Membership, and Permissions

Multi-tenant auth has two separate questions:

1. Who is the human or machine actor?
2. What can that actor do in this tenant right now?

Do not collapse those into global `is_staff`, `is_superuser`, or global groups unless every tenant has identical permissions.

## Contents

- [Common models](#common-models)
- [`django-tenant-users` implementation](#django-tenant-users-implementation)
- [Sessions and cookie scope](#sessions-and-cookie-scope)
- [Membership model pattern](#membership-model-pattern)
- [Tenant switching](#tenant-switching)
- [Invitations](#invitations)
- [Support/admin impersonation](#supportadmin-impersonation)
- [Django admin](#django-admin)
- [DRF permissions](#drf-permissions)
- [API tokens and service accounts](#api-tokens-and-service-accounts)
- [Authorization test cases](#authorization-test-cases)

## Common models

### Per-tenant user accounts

Each tenant has its own user rows and logins. This is simpler for strict isolation but annoying for users who belong to many tenants.

Use when:

- users rarely belong to multiple tenants
- tenants require separate identity spaces
- schema-per-tenant auth is acceptable

Risks:

- duplicate accounts
- password/reset complexity
- cross-tenant support workflows are harder

### Global user with tenant membership

One global user identity can belong to many tenants. Roles/permissions are scoped per tenant.

Use when:

- agencies, consultants, support teams, or owners work across many tenants
- SaaS has a workspace switcher
- enterprise SSO maps users to organizations

For `django-tenants`, consider `django-tenant-users` when this model is required.

## `django-tenant-users` implementation

`django-tenant-users` is the skill's default when one global identity spans many `django-tenants` schemas with different roles per tenant. It moves the user identity into the public schema and keeps per-tenant permissions in each tenant schema, so you do not hand-roll the `Membership` pattern below.

Key API and settings (baseline 2.2.1 — confirm against the installed version):

- **User model** subclasses `tenant_users.tenants.models.UserProfile` and lives in the **public schema** — it is the global identity. Point `AUTH_USER_MODEL` at it. Email is the identifier.
- **Tenant model** subclasses `tenant_users.tenants.models.TenantBase` (this replaces `TenantMixin`; it adds `slug`, `owner`, and lifecycle fields).
- **Per-tenant permissions** come from `tenant_users.permissions.models.UserTenantPermissions`, which stores `is_staff`/`is_superuser`/groups/permissions **inside each tenant schema**; `PermissionsMixinFacade` on the user proxies `has_perm`/`is_staff` to whichever tenant schema is active. The same user can be staff in tenant A and a plain member in tenant B.
- **Auth backend**: `AUTHENTICATION_BACKENDS = ("tenant_users.permissions.backend.UserBackend",)`.
- **Domain suffix**: `TENANT_USERS_DOMAIN = "example.com"`, used to build tenant subdomains.

App placement is load-bearing — get it wrong and permissions resolve in the wrong schema:

```python
SHARED_APPS = (
    "django_tenants",
    "tenant_users.permissions",   # tables also needed in public
    "tenant_users.tenants",       # tenant registry + global users
    "accounts",                   # app holding your UserProfile subclass
    "django.contrib.auth",
    "django.contrib.contenttypes",
    # ...
)
TENANT_APPS = (
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tenant_users.permissions",   # per-tenant UserTenantPermissions rows
    # ...
)
```

Setup and tenant creation flow:

- Bootstrap once with `create_public_tenant(domain, owner_email)` (in `tenant_users.tenants.utils`; returns `(tenant, domain, user)`) to create the public tenant and the first global owner.
- Create tenants with `provision_tenant` from `tenant_users.tenants.tasks`, which creates the schema, domain, and owner atomically — do not `Client.objects.create()` by hand. Signature in 2.2.1: `provision_tenant(tenant_name, tenant_slug, owner, *, is_staff=False, is_superuser=True, tenant_type=None, schema_name=None, tenant_extra_data=None)`, returning `(tenant, domain)`. The third argument is a **user instance** — the pre-2.0 API took an email string. Unless `schema_name=` is passed explicitly, the schema name is auto-generated as `f"{slug}_{timestamp}"` — surprising if you expect slug == schema.

  ```python
  from tenant_users.tenants.tasks import provision_tenant

  tenant, domain = provision_tenant(tenant_name="Acme", tenant_slug="acme", owner=user)
  ```

- Add/remove members with the tenant's `add_user(user, ...)` / `remove_user(user)` helpers rather than writing permission rows directly; per-tenant roles are expressed through each tenant's groups/permissions in `UserTenantPermissions`.

## Sessions and cookie scope

A session cookie authenticates by storing a `user_id` PK. Two placement mistakes turn that into cross-tenant authentication:

1. **Split scope.** If `django.contrib.auth` (the user table) is in `TENANT_APPS` but `django.contrib.sessions` is in `SHARED_APPS` (or vice versa), a session minted in tenant A resolves its `user_id` against a *different* schema's user table on the next request. Keep the session store and the user table in the **same** scope — both `TENANT_APPS` or both `SHARED_APPS`, never split.
2. **Wildcard cookie domain.** With subdomain-per-tenant routing, `SESSION_COOKIE_DOMAIN = ".example.com"` makes a cookie issued on `a.example.com` valid on `b.example.com`. Combined with per-tenant user tables, the stored `user_id` PK can resolve to a *different* user with the same PK in tenant B — silent cross-tenant login. Do not set a parent-domain cookie across tenant subdomains; scope cookies to the tenant host.

Also rotate the session with `request.session.cycle_key()` on tenant switch so a captured pre-switch session id cannot be replayed against the new tenant.

## Membership model pattern

```python
class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        BILLING = "billing", "Billing"
        VIEWER = "viewer", "Viewer"

    tenant = models.ForeignKey("accounts.Tenant", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_invites")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "user"], name="uniq_membership_tenant_user"),
        ]
```

## Tenant switching

When a user switches active tenant:

1. Validate membership is active.
2. Validate tenant is active and not suspended/deleted.
3. Store active tenant in session or issue a tenant-bound token.
4. Audit the switch if security-sensitive.
5. Recompute permissions for that tenant.

Never accept arbitrary tenant ID from UI without server-side membership validation.

## Invitations

Invitation flow should include:

- invite email belongs to intended actor
- inviter has tenant role allowing invites
- invitation token is signed, expiring, and one-time-use
- accepted membership created in the correct tenant only
- invitation acceptance does not grant global staff/admin
- audit trail for invite, accept, revoke

## Support/admin impersonation

Support workflows are high-risk.

Require:

- explicit permission for support access
- reason/ticket ID
- time limit
- visible audit log
- no silent bypass of tenant permissions unless break-glass
- clear distinction between platform superuser and tenant admin

## Django admin

For tenant apps:

- tenant staff should only see current tenant data
- platform admin should have a separate view/path or explicit schema switcher
- destructive actions require confirmation and audit
- model admins should override `get_queryset` where shared schema is used

Example shared-schema admin:

```python
class TenantScopedAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser and getattr(request, "tenant", None) is None:
            return qs
        return qs.filter(tenant=request.tenant)

    def save_model(self, request, obj, form, change):
        if not change and hasattr(obj, "tenant"):
            obj.tenant = request.tenant
        super().save_model(request, obj, form, change)
```

## DRF permissions

Combine:

- authentication
- tenant membership permission
- object-level permission for retrieve/update/delete
- tenant-scoped queryset for lists and object retrieval

Example:

```python
class IsTenantMember(BasePermission):
    def has_permission(self, request, view):
        tenant = getattr(request, "tenant", None)
        user = request.user
        return bool(
            tenant
            and user.is_authenticated
            and Membership.objects.filter(tenant=tenant, user=user, is_active=True).exists()
        )
```

Do not let serializers accept tenant fields from user input unless the endpoint is explicitly platform-admin-only.

## API tokens and service accounts

API tokens should be tenant-bound unless they are platform-level tokens.

Store:

- tenant
- actor/service account
- scopes
- expiry/rotation metadata
- last used timestamp
- allowed IPs or integration ID if needed

Log tenant and token ID, not raw token.

## Authorization test cases

Minimum cases:

- user in tenant A cannot access tenant B endpoint
- user in tenant A and B has correct permissions per tenant
- inactive membership fails
- suspended tenant fails
- posted `tenant_id` is ignored or rejected
- tenant admin cannot become platform admin
- support impersonation is audited
