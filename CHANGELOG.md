# Changelog

All notable changes to the Django Multi-Tenant Production Skill are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The currency baseline in `references/99-sources-and-current-baseline.md` is the source
of truth for tested package versions; bump it and this changelog together.

## [1.2.0] — 2026-07-13

Outcome of a multi-agent review sweep (content accuracy vs the pinned package wheels,
deep code review + hands-on QA of the scripts, skill-authoring best practices, package
currency) plus two new subsystems: a self-test suite and Claude Code plugin/hooks packaging.

### Added

- **Self-test suite** (`tests/`, stdlib `unittest`, also pytest-compatible; ~75 tests) covering SKILL.md frontmatter validity, path integrity in both directions, doc/version consistency, seeded-bug fixtures proving each audit heuristic fires (and that correctly scoped code stays clean), scaffold/generator behavior, template compilation, plugin manifests, and the hook scripts end-to-end. CI workflow (`.github/workflows/tests.yml`) runs it on Python 3.10–3.13.
- **Claude Code plugin packaging**: `.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` make the repo installable via `/plugin marketplace add pablopda/django-multitenant-production-skill`, and upgrade existing `~/.claude/skills/` checkouts to skills-dir plugins.
- **Hooks** (`hooks/hooks.json` + `scripts/hooks/`, stdlib-only, fail-silent): SessionStart tenancy detector that injects skill-aware context and snapshots an audit baseline; PostToolUse incremental audit reporting only NEW Critical/High findings for the edited file (each reported exactly once); PreToolUse ask-first guard for bare `manage.py migrate` in schema-per-tenant projects.
- `scripts/tenant_static_audit.py`: `--tenancy auto|schema|shared` flag and `tenancy_mode` in the JSON facts.
- References: concrete RLS defense-in-depth pattern (ENABLE+FORCE, GUC policy, `SET LOCAL`, owner-bypass caveat, pooling contrast); Channels/websockets isolation; async/ASGI contextvars guidance; per-tenant rate limiting; pytest-django fixtures for django-tenants; GDPR data-subject requests; per-tenant `pg_dump -n` restore with coupling caveats; lock-safety/zero-downtime migration bullets; `migrate_schemas --executor multiprocessing`; `tenant-schemas-celery` and Celery beat fan-out; contenttypes-safe data-load guidance; observability cardinality caps and concrete anomaly signals; host-validation (`ALLOWED_HOSTS`) items; 404-vs-403 existence-oracle preference; `django-pgschemas` as a tracked alternative. Tables of contents on all references over 100 lines.
- Templates: update/delete IDOR negative tests in both isolation-test templates; a conftest fixture sketch and pluggable tenant routing in the shared-schema template; migration-commands and rollout/backout sections in the implementation plan; connection-pooling line and validation item in the ADR.
- SKILL.md frontmatter: `license`, `compatibility`, and a scoped `allowed-tools` grant for the bundled scripts.

### Changed

- `scripts/tenant_static_audit.py` heuristics are now tenancy-model-aware, matching SKILL.md's code-review heuristics: in detected schema-per-tenant projects the ORM/DRF/`get_object_or_404` rules fire only in code that runs outside a tenant request (tasks, commands, migrations, signals); Celery/raw-SQL checks no longer require a high-risk filename; severity aligned with SKILL.md's model (`REQUEST-SOURCED-TENANT-ID` → Critical, cache/file findings → High); DT settings presence checks aggregate across split settings files; scoping-hint matching is boundary-aware ("org" no longer hides inside "forgot"); one DRF queryset line yields one finding.
- SKILL.md script invocations use `${CLAUDE_SKILL_DIR}` (with a portability note for runtimes without the substitution).
- Baseline refreshed to 2026-07-13: Django 6.0.7 / 5.2.16 (2026-07-07 security releases), django-tenants 3.10.2; caveats recorded for django-multitenant (upstream support ends at Django 4.2, dormant since 2023-12) and django-tenant-users (no declared Django 6.0 support); OWASP source link replaced with the Cheat Sheet Series index and specific sheets.
- README: plugin install path documented first, hooks section, live-change-detection wording instead of the blanket restart instruction.

### Fixed

