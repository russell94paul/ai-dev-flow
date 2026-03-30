# ai-dev-flow Integrated Development Guidelines
**Version:** 1.0.0
**Date:** 2026-03-30
**Basis:** ALDC Agentic Coding Guidelines v0.2 + ai-dev-flow v3 + Paperclip integration
**Scope:** Python and TypeScript stacks. Go, Java, and other languages are out of scope for v1.0; declare `devflow.yaml → stack: go` to get advisory-only mode.

---

## 0. Purpose

This document is the single versioned reference for:
1. Why the rules exist (empirical basis)
2. What the rules require (normative statements)
3. Where enforcement lives (code pointer)
4. What is advisory vs. what is a hard gate

Agents read this to understand intent. Humans read this to audit coverage and adjust thresholds after retrospectives.

---

## 1. Philosophy and Empirical Basis

### 1.1 Why These Rules Exist

Autonomous agents fail in predictable ways. The rules in this document are calibrated against observed failure rates:

| Metric | Value | Implication |
|---|---|---|
| Agent first-attempt success rate | ~33% | Plan-verify cycles are not overhead — they are the baseline recovery mechanism |
| AI-co-authored security vulnerability rate | 2.74× human rate | Every changed file matching a security trigger pattern must be reviewed by the security-review skill (Opus tier) |
| Token savings in healthy code | ~50% | Clean, well-tested code reduces context consumption in subsequent phases — Iron Law is a forcing function, not a formality |
| Context quality degradation threshold | ~40% utilisation | Above this threshold, agent output quality degrades. Proxy signals replace direct measurement; `devflow orient` warns when proxies are exceeded |

### 1.2 Core Principles

1. **Enforce by code, not documentation.** Gates return exit codes. Artifacts are validated by schema. Advice that cannot be checked is not a gate.
2. **Single-purpose skills.** A skill does one thing and produces one artifact. Agents orchestrate; skills execute.
3. **AGENTS.md is declarative.** It lists what to call and when. All logic lives in skills or CLI commands.
4. **Every gate has a recovery path.** A blocking failure must produce a recovery action — not just a comment.
5. **Context isolation.** Each agent phase starts clean. No phase inherits the context pollution of a prior phase.
6. **Artifact-first verification.** Phase completion is defined by artifact presence + content validity, not agent self-report.

---

## 2. Workflow Phases

### 2.1 Phase Lifecycle

Every feature follows this pipeline. Each transition is gated by `devflow gate` and sealed by `devflow seal`.

```
orient → grill → prd → plan → build → review → qa [+ security] → deploy → done
```

| Phase | Agent | Gate (entering) | Seal (completing) |
|---|---|---|---|
| orient | any | — | — |
| grill | devflow-feature | — | state.grill_complete: true |
| prd | devflow-feature | grill_complete | specs/prd.md schema |
| plan | devflow-feature | prd_complete + prd.md present | plans/plan.md schema |
| build | devflow-builder | plan_approved + plan.md present | Iron Law regex + tdd-summary.md |
| review | devflow-reviewer | iron_law_met + tdd-summary.md | review-report.md Decision field |
| qa | devflow-qa | review_passed + review-report.md | evidence.md schema + coverage threshold |
| security | devflow-qa | (parallel with qa — always allowed when qa starts) | security-review.md max_severity field |
| deploy | devflow-sre | max_severity ≤ medium OR waiver + evidence.md present | deploy-steps.md schema |
| done | devflow-sre | artifact_contract_met: true + manifest present | — |

Full gate and seal preconditions: `docs/artifact-contract.md`.

### 2.2 Artifact Stack

Every completed feature must have all of the following:

