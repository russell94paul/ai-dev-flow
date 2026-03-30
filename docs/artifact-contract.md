# Artifact Contract
**Version:** 1.0 — WS3 baseline
**Purpose:** Defines the required artifacts at each pipeline phase, their schemas (required sections/fields), pass/fail thresholds, and security trigger rules. `devflow gate` and `devflow seal` validate against this document.

---

## 0. File Path Conventions

All artifact paths are relative to the feature root: `features/<slug>/`

| Phase | Artifact file | Key |
|---|---|---|
| PRD | `specs/prd.md` | `prd` |
| Plan | `plans/plan.md` | `plan` |
| Build | `build/tdd-summary.md` | `tdd-summary` |
| Review | `ops/review-report.md` | `review-report` |
| QA | `qa/evidence.md` | `evidence` |
| Security | `qa/security-review.md` | `security-review` |
| Deploy | `ops/deploy-steps.md` | `deployment` |
| Connector (conditional) | `ops/connector-checklist.md` | `connector-checklist` |
| Manifest | `verification-manifest.json` | — |

Artifacts are published to Paperclip issue documents using the `key` column above via `devflow publish-artifacts`.

---

## 1. Phase Gate Preconditions

`devflow gate --entering <phase>` checks these before any phase work begins. Gate is **read-only** — it never writes.

| Entering phase | State field required | Artifact required |
|---|---|---|
| Grill | — | — |
| PRD | `state.grill_complete: true` | — |
| Plan | `state.prd_complete: true` | `specs/prd.md` (passes schema) |
| Build | `state.plan_approved: true` | `plans/plan.md` (passes schema) |
| Review | `state.iron_law_met: true` | `build/tdd-summary.md` |
| QA | `state.review_passed: true` | `ops/review-report.md` |
| Security | (parallel with QA — always allowed when QA starts) | — |
| Deploy | `state.max_severity ≤ medium` OR waiver present | `qa/evidence.md`, `qa/security-review.md` (if triggered) |
| Done | `state.artifact_contract_met: true` | `verification-manifest.json` |

**Connector extra gate checks** (only when `state.feature_type = connector`):

| Entering phase | Extra check |
|---|---|
| Build | `connectors/<name>/` scaffold directory exists |
| Deploy | `qa/evidence.md` contains a `## Connector QA` section; contract test result = PASS |

---

## 2. Phase Seal Requirements

`devflow seal --completing <phase>` validates artifacts after phase work. Seal **writes** `verification-manifest.json` on pass.

### Grill

| Field | Requirement |
|---|---|
| `state.grill_complete` | Must be set to `true` |

### PRD — `prd/prd.md`

| Required section | Notes |
|---|---|
| `## Goal` | One-paragraph statement of what this achieves |
| `## Background` | Why now; context and motivation |
| `## Scope` | What is in and out of scope |
| `## Acceptance Criteria` | Numbered list; each item testable |
| `## Security Scope` | Explicitly states whether security review is triggered and why |

Conditional section:

| Section | Required when |
|---|---|
| `## API Contract` | PRD creates or changes any HTTP endpoint |

### Plan — `plans/plan.md`

| Required section | Notes |
|---|---|
| `## Phases` | Ordered list of implementation phases |
| `## ADRs` | Required when architectural decisions are present; may be `N/A — no architectural decisions` |
| `## Rollback` | ≥ 1 rollback step (how to undo this change in production) |
| `## Verification Commands` | ≥ 1 command to confirm the feature works post-deploy |

Diagram requirement:
- ≥ 2 Mermaid diagrams present (or `## Diagrams — N/A` with justification)
- If diagrams present: seal validates Mermaid syntax via `mmdc --input` dry-run or equivalent

### Build — `build/tdd-summary.md`

| Required section | Notes |
|---|---|
| `## Test Output` | Verbatim output from test runner |

Iron Law regex (seal validates test output section matches one of):
```
PASSED \d+
GREEN \d+
\d+ passed
```

State field written by seal on pass: `state.iron_law_met: true`

Iron Law checklist (seal fails if any item unresolved):
- No `# type: ignore` or `# noqa` without an inline explanation comment
- No commented-out code blocks
- No functions/classes added without at least one test covering them

### Review — `ops/review-report.md`

| Required field | Valid values |
|---|---|
| `**Decision:**` | `PASS` or `FAIL` |

| Required section | Notes |
|---|---|
| `## Checklist` | Table with Item / Status / Notes columns |
| `## Findings` | Required if Decision = FAIL; list of findings with file:line references |

Checklist items (all must be present):

| Item | FAIL condition |
|---|---|
| Cognitive debt | Any function unexplainable in one sentence, unfixed |
| OWASP scan | Any finding not addressed |
| AC coverage | Any Acceptance Criterion without a test or explicit out-of-scope note |
| git blame | Any prior fix reverted by this diff |
| Iron Law | tdd-summary test output does not match Iron Law regex |
| No over-engineering | Any new abstraction with < 2 use cases in the diff |

State field written by gate on Review PASS: `state.review_passed: true`

### QA — `qa/evidence.md`

| Required field | Notes |
|---|---|
| `**Tier:**` | `1`, `2`, or `3` (see tier definitions below) |
| `**coverage_pct:**` | Numeric percentage (e.g. `74.2`) |