- `scripts/tenant_static_audit.py` crash paths: dangling symlinks/unreadable files (`OSError` on stat/read), NUL-byte/UTF-16 sources on Python ≤ 3.11 (`ValueError` from `ast.parse`), and UTF-8-BOM files losing all AST checks. `app/tests.py` now counts as a test file; `Pipfile` and `requirements/` directory layouts are scanned; `--tenant-term` vocabulary now reaches tenant-test detection and command-context checks; the MIDDLEWARE order check parses the AST instead of a regex that a `)` in a comment could truncate; `request.get_host()`/task `**kwargs` are no longer misflagged as client-sourced tenant ids (while view kwargs still are); annotated `queryset:` assignments are flagged; `.objects.create` joined the checked methods.
- `scripts/scaffold_django_tenants_app.py`: Python keywords rejected as identifiers; identical `--tenant-model`/`--domain-model` rejected; generated command's schema-name rule matches the model validator (letter start) plus the 63-char limit; domain-creation failure now raises a `CommandError` naming the half-provisioned state; dotted apps get regular (not namespace) intermediate packages and a `migrations/` package; reruns print a wrote/skipped summary.
- `scripts/generate_tenant_isolation_tests.py`: schema-mode output directory is made a real package so `manage.py test` actually collects the fail-loudly tests on Python 3.11+ (previously they could be silently skipped — a vacuous green); `--output` can no longer escape `--root`.
- `templates/shared_schema_isolation_test_template.py` no longer routes tenants through django-tenants-only `get_primary_domain()` in shared-schema mode; docstring now describes the real error-then-fail behavior.
- `references/05`: `provision_tenant` corrected to the real django-tenant-users 2.2.1 API (`tenant_users.tenants.tasks`, owner is a user instance, returns `(tenant, domain)`, timestamped default `schema_name`).
- `references/02`: connection-pooler mode added as evidence + automatic-Critical red flag (a scorecard-driven review could previously emit "Ready" while violating SKILL.md rule 11); "critical domains" defined explicitly; plain-`migrate` red flag reworded to django-tenants' actual command aliasing.
- `references/07`: non-existent `api_client.set_tenant()` replaced with the real HTTP_HOST mechanism; context-leak regression tests added to the checklists that references/04 already mandated.

## [1.1.0] — 2026-07-02

Refinements from a five-expert content review plus a with-skill/baseline evaluation
of the skill. The production-gate checklist and reference playbooks are preserved;
this release sharpens accuracy, triggering, and the docs/install story.

### Added

- README: a **Compatibility** table mirroring `references/99-sources-and-current-baseline.md`, a **Verify the install** section, and a **Versioning** note.
- This changelog.

### Changed

- `SKILL.md` frontmatter: removed the non-standard `scope` field and merged its verbs into `description`; broadened `description` for auto-triggering (multi-tenancy/multitenancy, schema-per-tenant, shared-schema `tenant_id`/Citus, single-tenant → multi-tenant conversion) and added a `metadata.version`.
- README: explicit-invocation examples are labelled per runtime (Claude Code `/` slash form, Codex `$` mention); the Codex install snippet is self-contained; the per-project install no longer leaves a stray checkout or `.git/`; the Agent Skills docs link now points to `https://code.claude.com/docs/en/skills`.
- `templates/validation-report.md`: the scorecard carries a rubric legend pointing at `references/02-evaluation-scorecard.md`.
- `CONTRIBUTING.md`: documents which frontmatter fields the runtimes read and a doc-consistency step for version/layout changes.

### Fixed

- `scripts/tenant_static_audit.py`: no longer a `SyntaxError` on Python ≤3.11 (backslash in an f-string expression) — it previously failed to run, including `--help`, on the exact Django versions the skill targets. Added a `--tenant-term`/`--tenant-field` option so projects whose tenant is named `organization`/`account`/`workspace` are audited correctly (it no longer greps only the literal word "tenant"); added detection of raw SQL (`.raw()`, `.extra()`, `cursor.execute()`) and unscoped bulk mutations; file classification is now relative to `--root`; and several false-positive rules were tightened (public-fallback regex, settings-file detection, `TenantSubfolderMiddleware`, `tenant_schemas_celery`).
- `scripts/generate_tenant_isolation_tests.py`: generated isolation tests now **fail loudly** until implemented instead of passing green with empty bodies — an unimplemented isolation test can no longer be mistaken for a passing one.
- `scripts/scaffold_django_tenants_app.py`: dotted `--app` paths (e.g. `platform.tenants`) now emit a correct `TENANT_MODEL`/`TENANT_DOMAIN_MODEL` app label; dropped an unsafe `@transaction.atomic` around schema creation and added schema-name validation.
- `templates/*isolation_test_template.py`: corrected a non-existent test-client API (`.headers[...]` → `defaults["HTTP_HOST"]`/`get_primary_domain()`) and replaced flaky substring-on-JSON isolation assertions with id-set comparisons.
- `SKILL.md` code-review heuristics: ORM lookups (`objects.all()`, `get(pk=)`) are now qualified by tenancy model — flagged unconditionally in shared-schema, but in schema-per-tenant only outside tenant-request context — to stop false-positive floods on idiomatic `django-tenants` code.
- References: added connection-pooler caveats (PgBouncer transaction/statement pooling breaks `search_path` isolation), session-cookie scoping across tenant subdomains, `PUBLIC_SCHEMA_URLCONF`/hostname-resolution behavior, tenant-aware file/static storage, the real `django-multitenant` API surface and its middleware teardown caveat, tenant-count operational bands, single-API-domain + tenant-in-JWT guidance, and expanded `django-tenant-users` coverage.

## [1.0.0] — 2026-06-09

### Added

- Initial release: `SKILL.md`, references `01`–`10` plus `99`, copy-paste templates, and the `tenant_static_audit.py`, `scaffold_django_tenants_app.py`, and `generate_tenant_isolation_tests.py` scripts. Tested baseline captured in `references/99-sources-and-current-baseline.md`.
