# `django-tenants` Schema-Per-Tenant Playbook

Use for PostgreSQL schema-per-tenant applications.

## Baseline architecture

- Public schema contains shared/global tables, tenant registry, and domain mapping.
- Each tenant has a separate PostgreSQL schema for tenant-owned data.
- Tenant is usually resolved from hostname/custom domain.
- Middleware sets the PostgreSQL search path for the current request.
- Shared apps migrate only on public schema; tenant apps migrate on tenant schemas.

## Required settings

Check or add:

```python
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        # name/user/password/host/port...
    }
}

DATABASE_ROUTERS = (
    "django_tenants.routers.TenantSyncRouter",
)

MIDDLEWARE = (
    "django_tenants.middleware.main.TenantMainMiddleware",
    # all other middleware after tenant middleware
)

SHARED_APPS = (
    "django_tenants",
    "customers",  # app containing tenant/domain models
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    "django.contrib.staticfiles",
)

TENANT_APPS = (
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.admin",
    # tenant-specific apps here
)

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

TENANT_MODEL = "customers.Client"
TENANT_DOMAIN_MODEL = "customers.Domain"

ROOT_URLCONF = "myproject.urls"                    # tenant URLs
PUBLIC_SCHEMA_URLCONF = "myproject.urls_public"    # public/marketing/signup URLs
```

Review whether auth/admin should live in public, tenant schemas, or both. Do not blindly copy app lists.

### Hostname resolution and the public schema

`TenantMainMiddleware` maps the request hostname to a `Domain` row:

- On a hostname with no matching `Domain` it raises `Http404` (via `TENANT_NOT_FOUND_EXCEPTION`). Set `SHOW_PUBLIC_IF_NO_TENANT_FOUND = True` to fall back to the public schema instead of 404 — useful for a shared marketing/signup site, but it is a fail-*open* fallback, so keep the public urlconf minimal.
- On the public schema the middleware swaps `request.urlconf` to `PUBLIC_SCHEMA_URLCONF`; the tenant urlconf stays in `ROOT_URLCONF`. Without `PUBLIC_SCHEMA_URLCONF` the public schema serves the tenant URLs — a common mistake that exposes tenant routes on the marketing domain.
- For path-based tenancy instead of hostnames, use `django_tenants.middleware.TenantSubfolderMiddleware` with `TENANT_SUBFOLDER_PREFIX` (e.g. `example.com/t/acme/`); it resolves the tenant from the first path segment rather than the host.

## Tenant and domain models

Typical starter:

```python
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class Client(TenantMixin):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    paid_until = models.DateField(null=True, blank=True)
    on_trial = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_on = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True
    auto_drop_schema = False

    def __str__(self):
        return self.name

class Domain(DomainMixin):
    pass
```

Production considerations:

- keep `auto_drop_schema = False` unless there is a heavily reviewed deletion process
- avoid exposing `schema_name` as user-controlled free text
- validate schema names with a conservative allowlist
- track tenant status: provisioning, active, suspended, deleting, deleted
- separate logical deletion from physical schema drop
- custom domains need verification and takeover protection

## Provisioning flow

A safe tenant provisioning flow normally has:

1. create tenant record in public schema
2. create schema/migrate tenant apps
3. create domain record
4. create owner/membership/permissions
5. create default tenant data using `tenant_context`
6. emit audit event
7. send activation email or webhook only after migrations/default data succeed

For async provisioning, use idempotent steps and record provisioning state. Do not expose the tenant as active until schema and defaults are ready.

## Migrations

Commands to expect:

```bash
python manage.py makemigrations
python manage.py migrate_schemas --shared
python manage.py migrate_schemas
python manage.py migrate_schemas --schema=tenant_schema_name
```

Production migration checklist:

- dry-run or test against at least two tenant schemas
- test a large tenant copy where possible
- ensure data migrations use tenant context
- record migration duration per tenant
- throttle or parallelize carefully to avoid exhausting DB connections
- define backout plan before deploy

## Connection pooling

`django-tenants` isolation is entirely `SET search_path` session state set by the middleware/context managers on the Django connection. That makes pooler mode a correctness issue, not just a performance one:

