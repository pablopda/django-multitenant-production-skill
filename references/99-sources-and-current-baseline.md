# Sources and Current Baseline

This skill was prepared on 2026-07-13. Check current docs before pinning versions.

## Primary documentation

- Codex Agent Skills: https://developers.openai.com/codex/skills
- Claude Code Skills: https://code.claude.com/docs/en/skills
- Claude Code Plugins and Hooks: https://code.claude.com/docs/en/plugins-reference and https://code.claude.com/docs/en/hooks
- Django download/support policy: https://www.djangoproject.com/download/
- django-tenants docs: https://django-tenants.readthedocs.io/
- django-tenant-users docs: https://django-tenant-users.readthedocs.io/
- django-multitenant docs: https://django-multitenant.readthedocs.io/
- django-pgschemas docs: https://django-pgschemas.readthedocs.io/
- OWASP Cheat Sheet Series (Authorization, IDOR prevention, Session Management): https://cheatsheetseries.owasp.org/

## Package baseline as of 2026-07-13

- Django latest official: 6.0.7 (security release 2026-07-07)
- Django conservative production baseline: 5.2 LTS (latest patch 5.2.16, supported through April 2028); use 6.0.x when the project already targets Django 6
- django-tenants: 3.10.2 on PyPI (2026-06-30; fixes the multiprocessing migration executor on spawn-default platforms; declares Django 4.2/5.2/6.0, Python >= 3.10)
- django-tenant-users: 2.2.1 on PyPI (declares Django 4.2–5.2 only — Django 6.0 support is unverified upstream; test explicitly if targeting 6.0)
- django-multitenant: 4.1.1 on PyPI — **caveat**: upstream declares support only through Django 4.2 and has shipped no functional release since 2023-12; verify against your Django version or prefer a plain `tenant_id` + PostgreSQL RLS design (references/04)
- django-pgschemas: 1.2.0 on PyPI (2025-12-23; actively maintained schema-per-tenant alternative, Django 5.2/6.0, Python >= 3.12)
- PostgreSQL: current majors 17.x / 18.x; no RLS behavior changes in 17/18; PG18 adds native `uuidv7()` (good default for new tenant-scoped keys) and faster `pg_upgrade` for many-schema clusters

Do not treat these as permanent. Agent must verify when current-version precision matters.