| Artifact | Path | Phase | Blocking upload |
|---|---|---|---|
| PRD | `specs/prd.md` | prd | no |
| Plan | `plans/plan.md` | plan | no |
| TDD Summary | `build/tdd-summary.md` | build | no |
| Review Report | `ops/review-report.md` | review | no |
| QA Evidence | `qa/evidence.md` | qa | no |
| Security Review | `qa/security-review.md` | security (if triggered) | no |
| Deploy Steps | `ops/deploy-steps.md` | deploy | no |
| Connector Checklist | `ops/connector-checklist.md` | build (connector only) | no |
| Verification Manifest | `ops/verification-manifest.json` | done | yes |

Canonical definitions: `devflow/contract.py → ARTIFACTS`.

---

## 3. Context Management

### 3.1 The 40% Rule (Advisory)

Direct context utilisation measurement is not available to agents. The rule is preserved as advisory guidance. Enforcement uses proxy signals detected by `devflow orient`:

| Proxy signal | Warning threshold | Action |
|---|---|---|
| Session age | > 2 hours | Summarise and restart |
| Heartbeat count | > 10 | Checkpoint; consider fresh context |
| Fix-break-fix | > 5 edits to same file | Post warning; recommend fresh context |
| Unread inbox | Any unread Paperclip comments | Read before continuing |
| Opus without justification | `model_tier = opus` with no `model_tier_justification` | Post reminder |

These are warnings, not gates. A devflow-ceo agent watching heartbeat counts acts on them.

### 3.2 Context Isolation Per Phase

Each agent phase must start in a clean context:

- `devflow-reviewer` reads **only**: `specs/prd.md`, `plans/plan.md`, `build/tdd-summary.md`, git diff. It must not be given build-phase conversation history.
- `devflow-qa` reads security-review.md from a fresh context — not from the builder's session.
- `devflow-sre` reads evidence.md and security-review.md — no prior agent history.

This is structural, not advisory. An agent that inherits context from a prior phase is violating the isolation requirement.

---

## 4. Iron Law

### 4.1 What It Is

No code ships without passing tests. This is not a suggestion.

**Iron Law requirements (all must be met at build seal):**

1. `build/tdd-summary.md` must contain a `## Test Output` section with verbatim test runner output
2. That output must match one of these patterns:
   ```
   PASSED \d+
   GREEN \d+
   \d+ passed
   ```
3. No `# type: ignore` or `# noqa` without an inline explanation comment on the same line
4. No commented-out code blocks
5. No new functions or classes added without at least one test covering them

**Enforcement:** `devflow seal --completing build` validates all five. Failure is non-waivable (`iron-law` gate).

### 4.2 Why Verbatim Output

Agents are capable of writing plausible-looking test summaries that do not reflect actual test runs. The Iron Law regex exists specifically to make fabrication detectable. A correct test summary looks like:

```
PASSED 47
```

or

```
47 passed in 2.31s
```

The regex `\d+ passed` or `PASSED \d+` is intentionally minimal. It matches real pytest/jest/unittest output and does not match freeform prose.

---

## 5. Tier System

### 5.1 Tier Definitions

| Tier | Minimum test types | When required |
|---|---|---|
| 1 | Syntax checks + unit tests | Bug fixes, small utilities |
| 2 | Unit + integration tests | New features (default) |
| 3 | Unit + integration + end-to-end or contract tests | Connectors (mandatory), APIs with external consumers |

The `**Tier:**` field in `qa/evidence.md` declares which tier was applied. `devflow seal --completing qa` validates the field is present and is one of `1`, `2`, `3`.

### 5.2 Coverage Thresholds

| Feature type | Threshold | Waivable? |
|---|---|---|
| New feature | ≥ 70% | Yes — `coverage-threshold` GATE-WAIVER |
| Bug fix | ≥ 60% | Yes — `coverage-threshold` GATE-WAIVER |
| Refactor | Non-decreasing | Yes — `coverage-threshold` GATE-WAIVER |
| Connector | ≥ 70% (Tier 3 mandatory) | Yes for percentage; Tier 3 is non-waivable |

Coverage is written to `qa/evidence.md` as `**coverage_pct:** <number>`. The seal reads this field directly.

---

