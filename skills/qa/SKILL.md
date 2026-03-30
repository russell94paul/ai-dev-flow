---
name: qa
description: Run the QA test suite, measure coverage, and produce qa/evidence.md. Use when the QA phase begins, the user asks for QA evidence, or devflow gate reports review_passed is set and QA has not yet run.
---

# QA

Produces `qa/evidence.md` for the current feature. Called by `devflow-qa` during the QA phase.

## Tier model

Every feature is tested at one of three tiers. Declare the tier in the evidence artifact.

| Tier | Description | When to use |
|---|---|---|
| 1 | Unit tests only — no I/O, no network, no database | Purely algorithmic changes; no external dependencies |
| 2 | Integration tests — real databases, real APIs (or realistic stubs), no browser | Most backend features; the default for new_feature and connector |
| 3 | End-to-end tests — browser or full system stack | User-facing flows, UI changes, or acceptance-test scenarios required by the PRD |

Choose the **lowest tier that gives meaningful confidence**. Do not jump to Tier 3 for everything — it slows the pipeline. If the PRD acceptance criteria can be verified without a browser, use Tier 1 or 2.

## Coverage thresholds

| feature_type | Threshold | Check |
|---|---|---|
| `new_feature` | ≥ 70% | Hard gate — seal fails below threshold unless waived |
| `connector` | ≥ 70% | Hard gate |
| `bugfix` | ≥ 60% | Hard gate |
| `refactor` | Non-decreasing | Must be ≥ baseline recorded in state.baseline_coverage_pct |

Coverage is **line coverage** by default (Python: `coverage.py`; TypeScript: `nyc`/`c8`). Projects can override via `devflow.yaml`:

```yaml
qa:
  coverage_command: "pytest --cov=src --cov-report=term-missing"
  coverage_pct_regex: "TOTAL.*?(\\d+)%"
```

## Process

### Step 1: Confirm inputs

```
[ ] Review specs/prd.md — Acceptance Criteria (what must pass)
[ ] Review plans/plan.md — Verification Commands (commands specified by planner)
[ ] Check state.feature_type to select tier and coverage threshold
[ ] Check state.baseline_coverage_pct if feature_type = refactor
```

### Step 2: Determine tier

Choose the tier appropriate for this feature. Document the choice in `qa/evidence.md`.

### Step 3: Run tests

Run the full test suite. Use the commands from `plans/plan.md § Verification Commands` as your starting point, then extend as needed.

**Python (default):**
```bash
pytest -v 2>&1 | tee /tmp/qa-output.txt
coverage run -m pytest && coverage report --show-missing
```

**TypeScript (default):**
```bash
npx jest --coverage 2>&1 | tee /tmp/qa-output.txt
```

Copy the verbatim terminal output — you will paste it into `## Test Output`.

### Step 4: Measure coverage

Extract `coverage_pct` from the coverage report output. Record the numeric value (no `%` symbol).

Check against the threshold for this `feature_type`. If below threshold:
- Apply `--waive-coverage` only if there is a documented reason (technical debt, legacy module, etc.)
- Waiver is recorded in `verification-manifest.json` under `waivers[]`
- Do **not** silently skip coverage measurement

### Step 5: Syntax checks

Run basic syntax validation on all files touched in the diff:

**Python:**
```bash
git diff <base-branch>..HEAD --name-only | grep '\.py$' | xargs python -m py_compile
```

**TypeScript:**
```bash
npx tsc --noEmit
```

### Step 6: Connector QA (when feature_type = connector)

When `state.feature_type = "connector"`:

1. Run contract test:
   ```bash
   pytest tests/connectors/test_<name>_contract.py -v
   ```
2. Run idempotency test (verifies same input produces same output, not duplicate rows):
   ```bash
   pytest tests/connectors/ -k "idempotency" -v
   ```
3. Record results under a `## Connector QA` section in `qa/evidence.md`
4. If contract test fails: post findings to Paperclip issue; note potential API contract breach in `qa/security-review.md` (data risk)

### Step 7: Write the artifact

Write `qa/evidence.md` (relative to the feature root). Overwrite on each run.

## Output artifact: `qa/evidence.md`

```markdown
# QA Evidence: <feature-slug>

**Tier:** <1|2|3>
**coverage_pct:** <numeric — e.g. 73.4>
**Timestamp:** <ISO 8601>
**feature_type:** <new_feature|bugfix|refactor|connector>
**coverage_threshold:** <70|60|non-decreasing>

## Test Summary

| Suite | Tests | Passed | Failed | Skipped |
|---|---|---|---|---|
| <suite name> | N | N | 0 | N |

## Test Output

```
<verbatim test runner output — copy-paste exactly, do not summarise>
```

## Coverage Report

```
<verbatim coverage output>
```

## Syntax Checks

| File | Check | Result |
|---|---|---|
| <file.py> | py_compile | PASS |
| <file.ts> | tsc --noEmit | PASS |

## Connector QA (if applicable)

| Test | Result | Notes |
|---|---|---|
| Contract test | PASS/FAIL | <detail> |
| Idempotency test | PASS/FAIL | <detail> |

## Acceptance Criteria Verification

| Criterion | Verified by | Status |
|---|---|---|
| 1. <AC text> | <test name> | PASS |

## Waivers (if any)

| Gate | Reason | Approved by |
|---|---|---|
| coverage-threshold | <reason> | <authority> |
```

**Fill every section. The `## Test Output` section must contain verbatim runner output — never a summary.**

## Seal validation

`devflow seal --completing qa` checks:
- `**Tier:**` field present
- `**coverage_pct:**` field present and numeric
- `## Test Output` section present
- Coverage threshold check against `feature_type` (waivable with `--waive-coverage`)

## Performance baseline (informational)

If the plan includes a performance target, capture a baseline timing in the `## Test Summary` table (e.g. p95 response time from a load test). This is recorded but not a hard gate at QA phase.
