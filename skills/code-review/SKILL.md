---
name: code-review
description: Perform the Writer/Reviewer pass and produce ops/review-report.md. Use when the review phase begins, the user asks for a code review, or devflow gate reports review_passed is not set.
---

# Code Review (Writer/Reviewer Pass)

Produces `ops/review-report.md` for the current feature. Called by `devflow-reviewer` during the Review phase.

## Context isolation

**This skill runs in a fresh Paperclip heartbeat.** Do not read the builder's prior context or conversation history. Load only:

1. `specs/prd.md` — Acceptance Criteria (the contract you are verifying)
2. `plans/plan.md` — Implementation plan (what was intended)
3. `build/tdd-summary.md` — TDD evidence (what was built + Iron Law status)
4. `git diff <base-branch>..HEAD` — the actual diff (what changed)

Do not read any other files unless a specific finding requires you to inspect a particular module in depth.

## Process

### Step 1: Load inputs

```
[ ] Read specs/prd.md → extract Acceptance Criteria as a numbered list
[ ] Read plans/plan.md → note intended phases and any ADR decisions
[ ] Read build/tdd-summary.md → note Iron Law status + test count
[ ] Run: git diff <base-branch>..HEAD
[ ] Note the feature_type from Paperclip state (connector or standard)
```

### Step 2: Run the checklist

Work through each item. Mark PASS, FAIL, or N/A. A single FAIL item makes the overall Decision = FAIL.

```
[ ] Cognitive debt
    For every new function or class: can you explain it in one sentence?
    If not → flag as cognitive debt. If the debt is unfixed → FAIL.

[ ] OWASP scan
    Light pass over changed files (complements the dedicated security-review skill; does not replace it).
    Look for: obvious injection vectors, hard-coded secrets, unvalidated user input reaching sensitive operations.
    Mark FAIL only on clear findings; defer deep analysis to security-review skill.

[ ] AC coverage
    For each Acceptance Criterion in specs/prd.md:
    — Is there ≥ 1 test covering it?
    — OR is it explicitly marked out-of-scope with a reason in tdd-summary.md?
    Any criterion with no test and no out-of-scope marking → FAIL.

[ ] git blame
    Run: git log <base-branch>..HEAD -- <each modified existing file>
    Check: has any prior bug fix been reverted by this diff?
    Check: has any logic been silently removed that other callers may depend on?
    Flag any suspect removal → reviewer judgement on PASS/FAIL.

[ ] Iron Law
    Verify: tdd-summary.md ## Test Output section contains one of:
      PASSED \d+  |  GREEN \d+  |  \d+ passed
    If Iron Law field in tdd-summary.md says FAIL → this item is FAIL.

[ ] No over-engineering
    Inspect new abstractions: does each have ≥ 2 concrete use cases in this diff?
    Any abstraction with only 1 use case (speculative) → flag for discussion.
    If the builder cannot justify it → FAIL.
```

### Step 3: Connector review (when feature_type = connector)

When `state.feature_type = "connector"`, append a **Connector-Specific Checks** section and check each item:

```
[ ] Schema Gate is genuinely first — no data processing before schema validation
[ ] Idempotency key is deterministic — same inputs always produce same key
[ ] Contract test covers all fields the flow depends on (not just "any response")
[ ] Retry config uses reasonable delay — not hammering a failing API
[ ] Observability: records_extracted + records_loaded both logged (not just one)
[ ] README explains how to run the flow manually (not just automated)
[ ] No silent exception swallowing in extract/load tasks
```

All connector items must be PASS for the overall Decision to be PASS.

### Step 4: Write the artifact

Write `ops/review-report.md` (relative to the feature root). Overwrite on each run.

## Output artifact: `ops/review-report.md`

```markdown
# Review Report: <feature-slug>

**Decision:** PASS | FAIL
**Reviewer:** devflow-reviewer
**Timestamp:** <ISO 8601>

## Checklist
| Item | Status | Notes |
|---|---|---|
| Cognitive debt | PASS/FAIL/N/A | <detail> |
| OWASP scan | PASS/FAIL/N/A | <detail> |
| AC coverage | PASS/FAIL/N/A | <detail> |
| git blame | PASS/FAIL/N/A | <detail> |
| Iron Law | PASS/FAIL | <e.g. "5 passed" found in ## Test Output> |
| No over-engineering | PASS/FAIL/N/A | <detail> |

## Findings (FAIL items)
| # | File:Line | Issue | Severity | Must-fix? |
|---|---|---|---|---|
| 1 | <file>:<line> | <description> | low/medium/high | yes/no |

*(Leave table empty if Decision = PASS.)*

## Acceptance Criteria Coverage
| Criterion | Test name | Status |
|---|---|---|
| 1. <AC text> | <test name or "out-of-scope: <reason>"> | Covered / Out-of-scope |

## Connector-Specific Checks (if applicable)
| Item | Status | Notes |
|---|---|---|
| Schema Gate first | PASS/FAIL/N/A | |
| Idempotency deterministic | PASS/FAIL/N/A | |
| Contract test scope | PASS/FAIL/N/A | |
| Retry delay reasonable | PASS/FAIL/N/A | |
| Observability complete | PASS/FAIL/N/A | |
| README runnable | PASS/FAIL/N/A | |
| No silent exceptions | PASS/FAIL/N/A | |
```

**Fill every row with real data. Do not leave placeholder text.**

## Seal validation

`devflow seal --completing review` checks:
- `**Decision:**` field is present and value is exactly `PASS` or `FAIL`
- `## Checklist` section is present

## After FAIL

If Decision = FAIL:
1. The Deploy gate will block QA start
2. `devflow-feature` reopens the Builder subtask with a comment quoting the findings table
3. The builder must fix all Must-fix = yes findings and re-run TDD (re-seal Build)
4. After builder re-seals, `devflow-reviewer` runs this skill again from Step 1 in fresh context

After PASS: `devflow-feature` updates state `review_passed: true` and activates the QA subtask.
