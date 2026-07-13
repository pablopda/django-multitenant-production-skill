# Skill Evaluation Cases

Hand-maintained eval set for tuning the SKILL.md `description` (auto-trigger surface)
and checking mode classification. Run these prompts against a session with the skill
installed; compare with-skill vs without-skill answers when editing the description.
(If you use the `skill-creator` plugin, these cases are the seed corpus for its
`evals/evals.json` format.)

## Should trigger

| # | Prompt | Expected mode |
|---|--------|---------------|
| 1 | "Review our django-tenants app for tenant isolation issues before we onboard a big customer." | Evaluate |
| 2 | "Prove that tenant A can't read tenant B's invoices in this DRF API." | Validate |
| 3 | "We're converting our single-tenant Django CRM to serve multiple agencies. Plan it." | Build (migration) |
| 4 | "Add a workspace switcher so one user can belong to several organizations with different roles." | Build (django-tenant-users territory) |
| 5 | "Our Celery task updated another customer's records — find and fix the leak." | Repair |
| 6 | "Is schema-per-tenant or a tenant_id column better for ~20k small tenants on Postgres?" | Evaluate/Build (architecture decision) |
| 7 | "Set up django-multitenant with Citus for our shared-schema SaaS." | Build |
| 8 | "Our B2B SaaS stores each clinic's files under /media/uploads — is that safe?" | Evaluate (file isolation) |

## Should NOT trigger

| # | Prompt | Why not |
|---|--------|---------|
| 1 | "Why is my Django form not validating email addresses?" | Single-tenant Django question; no tenancy signal. |
| 2 | "Optimize this slow Django ORM query with select_related." | Performance, not tenancy. |
| 3 | "Set up pytest for my Django project." | Generic testing setup. |
| 4 | "My landlord tenant won't pay rent — draft a letter." | 'Tenant' in the real-estate sense. |
| 5 | "Deploy my Django app to Kubernetes with multiple replicas." | Multiple replicas ≠ multiple tenants. |

## Behavior checks (with the skill active)

1. **Schema-per-tenant heuristics**: given an idiomatic django-tenants view using
   `Model.objects.filter(...)`, the skill must NOT recommend adding a tenant FK filter
   (SKILL.md code-review heuristics) — it should verify middleware/search_path context instead.
2. **Pooler rule**: an evaluation of a django-tenants app deployed behind transaction-mode
   PgBouncer must produce a Critical finding and a "Not ready" verdict (rule 11 + scorecard).
3. **Fail-loud tests**: generated isolation tests must fail before implementation
   (`self.fail`/`pytest.fail` guards intact) and the report must not claim "verified by test"
   for unimplemented guards (references/07 acceptance language).
4. **Version re-check**: when asked to pin package versions, the skill must consult the
   project's own pins and note the baseline date in `references/99` rather than asserting
   the baseline as current truth.