## 6. Writer/Reviewer Protocol

### 6.1 Why Separate Agents

The reviewer must not have seen the code being written. Cognitive debt, OWASP findings, and over-engineering are easiest to spot by a reader who lacks the builder's context. An agent that wrote the code cannot reliably review it.

### 6.2 Reviewer Constraints

`devflow-reviewer` receives only:
- `specs/prd.md`
- `plans/plan.md`
- `build/tdd-summary.md`
- `git diff` of the feature branch

It does not receive build-phase conversation history, the builder's scratch notes, or intermediate artifacts.

### 6.3 Review Checklist

All six items must appear in `ops/review-report.md`. FAIL on any unresolved item:

| Item | FAIL condition |
|---|---|
| Cognitive debt | Any function unexplainable in one sentence, not addressed |
| OWASP scan | Any finding not addressed |
| AC coverage | Any Acceptance Criterion without a test or explicit out-of-scope note |
| git blame | Any prior fix reverted by this diff |
| Iron Law | tdd-summary.md test output does not match Iron Law regex |
| No over-engineering | Any new abstraction with < 2 use cases in the diff |

---

## 7. Security

### 7.1 Trigger Rules

The security-review skill runs automatically when any changed file matches a trigger pattern. Default patterns cover auth, middleware, data models, new API endpoints, external integrations, data migrations, and PRD keyword matches (auth, PII, payment, credentials, secret).

Full trigger list: `docs/artifact-contract.md §4`.

### 7.2 Severity Gate

| max_severity | Deploy gate | Recovery |
|---|---|---|
| none / low | Pass | Log in security-review.md |
| medium | Pass with comment | Post to Paperclip issue |
| high | Block deploy | Post + `@<waiver-authority>`; resolved by GATE-WAIVER |
| critical | Hard block | Escalate to team; human PATCH to state required |

Critical severity (`security-severity-critical`) is non-waivable. It cannot be bypassed by a GATE-WAIVER comment.

### 7.3 Model Tier

Security review requires the Opus model tier. An agent running security review at Haiku or Sonnet tier is in violation of this guideline. The `**sign_off:**` field in `qa/security-review.md` records which agent ID performed the review.

---

## 8. Connectors

### 8.1 Connector Contract

A connector feature (`state.feature_type = connector`) must produce all nine components:

| # | Component | Enforcement |
|---|---|---|
| 1 | Schema definition (`schemas.py` or `schemas/`) | Seal file-pattern check |
| 2 | SchemaValidationError on invalid input | connector-build skill |
| 3 | Idempotency key on all write operations | Seal grep: `idempotency_key` or `x-idempotency-key` |
| 4 | Idempotency test (duplicate input → single output) | connector-build skill |
| 5 | Contract test (`*contract*test*` or `*test*contract*` file) | Seal file-pattern check |
| 6 | Structured logging (records_extracted, records_loaded, errors_skipped) | connector-build skill |
| 7 | Retry configuration (`retries=` in connector source) | connector-build skill |
| 8 | Observability artifact export | connector-build skill |
| 9 | Connector README (≥ 3 sections) | connector-build skill |

All nine rows must be `PASS` in `ops/connector-checklist.md` for the build seal to pass.

### 8.2 Connector QA

Tier 3 is mandatory. The `qa/evidence.md` must contain a `## Connector QA` section with contract test results. The deploy gate checks for this section explicitly.

---

## 9. Waiver Protocol

### 9.1 What Can Be Waived

| Gate | Waivable? | Who can grant |
|---|---|---|
| coverage-threshold | Yes | Any human (or configured waiver-authority) |
| mermaid-diagrams | Yes | Any human (or configured waiver-authority) |
| security-severity (high) | Yes | waiver-authority only |
| iron-law | No | — |
| artifact-contract | No | — |
| reviewer-fail | No | — |
| security-severity-critical | No | — |

### 9.2 GATE-WAIVER Format

Post this comment on the Paperclip issue (not on a subtask):

