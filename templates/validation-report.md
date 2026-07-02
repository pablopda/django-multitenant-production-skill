# Django Multi-Tenant Validation Report

Date: YYYY-MM-DD
Reviewer: <agent/user>
Repository/branch/commit: <identifier>
Verdict: Ready | Conditionally ready | Not ready

## Executive summary

<3-7 bullet summary of readiness and highest risks.>

## Detected tenancy model

- Model:
- Packages:
- Tenant locator:
- Auth/membership model:
- Confidence:

## Critical findings

| ID | Severity | Area | Finding | Evidence | Required fix |
|---|---|---|---|---|---|
| MT-001 | Critical/High/Medium/Low | | | | |

## Scorecard

Score each domain 0-3: `0` = absent or unsafe, `1` = partial with high-risk gaps, `2` = mostly implemented with some gaps, `3` = production-ready evidence present. A `0` in tenant context, data isolation, auth, or tests means not production-ready. Full rubric: `references/02-evaluation-scorecard.md`.

| Domain | Score 0-3 | Evidence | Notes |
|---|---:|---|---|
| Architecture and tenancy model | | | |
| Tenant context resolution | | | |
| Data isolation | | | |
| Authentication and authorization | | | |
| APIs and views | | | |
| Admin | | | |
| Background jobs/signals/commands | | | |
| Cache/sessions/rate limits | | | |
| Files/media/static/templates | | | |
| Migrations and data lifecycle | | | |
| Observability and audit | | | |
| Tests | | | |

## Validation performed

Commands run:

```bash
# paste commands
```

Tests reviewed or added:

- 

Manual checks:

- 

## Required fixes before production

1. 
2. 
3. 

## Recommended improvements

1. 
2. 
3. 

## Release decision

- Release blocker count:
- High-risk accepted items:
- Owner/date for each accepted risk:
- Final verdict:
