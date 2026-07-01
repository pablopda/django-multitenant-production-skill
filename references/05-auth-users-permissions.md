# Auth, Users, Membership, and Permissions

Multi-tenant auth has two separate questions:

1. Who is the human or machine actor?
2. What can that actor do in this tenant right now?

Do not collapse those into global `is_staff`, `is_superuser`, or global groups unless every tenant has identical permissions.

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
