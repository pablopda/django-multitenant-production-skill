# Sources and Current Baseline

This skill was prepared on 2026-06-09. Check current docs before pinning versions.

## Primary documentation

- Codex Agent Skills: https://developers.openai.com/codex/skills
- Claude Code Skills: https://code.claude.com/docs/en/skills
- Django download/support policy: https://www.djangoproject.com/download/
- django-tenants docs: https://django-tenants.readthedocs.io/
- django-tenant-users docs: https://django-tenant-users.readthedocs.io/
- django-multitenant docs: https://django-multitenant.readthedocs.io/
- OWASP Multi-Tenant Application Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html

## Package baseline as of 2026-06-09

- Django latest official: 6.0.6
- Django conservative production baseline: 5.2 LTS where long support matters; 6.0.x when project already targets Django 6
- django-tenants: 3.10.1 on PyPI
- django-tenant-users: 2.2.1 on PyPI
- django-multitenant: 4.1.1 on PyPI

Do not treat these as permanent. Agent must verify when current-version precision matters.
