# Django Multi-Tenant Production Skill

A production-grade [Agent Skill](https://code.claude.com/docs/en/skills) for **evaluating, validating, building, repairing, and migrating Django multi-tenant SaaS applications** — with tenant isolation treated as an explicit, tested, observable, and hard-to-bypass property.

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

## Compatibility

The playbooks and scripts were written and validated against these baselines (see `references/99-sources-and-current-baseline.md`):

| Component | Baseline version | Notes |
|---|---|---|
| Django | 5.2 LTS (default) / 6.0.x | 5.2 LTS is the conservative default (supported through April 2028); use 6.0.x when the project already targets Django 6. |
| `django-tenants` | 3.10.1 | Schema-per-tenant isolation. |
| `django-tenant-users` | 2.2.1 | Global users with per-tenant permissions. |
| `django-multitenant` | 4.1.1 | Shared-schema (`tenant_id` / Citus). |
| Python | 3.10+ | Bundled scripts are standard-library only. |
| PostgreSQL | Required | Schema-per-tenant relies on PostgreSQL schemas; shared-schema RLS is PostgreSQL-specific. |

The skill re-checks your project's pinned versions before implementing; this table is the tested baseline as of **2026-06-09**.

---

## Install

### Claude Code

**Per project** (available in that repo only) — clone to a temp path so no stray checkout or `.git/` is left in the repo:

```bash
git clone --depth 1 https://github.com/pablopda/django-multitenant-production-skill.git /tmp/dmtp
mkdir -p .claude/skills
cp -R /tmp/dmtp .claude/skills/django-multitenant-production
rm -rf /tmp/dmtp .claude/skills/django-multitenant-production/.git
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
git clone https://github.com/pablopda/django-multitenant-production-skill.git ~/skills/django-multitenant-production-skill
mkdir -p ~/.agents/skills
ln -s ~/skills/django-multitenant-production-skill ~/.agents/skills/django-multitenant-production
```

> The skill's internal name is `django-multitenant-production` (from `SKILL.md` frontmatter). Name the installed directory to match.

### Verify the install

- **Claude Code**: type `/` and confirm `django-multitenant-production` appears in the list, or ask "what skills are available?".
- **Codex**: run `/skills` and confirm it is listed.

`SKILL.md` must sit **directly** at `.claude/skills/django-multitenant-production/SKILL.md` (or the `.agents/skills/...` equivalent). One extra nesting level — e.g. `.claude/skills/django-multitenant-production/django-multitenant-production-skill/SKILL.md`, which happens if you copy the repo folder *inside* the skill folder — makes the skill fail to load silently.

---

## Use it

It **auto-triggers** when a task matches its description (Django multi-tenant / multitenancy / tenant isolation / `django-tenants` / `django-tenant-users` / `django-multitenant` / schema-per-tenant / shared-schema `tenant_id` / B2B SaaS evaluate·validate·migrate·build). A plain natural-language mention works in **either runtime**:

```text
Use the django-multitenant-production skill to evaluate this Django SaaS app for tenant isolation risks.
```

You can also invoke it explicitly. The explicit-mention syntax differs per runtime:

**Claude Code** — slash form:

```text
/django-multitenant-production validate our django-tenants setup and propose production fixes.
```

**Codex** — `$` mention (or pick it from the `/skills` list):

```text
$django-multitenant-production validate our django-tenants setup and propose production fixes.
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

## Versioning

Changes are tracked in [CHANGELOG.md](./CHANGELOG.md) (Keep a Changelog format). The currency baseline lives in `references/99-sources-and-current-baseline.md`; its baseline date (currently **2026-06-09**) is bumped whenever the tested package versions change, and the compatibility table above and the changelog move with it.

---

## Contributing

Issues and PRs welcome — see [CONTRIBUTING.md](./CONTRIBUTING.md). The reference playbooks and the anti-patterns list are the most valuable places to add hard-won production lessons.

## License

[MIT](./LICENSE) © 2026 Pablo Perez De Angelis
