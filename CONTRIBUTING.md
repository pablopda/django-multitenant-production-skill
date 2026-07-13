# Contributing

Thanks for helping improve the Django Multi-Tenant Production Skill.

## Ways to contribute

- **Playbooks & checklists** (`references/`) — the highest-value area. Add concrete, production-tested guidance for `django-tenants`, shared-schema/`django-multitenant`, auth, migrations, ops, and security.
- **Anti-patterns** (`references/10-anti-patterns.md`) — real failure modes you've hit and how to detect/avoid them.
- **Scripts** (`scripts/`) — keep them **standard-library only** (no third-party deps) and Python 3.10+ compatible, so they run anywhere without install.
- **Templates** (`templates/`) — ADRs, validation reports, test skeletons.
- **Hooks** (`hooks/hooks.json` + `scripts/hooks/`) — plugin hooks must stay stdlib-only, gate on the SessionStart baseline so they are silent outside multi-tenant repos, and end in a silent exit 0 on any unexpected error (a hook bug must never break a user's session).
- **Tests** (`tests/`) — the self-test suite. Run `python3 -m unittest discover -s tests -t .` (pytest works too) before opening a PR; add a regression test for any script/template defect you fix.

## Ground rules

- Keep isolation guidance **security-first**: prefer explicit, testable, hard-to-bypass patterns.
- Cite sources for version-sensitive claims and update `references/99-sources-and-current-baseline.md` when the baseline changes (current default: Django 5.2 LTS).
- Don't add runtime dependencies to the scripts.
- Keep `SKILL.md` frontmatter (`name`, `description`) accurate — it drives auto-triggering.
- Frontmatter shape: only `name` and `description` are read by **both** Claude Code and Codex. The spec-defined optional fields `license`, `compatibility`, and (Claude Code only) `allowed-tools` are fine; don't add other custom top-level keys — unrecognized fields are silently ignored, so their content never reaches the model. Put anything else under `metadata:`. The structure tests enforce this.
- Doc consistency: if a change touches versions or file layout, update `references/99-sources-and-current-baseline.md`, the README compatibility table, the README file tree, and `CHANGELOG.md` in the same PR; keep `SKILL.md` `metadata.version` and `.claude-plugin/plugin.json` `version` in sync with the latest changelog entry (also test-enforced).

## Workflow

1. Fork and branch.
2. Make focused changes with a clear rationale.
3. If you touch a script, run it against a sample Django repo and paste the output in the PR.
4. Open a PR describing the production problem your change addresses.
