# Changelog

All notable changes to the Django Multi-Tenant Production Skill are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The currency baseline in `references/99-sources-and-current-baseline.md` is the source
of truth for tested package versions; bump it and this changelog together.

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