| Required section | Notes |
|---|---|
| `## Test Output` | Verbatim test runner output |

**Coverage thresholds** (waivable with `GATE-WAIVER` in state):

| Feature type | Threshold |
|---|---|
| New feature | ≥ 70% |
| Bug fix | ≥ 60% |
| Refactor | Non-decreasing (coverage_pct ≥ baseline recorded in prior seal) |

**Tier definitions:**

| Tier | Minimum test types |
|---|---|
| 1 | Syntax checks + unit tests only |
| 2 | Unit + integration tests |
| 3 | Unit + integration + end-to-end or contract tests |

Connector feature minimum: Tier 3 (contract tests required).

Optional section (captured; not a gate):
- `## Performance Baseline` — latency or throughput numbers for regression tracking

### Security — `ops/security-review.md`

| Required field | Valid values |
|---|---|
| `**max_severity:**` | `none`, `low`, `medium`, `high`, `critical` |
| `**sign_off:**` | Agent ID or `human:<name>` |

State field written by seal: `state.max_severity`

**Severity gate:**

| max_severity | Gate action | Notification |
|---|---|---|
| `none` / `low` | Pass | Log in security-review.md |
| `medium` | Pass with comment | Post to Paperclip issue |
| `high` | Block deploy | Post comment + `@<waiver-authority>` |
| `critical` | Hard block | Post comment + `devflow /msg <team>` (fallback: `ESCALATION-REQUIRED` comment) |

### Deploy — `ops/deploy-steps.md`

| Required section | Minimum content |
|---|---|
| `## Steps` | ≥ 1 executed step with timestamp |
| `## Rollback` | ≥ 1 rollback command or procedure |
| `## Health Checks` | ≥ 1 command run post-deploy with output |

### Connector Checklist (conditional) — `ops/connector-checklist.md`

Only required when `state.feature_type = connector`. Seal checks all rows = `PASS`.

| Check | Validated by |
|---|---|
| `connector-checklist.md` present | Seal file presence check |
| All checklist rows = PASS | Seal table parse |
| `schemas.py` file detected | Seal file-pattern check |
| Contract test file detected | Seal file-pattern check (`*contract*test*` or `*test*contract*`) |
| Idempotency key pattern detected | Seal grep: `idempotency_key` or `x-idempotency-key` in connector source |

---

## 3. Verification Manifest — `verification-manifest.json`

Written by `devflow seal` after each phase passes. Structure:

```json
{
  "schema_version": "v3",
  "feature_slug": "<slug>",
  "issue_id": "<uuid>",
  "phases": {
    "<phase>": {
      "sealed_at": "<ISO-8601>",
      "artifacts": ["<relative-path>", "..."],
      "thresholds": {
        "coverage_pct": 74.2,
        "iron_law_met": true,
        "max_severity": "low"
      },
      "waivers": []
    }
  }
}
```

`devflow gate --entering done` checks `verification-manifest.json` is present and all expected phases have a seal record.

---

## 4. Security Trigger Rules

`devflow-qa` runs the security-review skill when **any** changed file matches a trigger pattern. Projects can extend or narrow rules via `devflow.yaml` under `security.trigger_patterns`.

### Default Trigger Patterns

| Category | Patterns |
|---|---|
| Auth / identity | `*auth*`, `*login*`, `*password*`, `*token*`, `*jwt*`, `*session*`, `*permission*`, `*credential*` |
| Middleware / guards | `*middleware*`, `*interceptor*`, `*guard*`, `*policy*` |
| Data model / schema | `migrations/`, `*/models.py`, `*.sql`, `*schema*`, `*/entities/*` |
| New API endpoints | Files matching route registration regex: `@app\.route\|router\.(get\|post\|put\|delete\|patch)\|path\(` |
| External integrations | `*webhook*`, `*integration*`, `*connector*`, `*callback*` |
| Data migrations | `*/migrations/*`, `*migrate*`, `*seed*`, `*fixtures*` |
| PRD keyword fallback | `auth`, `PII`, `payment`, `credentials`, `secret` present in `prd/prd.md` body |

Note: data migrations and schema migrations are separate categories — a data migration touching millions of rows carries different OWASP risk (injection, data exposure) from a DDL-only schema change.

### Per-repo Override (devflow.yaml)

```yaml
security:
  trigger_patterns:
    add:
      - "src/payments/**"
    remove:
      - "*webhook*"
```

---

## 5. Waiver Protocol

A waiver allows a threshold failure to proceed. Waivers are recorded in `verification-manifest.json` under the relevant phase and must be present before `devflow gate` will pass a blocked phase.

| Waiver type | Who can grant | How recorded |
|---|---|---|
| Coverage below threshold | Any agent (self-waiver) | `state.waivers[].type = coverage` + justification |
| Mermaid diagram not applicable | Any agent | `state.waivers[].type = diagrams` + justification |
| Security high severity | `waiver-authority` (human or designated agent) | `GATE-WAIVER` comment on Paperclip issue |
| Security critical severity | Human only | PATCH to issue state by human; confirmed by seal |

---

## 6. Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-03-30 | Initial version — WS3 baseline |