- **Session-mode pooling** (or no external pooler at all, relying on Django `CONN_MAX_AGE` persistent connections) is required.
- **Transaction- or statement-mode PgBouncer is unsafe**: the pooler multiplexes server connections mid-session, so a query can execute with another tenant's `search_path` — silent cross-tenant leakage. This is the number-one production burn for schema-per-tenant.
- If transaction-mode PgBouncer is mandatory for other services, give Django its own session-mode pool (or a direct connection), or move off `search_path`-based isolation. The middleware sets the schema once per request; do not assume it re-asserts it per pooled transaction.

## Request-time code

Schema-per-tenant design reduces the need for explicit tenant filters in normal tenant apps, but code still must be context-safe.

Good practices:

- access `request.tenant` when you need tenant metadata
- use `connection.schema_name` for logging or low-level diagnostics only
- use `schema_context(schema_name)` or `tenant_context(tenant)` outside request flow
- fail closed when tenant is missing, inactive, or suspended

## Background jobs and commands

Every task touching tenant data must include tenant context.

Example pattern:

```python
from celery import shared_task
from django_tenants.utils import tenant_context
from customers.models import Client

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True)
def recompute_usage(self, tenant_id):
    tenant = Client.objects.get(pk=tenant_id, is_active=True)
    with tenant_context(tenant):
        # Tenant-owned ORM queries here
        ...
```

Avoid tasks that accept only a tenant-owned object ID. Use tenant ID/schema plus object ID.

For management commands, use tenant-aware wrappers or explicitly iterate tenants and enter context.

## Cache

Use tenant-aware cache keys. For `django-tenants`, prefer the package key function or a project wrapper that includes schema name.

Bad:

```python
cache.set("dashboard_stats", stats)
```

Better:

```python
cache.set(f"tenant:{connection.schema_name}:dashboard_stats", stats)
```

## Files/media/static/templates

Prefer `django-tenants`' built-in tenant-aware storage over hand-rolled paths.

Media and static — point storage at the tenant-aware backends, which prefix each schema's files:

```python
# settings.py
STORAGES = {
    "default": {"BACKEND": "django_tenants.files.storage.TenantFileSystemStorage"},
    "staticfiles": {"BACKEND": "django_tenants.staticfiles.storage.TenantStaticFilesStorage"},
}
MULTITENANT_RELATIVE_MEDIA_ROOT = "%s"    # "%s" is replaced by the schema name
MULTITENANT_RELATIVE_STATIC_ROOT = "%s"
```

Collect per-tenant static files with the `collectstatic_schemas` command. For per-tenant templates, use `django_tenants.template.loaders.filesystem`/`cached` with `MULTITENANT_TEMPLATE_DIRS`.

For object storage (S3/GCS), where the built-in filesystem storage does not apply, derive a tenant-prefixed key from the active schema — but only inside a request or `tenant_context`, so `schema_name` is never `public`:

```python
from django.db import connection

def tenant_upload_to(instance, filename):
    return f"tenants/{connection.schema_name}/{instance._meta.model_name}/{filename}"
```

Ensure file downloads are authorized against tenant context before returning storage URLs.

## Admin

Use `TenantAdminMixin` for tenant model admin. Decide whether admin runs:

- only on public schema for platform operators
- per tenant for tenant staff
- both, with separate URLConf/settings

Guardrails:

- tenant staff cannot browse other tenant schemas
- platform support actions are audited
- admin bulk actions are tenant-scoped
- tenant deletion/renaming requires extra confirmation and backups

## Tests

Use package test utilities where possible:

- `TenantTestCase`
- `TenantClient`
- `TenantRequestFactory`
- `schema_context`
- `tenant_context`

Minimum negative tests:

- tenant A list endpoint does not include tenant B data
- tenant A cannot retrieve/update/delete tenant B object by ID
- task for tenant A does not mutate tenant B data
- cache key for tenant A does not return tenant B value
- file download for tenant A cannot access tenant B file

## Common mistakes

- middleware order wrong
- tenant model app missing from `SHARED_APPS`
- tenant apps included in shared apps accidentally
- running `migrate` instead of tenant migration command without understanding effect
- tenant deletion drops schema unexpectedly
- Celery tasks run in public schema
- admin exposes public/global tables to tenant staff
- transaction-mode PgBouncer resets/reuses `search_path` across tenants (see Connection pooling)
- serving tenant URLs on the public schema because `PUBLIC_SCHEMA_URLCONF` is unset
- tests use only one tenant/schema
