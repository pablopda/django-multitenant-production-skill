# Contributing

Thanks for helping improve the Django Multi-Tenant Production Skill.

## Ways to contribute

- **Playbooks & checklists** (`references/`) — the highest-value area. Add concrete, production-tested guidance for `django-tenants`, shared-schema/`django-multitenant`, auth, migrations, ops, and security.
- **Anti-patterns** (`references/10-anti-patterns.md`) — real failure modes you've hit and how to detect/avoid them.
- **Scripts** (`scripts/`) — keep them **standard-library only** (no third-party deps) and Python 3.10+ compatible, so they run anywhere without install.
- **Templates** (`templates/`) — ADRs, validation reports, test skeletons.

## Ground rules

- Keep isolation guidance **security-first**: prefer explicit, testable, hard-to-bypass patterns.
- Cite sources for version-sensitive claims and update `references/99-sources-and-current-baseline.md` when the baseline changes (current default: Django 5.2 LTS).
- Don't add runtime dependencies to the scripts.
- Keep `SKILL.md` frontmatter (`name`, `description`) accurate — it drives auto-triggering.

## Workflow

1. Fork and branch.
2. Make focused changes with a clear rationale.
3. If you touch a script, run it against a sample Django repo and paste the output in the PR.
4. Open a PR describing the production problem your change addresses.