```
GATE-WAIVER
gate: security-severity
reason: External pentest scheduled for next sprint; findings tracked in ANA-99.
approved-by: <username>
expires: YYYY-MM-DD
```

All four fields are required. `devflow gate` validates:
1. `gate` is in the waivable set
2. Comment was posted by a human (not an agent)
3. `approved-by` is in `governance.waiver_authority` (or authority list is empty → permissive)
4. `expires` is a valid date that has not passed

### 9.3 Waiver Authority Configuration

```yaml
# devflow.yaml
governance:
  waiver_authority:
    - paulrussell
    - teamlead
```

If `waiver_authority` is absent or empty, any human commenter can grant a waiver. Teams processing compliance-sensitive features should configure the allowlist.

---

## 10. Model Tier Routing

| Tier | Model | Use when |
|---|---|---|
| Haiku | claude-haiku-4-5 | Orient, state reads, short planning tasks |
| Sonnet | claude-sonnet-4-6 | Default — PRD, plan, build, review, deploy |
| Opus | claude-opus-4-6 | Security review (mandatory); complex multi-file refactors |

Opus tier requires `state.model_tier_justification` to be set. `devflow orient` warns when Opus is declared without justification. CEO checks on next heartbeat and posts a reminder if > 2 unjustified Opus runs per feature.

---

## 11. Preserved v2 Practices

These practices from ai-dev-flow v2 are retained in v3 and are normative.

### 11.1 Vertical Slice / Tracer Bullet TDD

Build the thinnest possible end-to-end path first. Do not build components in isolation and integrate later. The first passing test should exercise the whole call stack from entry point to persistence (or its test double).

This maps to `plans/plan.md § Phases` — Phase 1 should always be the tracer bullet.

### 11.2 Heartbeat + State Checkpoint

Agents must write a heartbeat to Paperclip at regular intervals. State is the source of truth for phase position. An agent that crashes mid-phase is recoverable because the state document records the last-known gate/seal status.

`heartbeat_count` in state is a proxy for session age. CEO triggers a warning at > 10.

### 11.3 Devflow YAML Project Config

Every repo using ai-dev-flow must have a `devflow.yaml` at the repo root. Minimum required fields:

```yaml
project:
  slug: <repo-slug>
deploy:
  steps:
    - name: run migrations
      command: alembic upgrade head
```

Optional governance and security override fields documented in `docs/artifact-contract.md`.

---

## 12. Metrics and Health

`devflow metrics` aggregates across all features in the Paperclip project.

| Metric | Target |
|---|---|
| Iron Law compliance | ≥ 90% (% features where iron_law_met: true) |
| Artifact contract compliance | 100% (all artifacts present before done seal) |
| Average coverage | ≥ 70% (mean of coverage_pct across features) |
| Waiver rate | < 20% (waivers.count / total features) |
| Security escalations | Track; no hard target for v1.0 |

---

## 13. Out of Scope (v1.0)

- Go, Java, Rust, and other language stacks
- Mobile / React Native features
- Database migrations that modify > 10,000 existing rows (treat as a separate feature with a dedicated migration plan)
- Multi-repo features spanning more than one Paperclip project

---

## 14. Versioning and Retrospective

This document is versioned using semver. The version field at the top of this file is the authoritative version.

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-03-30 | Initial version — WS16 baseline, covers WS1–WS15 |

After every 10 completed features, run a retrospective:
1. Review `devflow metrics --summary` against targets in §12
2. Adjust thresholds where empirical data diverges from targets
3. Capture new failure patterns not covered by existing gates
4. Increment version and commit with message: `docs: guidelines vX.Y.Z — <retrospective summary>`

---

*For enforcement code see: `devflow/gatekeeper.py`, `devflow/waivers.py`, `devflow/contract.py`.*
*For artifact schemas see: `docs/artifact-contract.md`.*
*For ALDC requirement traceability see: `docs/guidelines-traceability.md`.*
