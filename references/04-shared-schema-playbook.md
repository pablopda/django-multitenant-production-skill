# Shared-Schema Tenant-ID Playbook

Use when all tenants share tables and every tenant-owned row has a tenant/account/organization key. This includes `django-multitenant` and custom tenant-id designs.

Shared schema can be production-grade, but it is easier to leak data. The skill must be stricter here than in schema-per-tenant designs.

## Required design elements

1. A canonical tenant model, usually `Account`, `Organization`, `Workspace`, or `Tenant`.
2. A tenant key on every tenant-owned model.
3. Tenant-scoped managers/querysets.
4. Tenant-scoped unique constraints.
5. Tenant-scoped foreign key constraints where feasible.
6. Tenant-aware API/admin/tasks/commands.
7. Negative tests for all user-facing surfaces.
8. Optional PostgreSQL Row-Level Security for high-risk tables.

## Model pattern

Generic Django pattern:

```python
class TenantOwnedQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)

class TenantOwnedManager(models.Manager):
    def get_queryset(self):
        return TenantOwnedQuerySet(self.model, using=self._db)

    def for_tenant(self, tenant):
        return self.get_queryset().for_tenant(tenant)

class Project(models.Model):
    tenant = models.ForeignKey("accounts.Tenant", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)

    objects = TenantOwnedManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="uniq_project_name_per_tenant"),
        ]
        indexes = [
            models.Index(fields=["tenant", "name"]),
        ]
```

Do not leave an easy unscoped global manager available in application code unless there is a strong convention and tests. For platform admin/reporting, create explicit privileged query paths.

## DRF patterns

Bad:

```python
class ProjectViewSet(ModelViewSet):
    queryset = Project.objects.all()
```

Good:

```python
class ProjectViewSet(ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        return Project.objects.for_tenant(self.request.tenant)

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant)
```

Also ensure `get_object()` is derived from `get_queryset()`, not a raw model lookup.

## Object permissions

Permission checks must bind actor, tenant, and object:

```python
class IsTenantObjectMember(BasePermission):
    def has_object_permission(self, request, view, obj):
        return (
            getattr(obj, "tenant_id", None) == request.tenant.id
            and request.user.memberships.filter(tenant=request.tenant, is_active=True).exists()
        )
```

Do not rely only on object permissions if list endpoints are unscoped. Always scope querysets first.

## Tenant context middleware

Shared-schema apps need an explicit request tenant context:

1. Resolve candidate tenant from domain/path/session/token.
2. Validate tenant exists and is active.
3. Validate user has access when the endpoint requires auth.
4. Attach `request.tenant`.
5. Clear context at the end of request.

Use Python `contextvars` carefully if code needs context outside request objects. Reset it after each request/task to avoid leakage across threads/async tasks.

## Database constraints

Use tenant-scoped uniqueness:

```python
models.UniqueConstraint(fields=["tenant", "external_id"], name="uniq_external_id_per_tenant")
```

Consider composite keys or extra constraints for critical child tables to ensure a child cannot reference a parent from another tenant.

For PostgreSQL, consider Row-Level Security when the risk justifies it. RLS is not a substitute for app-level scoping, but it can provide defense in depth.

## Background jobs

Celery task payloads should include tenant ID and object ID:

```python
@shared_task
def send_project_digest(tenant_id, project_id):
    tenant = Tenant.objects.get(pk=tenant_id, is_active=True)
    project = Project.objects.for_tenant(tenant).get(pk=project_id)
    ...
```

Bad:

```python
@shared_task
def send_project_digest(project_id):
    project = Project.objects.get(pk=project_id)
```

## Cache and storage

Cache keys:

```python
cache_key = f"tenant:{request.tenant.pk}:project:{project.pk}:stats"
```

File paths:

```python
def tenant_upload_to(instance, filename):
    return f"tenants/{instance.tenant_id}/{instance._meta.model_name}/{filename}"
```

## Reporting and global admin

Cross-tenant queries are allowed only in explicit platform/admin modules, with:

- clear naming such as `platform_reports` or `global_admin`
- privileged permissions
- audit logging
- tests proving tenant users cannot reach the same path

## Minimum tests

For every tenant-owned model exposed by API/admin:

- list endpoint excludes other tenant rows
- retrieve returns 404/403 for other tenant row ID
- update/delete cannot mutate other tenant rows
- create assigns current tenant and ignores posted tenant ID
- import/export is tenant-scoped
- cache/session does not leak values
- background task accepts tenant ID and scopes object lookup

## `django-multitenant` notes

`django-multitenant` (the Citus helper) adds an implicit tenant filter to the ORM based on a thread/async-local "current tenant". Concrete API to look for and use:

- Models subclass `django_multitenant.models.TenantModel` and declare `tenant_id = "account_id"` — the name of the tenant column/FK on that model. `TenantManager` (`.objects`) then auto-injects `WHERE account_id = <current tenant>` on `get_queryset` whenever a current tenant is set. Mixin form: `django_multitenant.mixins.TenantModelMixin` / `TenantManagerMixin`.
- Foreign keys between tenant-owned models use `django_multitenant.fields.TenantForeignKey` (and `TenantOneToOneField`) so joins carry the tenant column — required for Citus colocation and composite references.
- Request/task code brackets its work with `set_current_tenant(tenant)` ... `unset_current_tenant()` from `django_multitenant.utils`; `get_current_tenant()` reads it back.
- **Fail-open default:** with no current tenant set, `TenantManager` returns ALL rows across tenants — it does not raise. Any path that forgets `set_current_tenant` silently leaks, so tests must cover the no-context case explicitly.
- Still verify migrations include the tenant/composite constraints, review (do not assume) DRF integration, and plan Citus/distributed tables if scale-out is a goal.

### Middleware caveat

Do not adopt the shipped `django_multitenant.middlewares.MultitenantMiddleware` as-is. In 4.1.1 it calls `set_current_tenant()` only for authenticated users and never unsets it after the response. Because the current tenant lives in a thread-local/asgiref `Local`, a later anonymous request — or a different tenant's request — handled by the same thread/worker inherits the previous request's tenant: exactly the cross-request leak the middleware section above warns about. Instead:

- Set the current tenant in a custom middleware that wraps the view call in `try/finally` and calls `unset_current_tenant()` in the `finally`.
- Unset in Celery task teardown too (`task_postrun` or a `finally` block), not just in the web tier.
- Add a negative test: an anonymous (or tenant-B) request after a tenant-A request on the same worker sees no leftover tenant context.
