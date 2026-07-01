# Anti-Patterns and Review Prompts

Use this file to guide code reviews and agent self-checks.

## Critical anti-patterns

### Raw tenant ID from request

```python
tenant_id = request.headers["X-Tenant-ID"]
return Invoice.objects.filter(tenant_id=tenant_id)
```

Why unsafe: the client controls tenant identity. Validate tenant against authenticated membership or use trusted domain/session context.

### Unscoped object lookup

```python
invoice = Invoice.objects.get(pk=invoice_id)
```

Safe alternative for shared schema:

```python
invoice = Invoice.objects.for_tenant(request.tenant).get(pk=invoice_id)
```

Schema-per-tenant still requires correct schema context before this lookup.

### DRF global queryset

```python
class InvoiceViewSet(ModelViewSet):
    queryset = Invoice.objects.all()
```

Fix with tenant-scoped `get_queryset`.

### Task without tenant context

```python
@shared_task
def send_invoice(invoice_id):
    invoice = Invoice.objects.get(pk=invoice_id)
```

Fix by passing tenant ID/schema and scoping lookup.

### Shared cache key

```python
cache.set("feature_flags", flags)
```

Fix with tenant-aware key unless flags are truly global.

### Unsafe upload path

```python
contract = models.FileField(upload_to="contracts/")
```

Fix with tenant-prefixed path and download authorization.

### Global tenant admin role

```python
if request.user.is_staff:
    # tenant admin
```

Fix with tenant membership role checks.

## Medium anti-patterns

- no ADR for tenancy model
- no tenant lifecycle states
- physical delete used for tenants/users instead of soft deletion/retention
- custom domain accepted without verification
- tenant migrations not timed or observable
- logs lack tenant identifier
- tests use only one tenant

## Review prompts

Ask these while reviewing code:

1. What tenant is active at this line?
2. What prevents tenant A from providing tenant B's object ID?
3. What happens if the user belongs to tenant A but not tenant B?
4. What happens if the tenant is suspended?
5. Does this code run in a request, task, signal, command, migration, or shell?
6. Does this cache key include tenant/schema?
7. Does this file path include tenant/schema?
8. Does this permission check use tenant membership, not just global user flags?
9. Does this migration run for public schema, tenant schemas, or both?
10. Is there a negative test proving the boundary?

## Agent self-check before final answer

Before claiming completion, verify:

- tenancy model identified
- tenant context path explained
- auth/membership path explained
- code changes include tests
- async/cache/file/admin/migration implications addressed
- remaining risks disclosed
