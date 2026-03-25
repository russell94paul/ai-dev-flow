# Example Feature: API Sync

## Input

ai feature "Build API sync feature"

---

## Grill Summary

- Clarified API endpoints
- Identified sync frequency
- Defined failure handling

---

## PRD (Summary)

Goal:
Synchronize data between systems X and Y.

Key requirements:
- retry logic
- idempotency
- logging

---

## Plan

1. Define sync interface
2. Implement API client
3. Add retry mechanism
4. Write tests

---

## Artifacts

```text
api-sync/
  PRD.md     ← written by `ai feature` after PRD phase
  plan.md    ← written by `ai feature` after PLAN phase
```

---

## TDD Phase

After plan is confirmed:

```bash
ai tdd "api-sync"
```

Reads `api-sync/plan.md` and implements via Claude Code CLI with git guardrails active.

---

## Notes

- GRILL/PRD/PLAN run in Claude chat; TDD runs in Claude Code CLI
- Edge cases discovered during grill phase
- Each TDD cycle: one failing test → minimal code to pass → repeat