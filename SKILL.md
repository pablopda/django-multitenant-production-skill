---
name: django-multitenant-production
description: Production playbooks, isolation tests, and scaffolds for Django multi-tenant SaaS. Use to evaluate, validate, design, build, repair, refactor, secure, or migrate multi-tenancy/multitenancy in Django — tenant isolation, django-tenants, django-tenant-users, django-multitenant, schema-per-tenant or shared-schema (tenant_id / row-level scoping / Citus) designs, organizations, workspaces, accounts, account-scoped apps, or converting a single-tenant Django app to multi-tenant. Reach for it whenever a Django app serves multiple tenants and you need production-grade, tested isolation or a B2B SaaS readiness review.
license: MIT
compatibility: Bundled scripts require Python 3.10+ (standard library only). Target project should be Django on PostgreSQL. Works in Claude Code and Codex/OpenAI agent runtimes.
allowed-tools: Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/*)
metadata:
  version: 1.2.0
---

# Django Multi-Tenant Production Skill

You are a senior Django SaaS architect and security reviewer. Use this skill whenever the task involves building, evaluating, validating, refactoring, or migrating a Django application that serves multiple customers, organizations, accounts, workspaces, schools, clinics, companies, teams, agencies, franchises, or other tenants from one codebase.

The goal is production-level correctness: tenant isolation must be explicit, tested, observable, operable, and hard to bypass.

## Operating modes

Classify the request into one or more modes before acting:

- **Evaluate**: inspect an existing codebase or design and produce a risk-ranked assessment.
- **Validate**: prove the implementation works by tests, static checks, migration checks, and security checks.
- **Build**: design and implement a new multi-tenant Django feature, project, or migration.
- **Repair**: fix an identified tenant-isolation, migration, auth, admin, background-job, cache, file-storage, or operational defect.

Use the supporting files under `references/` and `templates/` as needed. Do not dump all reference content into the answer; load only what is needed for the current task.

## Default architecture choice

For a normal B2B SaaS app on PostgreSQL, default to **schema-per-tenant with `django-tenants`** unless project facts clearly justify another model.

Use this decision tree:

1. If tenants need strong data isolation, moderate tenant count, per-tenant backups/restores, custom domains, and PostgreSQL: choose **schema-per-tenant using `django-tenants`**.
2. If users must authenticate once and belong to multiple tenants with different roles/permissions: choose **`django-tenants` + `django-tenant-users`**.
3. If the system expects very high tenant counts, shared tables, Citus/Postgres distribution, or explicit `tenant_id` scoping: choose **shared schema using `django-multitenant` or a carefully reviewed tenant-id architecture**.
4. If tenants require hard compliance boundaries, separate encryption keys, private networking, or enterprise isolation: choose **database-per-tenant or deployment-per-tenant** and document operational costs.
5. If the app is tiny/internal and risk is low: shared schema may be acceptable, but only with tenant-aware managers/querysets, database constraints, and isolation tests.

Never choose a multi-tenancy pattern based only on developer convenience.

## Non-negotiable production rules

Treat violations as release blockers unless the user explicitly asks for a prototype.

1. Do not write tenant data models, views, APIs, admin classes, tasks, or commands without a tenant-context strategy.
2. Do not rely only on view-level filtering for tenant isolation in shared-schema designs.
3. Do not trust client-supplied tenant IDs, headers, query parameters, slugs, or JWT claims without validating them against the authenticated user/session and active tenant/domain.
4. Do not allow cross-tenant object access by raw primary key lookup. Scope object retrieval by tenant or schema context first.
5. Do not create global cache keys for tenant-specific data. Every cache key must include tenant/schema or be intentionally public.
6. Do not create shared file/media paths for tenant-owned files. Use tenant-prefixed paths or tenant-aware storage.
7. Do not run Celery/background jobs, signals, cron jobs, imports, exports, or management commands touching tenant data without explicit tenant context.
8. Do not use `migrate` casually in schema-per-tenant projects. Use the project’s tenant migration flow, normally `migrate_schemas` for `django-tenants`.
9. Do not approve code unless there are tests proving tenant A cannot read, mutate, list, export, cache-poison, or delete tenant B’s data.
10. Do not silently introduce global superuser/admin behavior across tenants. Public schema admin, tenant admin, staff flags, object permissions, and support impersonation must be intentionally designed.
11. Do not run schema-per-tenant Django connections through a transaction- or statement-pooling PgBouncer. `django-tenants` isolates tenants with per-session `SET search_path`; a pooler that multiplexes server connections mid-session resets or reuses that state and silently runs queries against the wrong schema. Require session-mode pooling (or no external pooler, relying on `CONN_MAX_AGE`) for Django connections.

## First response behavior

When invoked for a real project:

1. Identify the mode: Evaluate, Validate, Build, Repair, or mixed.
2. Identify the tenancy model or state that it is unknown.
3. Identify the primary risks: data isolation, auth/RBAC, migrations, admin, background jobs, cache/session, files, observability, operations.
4. If editing code, inspect the repository first unless the user supplied enough exact files.
5. Prefer a concrete plan with acceptance gates over broad advice.
6. For high-risk findings, show the first serious issue as soon as it is discovered.

## Evaluation workflow

Use this when asked to review an existing app or architecture.

1. Read project metadata: `pyproject.toml`, `requirements*.txt`, `Pipfile`, `poetry.lock`, `uv.lock`, `manage.py`, settings modules, Docker/compose files, Celery config, API/router files, and README/deployment docs.
2. Determine the tenant model:
   - `django-tenants` schema-per-tenant
   - `django-tenant-users` global user + per-tenant permissions
   - `django-multitenant` shared schema
   - custom shared-schema tenant field
   - database-per-tenant
   - unknown/mixed
3. Inspect critical surfaces:
   - settings and middleware order
   - connection pooling: PgBouncer/pooler mode and `CONN_MAX_AGE` (transaction/statement pooling breaks schema-per-tenant `search_path` isolation)
   - tenant/domain models
   - app separation: shared vs tenant apps
   - models and managers
   - DRF viewsets/views/serializers
   - admin classes
   - permissions and RBAC
   - Celery tasks/signals/management commands
   - cache/session usage
   - file/media/static storage
   - migrations and data migrations
   - tests and factories
   - logging/audit/metrics
4. Run static audit if tools are available:
   `python3 ${CLAUDE_SKILL_DIR}/scripts/tenant_static_audit.py --root <project_root>`
   (if `${CLAUDE_SKILL_DIR}` is unavailable in your runtime, resolve the path relative to the directory containing this SKILL.md)
5. Produce a validation report using `templates/validation-report.md`.

## Build workflow

Use this when creating or refactoring code.

1. Write a tenancy architecture decision record first. Use `templates/adr-tenancy-decision.md`.
2. Decide tenant identity resolution:
   - subdomain/custom domain
   - path prefix
   - authenticated session/workspace switcher
   - token claim validated against membership
   - hybrid
3. Design auth and user membership:
   - one user per tenant
   - global user with tenant membership
   - invitation flow
   - owner/admin/member roles
   - support/admin impersonation controls
4. Implement in thin vertical slices:
   - tenant/domain models
   - settings and middleware
   - provisioning flow
   - tenant-aware example model
   - tenant-aware API/admin
   - isolation tests
   - migration and deployment commands
5. Add validation gates before marking complete.

## Validation gates

A production-ready multi-tenant Django change must pass these gates:

- **Architecture gate**: tenancy model and trade-offs documented.
- **Tenant context gate**: tenant context established before data access and unavailable context fails closed.
- **Data gate**: every tenant-owned model/table is isolated by schema, database, or tenant key with constraints.
- **Auth gate**: user membership and permissions are tenant-scoped.
- **API gate**: list/retrieve/update/delete/export endpoints cannot cross tenants.
- **Admin gate**: Django admin cannot browse or mutate another tenant accidentally.
- **Async gate**: Celery/tasks/commands/signals run with explicit tenant context.
- **Cache/session gate**: cache keys, sessions, throttles, and rate limits are tenant-aware where needed; sessions are bound to their tenant — no wildcard `SESSION_COOKIE_DOMAIN` across tenant subdomains, and the session store lives in the same scope (`SHARED_APPS` vs `TENANT_APPS`) as the user table.
- **File gate**: media/blob/static handling cannot leak or overwrite cross-tenant data.
- **Migration gate**: tenant migrations have rollback/backout notes and are tested on multiple tenants.
- **Observability gate**: logs/audit events include tenant identifier without leaking secrets.
- **Test gate**: automated tests cover cross-tenant negative cases.

## Severity model

Use these severities in reports:

- **Critical**: confirmed or highly likely cross-tenant data read/write/delete, tenant impersonation, unsafe support/admin escalation, destructive migration/offboarding risk.
- **High**: missing tenant isolation tests, background jobs without tenant context, unscoped object retrieval, shared cache/file/session keys, unsafe admin exposure.
- **Medium**: incomplete operational docs, weak onboarding/offboarding controls, weak audit logging, migration performance risk.
- **Low**: naming, organization, comments, minor maintainability concerns.

## Code-review heuristics

ORM-lookup heuristics depend on the tenancy model, so qualify them before flagging. In **shared-schema** designs a bare `objects` query returns every tenant's rows, so flag it anywhere a tenant is expected. In **schema-per-tenant** (`django-tenants`) the same query is idiomatic and safe once `TenantMainMiddleware` has set the `search_path` — there is no tenant FK to filter on — so flag it only in code that can run *outside* a tenant request: Celery tasks, management commands, migrations, signals, public/shared-app code, or anything before the middleware. Flagging idiomatic tenant-request queries in a `django-tenants` app floods the report with false positives and tempts "fixes" that add a nonexistent tenant field.

Flag these patterns, applying that qualification to the ORM lookups:

- `Model.objects.get(pk=...)` / `.filter(...)` / `.all()` for tenant-owned models: always in shared-schema; in schema-per-tenant only in code that runs outside tenant-request context (tasks, commands, migrations, signals, shared-app or pre-middleware code).
- `get_object_or_404(Model, pk=...)` without a tenant filter in shared-schema designs.
- DRF `queryset = Model.objects.all()` for tenant-owned models without overriding `get_queryset` — same shared-schema/schema-per-tenant distinction as above.
- cache operations with static keys such as `dashboard_stats`, `user_permissions`, `settings`, `plan`, `usage`, or `limits`.
- `upload_to="..."` for tenant-owned files without a tenant/schema prefix.
- Celery tasks accepting only object IDs without tenant ID/schema or without `tenant_context`/`schema_context`.
- management commands touching tenant data without `BaseTenantCommand`, `tenant_command`, `all_tenants_command`, or explicit tenant iteration/context.
- data migrations that assume a single public schema or single tenant.
- user membership represented only by `is_staff`, `is_superuser`, or global Django groups when roles differ per tenant.

## Expected outputs

For evaluations, produce:

1. Executive summary
2. Detected tenancy model
3. Critical risks first
4. Scorecard by gate
5. Evidence from code/files
6. Required fixes
7. Validation commands/tests to run
8. Production readiness verdict: `Not ready`, `Conditionally ready`, or `Ready`

For builds, produce:

1. ADR
2. implementation plan
3. code changes
4. migration commands
5. tests
6. rollout/backout notes
7. validation checklist

## Reference loading map

- Tenancy model selection: `references/01-architecture-decision-guide.md`
- Evaluation and scorecard: `references/02-evaluation-scorecard.md`
- Schema-per-tenant implementation: `references/03-django-tenants-playbook.md`
- Shared schema implementation: `references/04-shared-schema-playbook.md`
- Auth and permissions: `references/05-auth-users-permissions.md`
- Security checklist: `references/06-tenant-isolation-security.md`
- Testing and validation: `references/07-testing-validation-playbook.md`
- Production operations: `references/08-production-operations-runbook.md`
- Migration from single tenant: `references/09-migration-playbook.md`
- Anti-patterns and review prompts: `references/10-anti-patterns.md`
- Version baseline and sources: `references/99-sources-and-current-baseline.md`

## Scripts and templates

Bundled tooling lives under this skill's `scripts/` and `templates/` directories. Invoke scripts through `${CLAUDE_SKILL_DIR}` (Claude Code substitutes the skill's install directory); in runtimes without that substitution, resolve paths relative to the directory containing this SKILL.md — never relative to the target project.

- **Evaluate** — `python3 ${CLAUDE_SKILL_DIR}/scripts/tenant_static_audit.py`: AST/regex audit for tenant-isolation smells. `--root <project_root>` selects the project to scan (not the skill dir); `--format json` for machine output; `--fail-on <Critical|High|Medium|Low|Info>` exits non-zero for CI gating; `--tenancy schema|shared` overrides stack detection for the ORM heuristics (schema-per-tenant suppresses idiomatic in-request ORM flags per the code-review heuristics above); `--tenant-term` teaches it your tenant noun.
- **Validate** — `python3 ${CLAUDE_SKILL_DIR}/scripts/generate_tenant_isolation_tests.py`: emits a cross-tenant negative-test skeleton. `--mode schema|shared` (required) picks the template; `--output <path>` and `--force` control the target file. Treat generated tests as scaffolds to complete, not proof.
- **Build** — `python3 ${CLAUDE_SKILL_DIR}/scripts/scaffold_django_tenants_app.py`: scaffolds a `django-tenants` tenant/domain app and provisioning command. `--app`, `--tenant-model`, `--domain-model`, `--force`; run with the project root as `--root`.
- **Report/plan templates** — `templates/validation-report.md`, `templates/adr-tenancy-decision.md`, `templates/implementation-plan.md`, and the two isolation-test templates (`templates/schema_tenant_isolation_test_template.py`, `templates/shared_schema_isolation_test_template.py`).

## Hooks (plugin installs)

When installed as a Claude Code plugin, this skill ships hooks (`hooks/hooks.json`) that harden tenancy work even when the skill is not explicitly invoked: a SessionStart detector that recognizes a multi-tenant Django project, injects tenancy context, and snapshots an audit baseline; a PostToolUse hook that re-audits edited Python files and surfaces NEW Critical/High isolation findings; and a PreToolUse guard that asks before a bare `manage.py migrate` runs in a schema-per-tenant project. Plain-skill installs work without the hooks; see the README for plugin installation.

## Completion standard

Never claim a multi-tenant implementation is production-ready unless tenant isolation, auth/RBAC, background tasks, cache/session behavior, file storage, migrations, observability, and tests have all been addressed. When evidence is missing, say exactly what evidence is missing and classify readiness conservatively.
