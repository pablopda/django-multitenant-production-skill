# Django Multi-Tenant Production Skill

A production-grade [Agent Skill](https://docs.anthropic.com/en/docs/claude-code/skills) for **evaluating, validating, building, repairing, and migrating Django multi-tenant SaaS applications** — with tenant isolation treated as an explicit, tested, observable, and hard-to-bypass property.

It ships as a portable skill directory (`SKILL.md` + `references/` + `templates/` + `scripts/`) that works with both **Claude Code** (`.claude/skills/`) and **Codex / OpenAI agents** (`.agents/skills/`).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
![Skill](https://img.shields.io/badge/type-agent%20skill-blueviolet)
![Django](https://img.shields.io/badge/Django-5.2%20LTS%20default-092E20?logo=django)

---

## What it does

Classify the request into one or more **operating modes**, then act:

| Mode | What you get |
|------|--------------|
| **Evaluate** | Inspect an existing app/design → risk-ranked production-readiness scorecard. |
| **Validate** | Prove isolation with tests + static checks: tenant data isolation, auth/RBAC, migrations, async jobs, cache/session isolation, file/blob isolation, admin isolation, audit logging. |
| **Build** | Architecture selection → implementation → migration strategy → test generation → rollout/backout plan. |
| **Repair** | Fix an identified isolation, migration, auth, admin, background-job, cache, storage, or ops defect. |

### Opinionated defaults

- **Schema-per-tenant with [`django-tenants`](https://django-tenants.readthedocs.io/)** for typical B2B SaaS on PostgreSQL (shared DB / separate schema).
- **[`django-tenant-users`](https://github.com/Corvia/django-tenant-users)** when one global user account needs access to multiple tenants with different per-tenant permissions.
- **Shared-schema (`tenant_id` / Citus-style) playbook** via [`django-multitenant`](https://github.com/citusdata/django-multitenant) for large-scale shared-table designs.
- **Security-heavy validation** aligned with OWASP multi-tenant guidance: cross-tenant leakage, tenant-context injection, cache/session/file isolation, onboarding/offboarding, audit logging.

---

## What's inside

```
django-multitenant-production-skill/
├── SKILL.md                     # Main skill instructions (entry point)
├── README.md
├── LICENSE
├── agents/
│   └── openai.yaml              # Codex/OpenAI agent interface manifest
├── references/                  # Playbooks & checklists (loaded on demand)
│   ├── 01-architecture-decision-guide.md
│   ├── 02-evaluation-scorecard.md
│   ├── 03-django-tenants-playbook.md
│   ├── 04-shared-schema-playbook.md
│   ├── 05-auth-users-permissions.md
│   ├── 06-tenant-isolation-security.md
│   ├── 07-testing-validation-playbook.md
│   ├── 08-production-operations-runbook.md
│   ├── 09-migration-playbook.md
│   ├── 10-anti-patterns.md
│   └── 99-sources-and-current-baseline.md
├── templates/                   # Copy-paste starting points
│   ├── adr-tenancy-decision.md
│   ├── validation-report.md
│   ├── implementation-plan.md
│   ├── schema_tenant_isolation_test_template.py
│   └── shared_schema_isolation_test_template.py
└── scripts/                     # Standalone Python helpers (stdlib only)
    ├── tenant_static_audit.py
    ├── scaffold_django_tenants_app.py
    └── generate_tenant_isolation_tests.py
```

---

## Install

### Claude Code

**Per project** (available in that repo only):

```bash
git clone https://github.com/pablopda/django-multitenant-production-skill.git
mkdir -p .claude/skills
cp -R django-multitenant-production-skill .claude/skills/django-multitenant-production
```

**Globally** (available in every session) — symlink so the checkout stays the single editable source:

```bash
git clone https://github.com/pablopda/django-multitenant-production-skill.git ~/skills/django-multitenant-production-skill
mkdir -p ~/.claude/skills
ln -s ~/skills/django-multitenant-production-skill ~/.claude/skills/django-multitenant-production
```

Restart Claude Code so it picks up the new skill.

### Codex / OpenAI agents

Same layout under `.agents/skills/` (per repo) or `~/.agents/skills/` (global):

```bash
mkdir -p ~/.agents/skills
ln -s ~/skills/django-multitenant-production-skill ~/.agents/skills/django-multitenant-production
```

> The skill's internal name is `django-multitenant-production` (from `SKILL.md` frontmatter). Name the installed directory to match.

---

## Use it

It **auto-triggers** when a task matches its description (Django multi-tenant / tenant isolation / `django-tenants` / `django-tenant-users` / `django-multitenant` / B2B SaaS evaluate·validate·migrate·build). You can also invoke it explicitly:

```text
Use the django-multitenant-production skill to evaluate this Django SaaS app for tenant isolation risks.
```

```text
/django-multitenant-production validate our django-tenants setup and propose production fixes.
```

```text
Use django-multitenant-production to build a schema-per-tenant Django app with global users and per-tenant permissions.
```

---

## Included scripts

All three are dependency-free Python (3.10+) and run from the root of a Django repo.

### `tenant_static_audit.py` — static isolation audit

Flags common multi-tenant Django risk patterns. Conservative by design: it finds suspicious patterns, it does **not** prove security.

```bash
# Markdown report
python scripts/tenant_static_audit.py --root .

# JSON output (for tooling)
python scripts/tenant_static_audit.py --root . --format json

# CI gate: non-zero exit if any finding at/above a severity
python scripts/tenant_static_audit.py --root . --fail-on High
```

### `scaffold_django_tenants_app.py` — conservative `django-tenants` scaffold

Writes a minimal tenant app plus a settings snippet. Review before merging.

```bash
python scripts/scaffold_django_tenants_app.py \
  --root . --app customers --tenant-model Client --domain-model Domain
```

### `generate_tenant_isolation_tests.py` — starter isolation tests

```bash
# schema-per-tenant
python scripts/generate_tenant_isolation_tests.py --root . --mode schema

# shared-schema (tenant_id)
python scripts/generate_tenant_isolation_tests.py --root . --mode shared
```

Both scaffolders write starting points, not finished work — read and adapt the output.

---

## Baseline & currency

As of **2026-06-09**, the skill treats **Django 5.2 LTS** as the conservative default for new production SaaS projects (supported through April 2028), unless the repository already standardizes on Django 6.x. The skill always re-checks project dependencies and current package docs before implementing. See `references/99-sources-and-current-baseline.md`.

---

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md). The reference playbooks and the anti-patterns list are the most valuable places to add hard-won production lessons.

## License

[MIT](./LICENSE) © 2026 Pablo Perez De Angelis
