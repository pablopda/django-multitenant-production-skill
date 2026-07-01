# Django Multi-Tenant Implementation Plan

## Objective

<What we are building/refactoring.>

## Tenancy model

Chosen model:

Reason:

Rejected alternatives:

## Work plan

### Phase 1: Architecture and setup

- [ ] ADR accepted
- [ ] dependencies pinned
- [ ] settings updated
- [ ] tenant/domain or tenant key model added
- [ ] middleware/resolver added

### Phase 2: Auth and membership

- [ ] user model decision made
- [ ] membership model implemented
- [ ] tenant switching implemented
- [ ] permissions implemented
- [ ] invitation/owner flow implemented if needed

### Phase 3: Tenant-owned domain slice

- [ ] first tenant-owned model implemented/refactored
- [ ] tenant-aware manager/queryset or schema context verified
- [ ] API/admin scoped
- [ ] serializers ignore/reject posted tenant IDs

### Phase 4: Async/cache/files

- [ ] Celery tasks include tenant context
- [ ] management commands are tenant-aware
- [ ] cache keys are tenant-aware
- [ ] file paths/downloads are tenant-aware

### Phase 5: Validation

- [ ] tenant A/B isolation tests
- [ ] auth/RBAC tests
- [ ] admin tests
- [ ] task/command tests
- [ ] migration tests
- [ ] static audit reviewed

### Phase 6: Production rollout

- [ ] migration runbook
- [ ] backup/restore plan
- [ ] observability/audit logs
- [ ] feature flags if needed
- [ ] rollback/backout plan

## Acceptance criteria

- 

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| | | |
