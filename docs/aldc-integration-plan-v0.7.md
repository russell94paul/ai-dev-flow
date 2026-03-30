# Plan: ALDC Guidelines Integration with ai-dev-flow + Paperclip
**Version:** 0.7 — connector gate/seal branch, CEO thresholds, cleanup ordering, connector README blocking, escalation prerequisites
**Goal:** Every Paperclip autonomous run ships production-quality code plus a complete, verified artifact stack: PRD, Plan, Technical Diagrams, Test Evidence, QA, Security Review, Deploy + Rollback, ADRs.

---

## 0. Core Design Principles

1. **Enforce by code, not documentation.** Gates return exit codes. Artifacts are validated by schema. Advice that cannot be checked is not a gate.
2. **Single-purpose skills.** A skill does one thing and produces one artifact. Agents orchestrate; skills execute.
3. **AGENTS.md is declarative.** It lists what to call and when. All logic lives in skills or CLI commands.
4. **Every gate has a recovery path.** A blocking failure must produce a recovery action — not just a comment.
5. **Context isolation.** Each agent phase starts clean. No phase inherits the context pollution of a prior phase.
6. **Artifact-first verification.** Phase completion is defined by artifact presence + content validity, not agent self-report.

---

## 1. Relationship to ai-dev-flow v2 + Prior v3 Drafts

### Preserved from v2

| v2 Component | Preserved? | Why |
|---|---|---|
| Grill → PRD → Plan → TDD → QA → Deploy phase structure | ✓ | Validated; phases map cleanly to agent roles |
| `skills/*/SKILL.md` modular skill pattern | ✓ | Correct abstraction; composable |
| Vertical slice / tracer bullet TDD | ✓ | Best-practice; added to integrated standard |
| `devflow.yaml` manifest-driven project config | ✓ | Flexible per-project config; schema extended, not replaced |
| Paperclip heartbeat + state checkpoint pattern | ✓ (extended) | Proven mechanism |
| `devflow-feature` subtask creation pattern | ✓ (extended) | Adding Reviewer + Security subtasks |
| `session.json` conversation persistence | ✓ | Still needed for resumable human sessions |
| `tdd-summary.md`, `evidence.md` artifact files | ✓ (extended) | Content requirements tightened |

### Retired or Reimagined

| v2 Component | Verdict | Reason |
|---|---|---|
| `devflow-feature` as all-in-one agent | ✗ Retired | Unmaintainable monolith; split into scoped agents |
| Phase A GUI/AutoHotkey as primary path | ~ Reimagined | Still supported; Paperclip-native path is now first-class |
| No security review step | ✗ Retired | OWASP risk for autonomous deploy |
| No architecture diagram requirement | ✗ Retired | Missing artifact; now required |
| Implicit "done" (self-reported) | ✗ Retired | Replaced by gatekeeper (artifact-validated completion) |
| Single model for all tasks | ✗ Retired | Model tier routing; enforced via state metadata |

### Migration: v2 Issues to v3

`devflow sync <issue-id> --migrate-v3` — explicit migration command:

1. Fetch current issue state from Paperclip (`GET /issues/{id}/documents/state`)
2. Read `phase` field. Map old phase names to v3 names:
   | v2 phase | v3 phase | Notes |
   |---|---|---|
   | `grill` | `grill` | No change |
   | `prd` | `prd` | No change |
   | `plan` | `plan` | No change |
   | `build` / `tdd` | `build` | Unified name |
   | `qa` | `qa` | No change |
   | `deploy` | `deploy` | No change |
3. For each artifact expected at the current phase (per `docs/artifact-contract.md`), check if local file exists:
   - If present: validate against schema; note any missing sections in `migration-report.md`
   - If absent: write a stub file with `# [STUB — migrated from v2, requires completion]` header
4. Check which new v3 artifacts are not yet expected at this phase (e.g., security-review not due until QA). Mark them as `pending` in state, not missing.
5. Write `features/<slug>/ops/migration-report.md` — lists what was found, mapped, stubbed, or skipped.
6. Print reconciliation summary. Without `--apply` flag, makes no state changes (dry-run).
7. With `--apply`: update state document to v3 schema, upload stubs to Paperclip, post migration comment.

Partially-complete artifacts: if a local artifact exists but fails schema validation (missing required sections), stub fills only the missing sections and marks them `# [STUB — migration]`. Existing content is preserved.

---

## 2. Traceability Matrix

**Output:** `docs/guidelines-traceability.md`
**Do this first** — it is the scope audit trail.

| ALDC Section | Covered? | Artifact | Action |
|---|---|---|---|
| §2 Orient | Partial | None | Add `devflow orient` + Orient protocol in AGENTS.md |
| §2 Plan | ✓ prd-to-plan skill | `plans/plan.md` | Add: diagrams, ADRs, rollback, verification commands |
| §2 Implement | ✓ tdd skill | `build/tdd-summary.md` | Add: Iron Law gate, git-blame, cognitive debt, bug-pattern |
| §2 Verify | Partial | `qa/evidence.md` | Add: Tier 1/2/3, coverage %, syntax checks |
| §2 Commit & Communicate | Partial | `ops/deploy-steps.md` | Add: rollback, health checks, release notes |
| §3 Context management | ✗ Absent | None | Orient protocol (sans unenforceable token-count claim) |
| §4 Iron Law | ✗ Absent | None | Iron Law checklist in tdd skill; seal validates |
| §4 Tier 1/2/3 | ✗ Absent | None | Tier declared in evidence.md; seal validates |
| §4 Writer/Reviewer | ✗ Absent | `review-report.md` | devflow-reviewer agent + code-review skill |
| §7 Cognitive debt | ✗ Absent | None | Iron Law gate in tdd skill |
| §7 git blame | ✗ Absent | None | Checklist in tdd skill |
| §7 OWASP | ✗ Absent | `security-review.md` | security-review skill |
| §7 Model tier | ✗ Absent | (state metadata) | Model-router config + orient enforcement |
| v2: vertical slices | Not in ALDC | `plans/plan.md` | Document in guidelines; keep in prd-to-plan |
| v2: connector gates | Not in ALDC | (contract tests) | Document in guidelines |
| v2: Paperclip heartbeat | Not in ALDC | (state docs) | Document in guidelines |

### Missing from Both

| Gap | Priority | Owner | Threshold |
|---|---|---|---|
| Technical diagrams (Mermaid) | HIGH | `skills/architecture-diagrams/SKILL.md` | Required: ≥ 2 phases; Mermaid syntax validated by seal |
| Security review | HIGH | `skills/security-review/SKILL.md` | Triggered by file-pattern rules; severity gates deploy |
| Deploy skill + release notes | HIGH | `skills/deploy/SKILL.md` (NEW, specced in §9) | Required: all deploy-stage features |
| Rollback plan | MEDIUM | `skills/prd-to-plan/SKILL.md` | Required: ≥ 1 rollback step |
| Coverage report | MEDIUM | `skills/qa/SKILL.md` | 70% new, 60% bugfix, non-decreasing refactor; waivable |
| ADRs | MEDIUM | `skills/prd-to-plan/SKILL.md` | Required when architectural decisions present |
| API contract | MEDIUM | `skills/write-a-prd/SKILL.md` | Required when PRD creates/changes endpoints |
| Reviewer handoff artifact | HIGH | `skills/code-review/SKILL.md` | `review-report.md` required before QA |
| Orient protocol | HIGH | `devflow/orient.py` | Enforced at every heartbeat start |
| Performance baseline | LOW | `skills/qa/SKILL.md` | Captured; not a hard gate |
| Metrics instrumentation | MEDIUM | `devflow/metrics.py` | Aggregate verification-manifest data; specced in §14 |

---

## 3. Gate ↔ Seal ↔ Publish: Truth Table

### When Each Command Runs

```
Phase lifecycle:

  devflow orient            ← start of every heartbeat (before gate)
        ↓
  devflow gate --entering <phase>   ← before beginning phase work
        ↓
  [Agent does work, calls skills]
        ↓
  devflow seal --completing <phase> ← after phase work finishes
        ↓
  devflow publish-artifacts --phase <phase>  ← after seal passes
        ↓
  [Agent updates state + transitions Paperclip issue]
```

### Truth Table: What Each Command Checks

| Command | Reads | Writes | Blocks on |
|---|---|---|---|
| `devflow orient` | State doc, Paperclip issue (assignee, status), state.model_tier | State doc (warnings), orient log | Cancellation, hard state conflict |
| `devflow gate --entering X` | State doc, artifact-contract.md, prior-phase seal record | Nothing (read-only check) | Missing prior-phase artifacts or seal record |
| `devflow seal --completing X` | Local artifact files, artifact-contract.md | `verification-manifest.json` (updates), seal record in state | Schema validation failure, Iron Law fail, threshold fail (unless waived) |
| `devflow publish-artifacts --phase X` | Local artifact files, current Paperclip document revisions | Paperclip documents (PUT), publisher log in verification-manifest | Only on verification-manifest upload failure |

### Interaction Contract

- `gate` is always read-only — it never writes. If it blocks, nothing changes.
- `seal` is the only command that writes `verification-manifest.json`. It runs after work, not before.
- `publish-artifacts` always runs after `seal` passes. It depends on seal having written the manifest entry.
- No command re-checks what another already validated. `gate` checks preconditions. `seal` checks outputs. They do not overlap.

### Connector Branch (when `feature_type = connector`)

Additional checks layered on top of the standard flow — not replacing it:

| Command | Extra check |
|---|---|
| `devflow gate --entering build` | Connector scaffold directory (`connectors/<name>/`) exists |
| `devflow seal --completing build` | `connector-checklist.md` present; all rows = PASS; `schemas.py`, contract test file, idempotency key pattern all detected |
| `devflow gate --entering deploy` | QA evidence contains a **Connector QA** section; contract test result = PASS |

If `feature_type` is not set in state, gate/seal skip connector checks entirely.

---

## 4. Orient Protocol

### Scope and Limitations

`devflow orient` does **not** attempt to measure Claude's internal context token usage — this is not reliably accessible from outside the model. Instead, orient uses these **proxy signals**:

| Signal | How measured | Action |
|---|---|---|
| Session age | Timestamp delta from state.last_heartbeat_start to now | If > 30 min gap AND same phase, warn: "Context may be stale — read state before continuing" |
| Heartbeat count | state.heartbeat_count for this phase | If > 10 heartbeats in same phase, warn: "Possible long session — consider summarising and restarting" |
| Fix-break-fix | Count of seal retries for this phase | If > 3 seal failures in same phase, post warning + recommend fresh context |
| Cancellation / reassignment | Paperclip issue assigneeAgentId | Hard block if no longer assigned |
| Unread inbox | Paperclip comments since last_read_comment_id | Warning: list unread comment count |
| Model tier justification | state.model_tier + state.model_tier_justification | Warning if Opus declared without justification |

The 40% context-utilisation rule from ALDC guidelines is preserved as **advisory guidance** in `docs/guidelines.md` and in agent AGENTS.md instructions. It is not a code-enforced gate because it is not measurable. The proxy signals above are the enforceable equivalent.

### `devflow orient` CLI

```
devflow orient --issue-id <id> --agent <name>

Exit 0: OK
Exit 1: Hard block (cancellation, critical state conflict)
Exit 2: Warning (stale session, model tier, unread comments) — proceeds with logged warnings
```

---

## 5. Unified Gating: `devflow gate` and `devflow seal`

### `devflow gate --entering <phase>`

Precondition checks before beginning a phase:

| Entering | Checks |
|---|---|
| PRD | state.grill_complete: true |
| Plan | PRD artifact exists + passes schema; state.prd_complete: true |
| Build | Plan artifact exists + passes schema; plan approved (gate checks state.plan_approved: true, set when Paperclip assigns Builder subtask) |
| Review | tdd-summary.md present; state.iron_law_met: true |
| QA | review-report.md present; state.review_passed: true |
| Security | (Runs in parallel with QA; always allowed to start when QA starts) |
| Deploy | evidence.md present; security-review.md present (if triggered); state.max_severity ≤ medium OR waiver present |
| Done | verification-manifest.json present; state.artifact_contract_met: true |

### `devflow seal --completing <phase>`

Output validation after phase work:

| Completing | Validates |
|---|---|
| Grill | state.grill_complete field set |
| PRD | prd.md: Goal + Background + Scope + Acceptance Criteria + Security Scope sections present |
| Plan | plan.md: Phases + ADRs + Rollback + Verification Commands present; Mermaid syntax valid (or waiver) |
| Build | tdd-summary.md: test output section matches Iron Law regex (`PASSED \d+` or `GREEN \d+` or `\d+ passed`); state.iron_law_met written |
| Review | review-report.md: Decision field = PASS or FAIL; Checklist table present |
| QA | evidence.md: Tier field + test output (verbatim) + coverage_pct number present; thresholds checked (waivable) |
| Security | security-review.md: max_severity field valid enum; sign-off field present |
| Deploy | deploy-steps.md: ≥ 1 rollback step + ≥ 1 health-check command present |

### Recovery Paths (per phase)

| Phase | Gate/Seal failure | Automated recovery action |
|---|---|---|
| Gate: PRD | Grill not complete | Re-run grill phase; post questions; set blocked |
| Gate: Plan | PRD missing sections | Run write-a-prd skill targeting missing sections only; re-seal PRD |
| Gate: Build | Plan not approved | Post review request; set in_review; exit — wait for human |
| Gate: Review | Iron Law failed | Run TDD skill on failing tests; re-seal Build |
| Gate: QA | Review FAIL | Post findings to Paperclip; reopen Builder subtask with reviewer findings |
| Gate: Deploy | Security high/critical | Post findings; notify human; set blocked (see §7) |
| Gate: Done | Artifact missing | Identify which artifact; re-run responsible skill; re-seal responsible phase; re-run publish |
| Seal: schema fail | Any phase | Post specific missing sections; re-run responsible skill targeting only missing sections |
| Seal: Iron Law fail | Build | Post exact regex match failure; re-run TDD for failing tests |
| Seal: Mermaid syntax | Plan | Re-run architecture-diagrams skill; or apply waiver if diagrams not applicable |
| Seal: coverage below threshold | QA | Apply waiver if justified; else re-run tests with coverage goal |
| Fix-break-fix detected (> 5 edits to same file) | Any | Post warning to Paperclip; increment heartbeat_count; recommend fresh context (non-blocking) |

---

## 6. Agent Architecture

### Roles and Scoped Responsibilities

| Agent | Responsibility | Skills invoked | Produces |
|---|---|---|---|
| `devflow-feature` | Orchestrate: Grill→PRD→Plan→subtask creation | write-a-prd, prd-to-plan, architecture-diagrams | PRD, Plan, Architecture, subtasks |
| `devflow-builder` | Implement plan via TDD | tdd | tdd-summary, code commits |
| `devflow-reviewer` | Writer/Reviewer (fresh context) | code-review | review-report.md |
| `devflow-qa` | QA + Security | qa, security-review | evidence.md, security-review.md |
| `devflow-sre` | Deploy + release notes | deploy | deploy-steps.md, release notes |

### AGENTS.md Canonical Template

```markdown
## Step 0: Orient
Run: devflow orient --issue-id $ISSUE_ID --agent $AGENT_NAME
On exit 1: [Recovery: Hard Block — see below]
On exit 2: log warning, continue

## Step 1: Gate
Run: devflow gate --entering <phase> --slug $SLUG --issue-id $ISSUE_ID
On exit 1: [Recovery: phase-specific — see below]

## Step 2: Load state checkpoint
GET /api/issues/{id}/documents/state

## Step 3: Phase work
[Calls to skills only — no inline logic]

## Step 4: Seal
Run: devflow seal --completing <phase> --slug $SLUG --issue-id $ISSUE_ID
On exit 1: [Recovery: seal-specific — see below]

## Step 5: Publish artifacts
Run: devflow publish-artifacts --issue-id $ISSUE_ID --slug $SLUG --phase <phase>

## Step 6: Update state + transition issue
PUT /api/issues/{id}/documents/state
PATCH /api/issues/{id} {status, assigneeAgentId, comment}

## Recovery: Hard Block
issue is cancelled or reassigned → POST /api/issues/{id}/release if available → exit cleanly

## Recovery: [phase-specific sections]
[from truth table in §5]
```

### Subtask Roster (v3)

`devflow-feature` creates 5 subtasks after plan approval. Activation order enforced by Paperclip status:

| # | Subtask title | Agent | Activated when |
|---|---|---|---|
| 1 | Build: <title> | `devflow-builder` | Plan approved (issue back to todo) |
| 2 | Review: <title> | `devflow-reviewer` | Build subtask status = done |
| 3 | QA + Security: <title> | `devflow-qa` | Review subtask status = done AND review-report Decision = PASS |
| 4 | Deploy: <title> | `devflow-sre` | QA subtask status = done AND security gate passed |
| 5 (conditional) | Security Escalation: <title> | Human | Created only if max_severity ≥ high |

### Paperclip Status Transitions (actual API fields)

| Event | PATCH body |
|---|---|
| Plan ready for review | `{"status": "in_review", "assigneeUserId": "<creator>", "assigneeAgentId": null}` |
| Plan approved → activate Build | `{"status": "todo", "assigneeAgentId": "<builder-id>", "assigneeUserId": null}` |
| Build complete → activate Review | Create Review subtask with `{"status": "todo", "assigneeAgentId": "<reviewer-id>"}` |
| Review PASS → activate QA | Update QA subtask `{"status": "todo", "assigneeAgentId": "<qa-id>"}` |
| Review FAIL → reopen Build | Update Build subtask `{"status": "todo"}` with findings comment |
| Security high → block | `{"status": "blocked", "assigneeUserId": "<human>", "assigneeAgentId": null}` |
| QA + Security pass → activate Deploy | Update Deploy subtask `{"status": "todo", "assigneeAgentId": "<sre-id>"}` |
| All done | Parent issue `{"status": "done"}` |

---

## 7. Security Review

### Trigger Rules (config-driven, repo-overridable)

Default trigger rules are file-pattern based. Projects can extend or narrow via `devflow.yaml`:

```yaml
security:
  trigger_patterns:
    add:
      - "src/payments/**"
      - "*/login_flow/*"
    remove:
      - "*webhook*"   # if webhooks are low-risk in this repo
```

**Default file patterns (in `docs/artifact-contract.md`):**

| Category | Patterns |
|---|---|
| Auth / identity | `*auth*`, `*login*`, `*password*`, `*token*`, `*jwt*`, `*session*`, `*permission*`, `*credential*` |
| Middleware / guards | `*middleware*`, `*interceptor*`, `*guard*`, `*policy*` |
| Data model / schema | `migrations/`, `*/models.py`, `*.sql`, `*schema*`, `*/entities/*` |
| New API endpoints | Files containing route registration patterns (regex: `@app.route|router.get|router.post|path(`) |
| External integrations | `*webhook*`, `*integration*`, `*connector*`, `*callback*` |
| Data migrations | `*/migrations/*`, `*migrate*`, `*seed*`, `*fixtures*` (separate from schema) |
| PRD keywords (backup) | auth, PII, payment, credentials, secret in PRD body |

**Data migrations** are explicitly separated from schema changes — a data migration touching millions of rows has different OWASP risk (injection, data exposure) from a schema-only DDL change.

### Severity Matrix + Gate

| Severity | Gate | Notification | Override |
|---|---|---|---|
| None / Low | Pass | Log in security-review.md | N/A |
| Medium | Pass with comment | Post to issue | N/A |
| High | Block deploy | Post + comment `@<waiver-authority>` | GATE-WAIVER from waiver-authority |
| Critical | Hard block | Post + `devflow /msg <team>` | Requires PATCH from human (not agent), confirmed by seal |

---

## 8. Writer/Reviewer Protocol

### Context Isolation

`devflow-reviewer` starts a fresh Paperclip heartbeat. Reads from Paperclip only:
- `plans/plan.md` (Plan artifact)
- `build/tdd-summary.md` (TDD artifact)
- Git diff via `git diff <base-branch>..HEAD` on the feature branch

Does **not** read builder's heartbeat context or conversation history.

### Reviewer Checklist (`skills/code-review/SKILL.md`)

```
[ ] Every function I cannot explain in one sentence → flag as cognitive debt (FAIL if unfixed)
[ ] OWASP scan on changed files (complements security-review skill; does not replace)
[ ] Each PRD acceptance criterion covered by ≥ 1 test or explicitly marked out-of-scope with reason
[ ] git log / git blame on every modified existing file: no prior fix reverted
[ ] Iron Law verified: tdd-summary test output section matches expected runner output pattern
[ ] No over-engineering: no new abstraction without ≥ 2 use cases in the diff
[ ] All checklist items complete → Decision: PASS
[ ] Any item marked fail → Decision: FAIL (list specific findings)
```

### `ops/review-report.md` (handoff artifact)

```markdown
# Review Report: <feature-slug>

**Decision:** PASS | FAIL
**Reviewer:** devflow-reviewer
**Timestamp:** ISO-8601

## Checklist
| Item | Status | Notes |
|---|---|---|
| Cognitive debt | PASS/FAIL | ... |
| OWASP scan | PASS/FAIL | ... |
| AC coverage | PASS/FAIL | ... |
| git blame | PASS/FAIL | ... |
| Iron Law | PASS/FAIL | ... |
| No over-engineering | PASS/FAIL | ... |

## Findings (FAIL items)
| # | File:Line | Issue | Severity | Must-fix? |
|---|---|---|---|---|

## Acceptance Criteria Coverage
| Criterion | Test name | Status |
|---|---|---|
```

`devflow seal --completing review`: validates Decision field is `PASS` or `FAIL`. If `FAIL`, gate blocks QA start; builder subtask reopened with findings comment quoting the review-report.

---

## 9. Deploy Skill (SRE Phase) — Full Spec

### `skills/deploy/SKILL.md`

**Trigger:** `devflow-sre` agent picks up Deploy subtask.

**Inputs:** `plans/plan.md` (deploy section), `devflow.yaml` (deploy.steps), prior QA evidence.

**Process:**
1. Read `devflow.yaml` → `deploy.steps[]`
2. Validate all steps are runnable in current environment (check tools exist)
3. Execute steps sequentially
4. After each step: run health check if defined; on failure → execute rollback procedure and post findings
5. Run post-deploy verification commands from `plans/plan.md` verification section
6. Write `ops/deploy-steps.md`

**Output artifact: `ops/deploy-steps.md`**

```markdown
# Deploy Steps: <feature-slug>

**Deployed at:** ISO-8601
**Environment:** <dev/staging/prod>
**Branch:** <branch>
**Commit:** <sha>

## Steps Executed
| # | Command | Status | Duration |
|---|---|---|---|

## Health Checks
| Check | Command | Result |
|---|---|---|

## Rollback Procedure
Steps to revert if deploy fails:
1. <command>
2. <command>

## Verification Evidence
| Command | Output | Pass? |
|---|---|---|

## Release Notes
### What changed
- <bullet per acceptance criterion delivered>

### Breaking changes
- <none / list>

### Known issues
- <none / list>
```

**Seal validation:** `devflow seal --completing deploy` checks:
- ≥ 1 rollback step present
- ≥ 1 health check command present
- Verification Evidence section present with ≥ 1 row

---

## 10. Exceptions and Waivers

### Waiver Protocol

Any threshold gate (except Iron Law and artifact contract) can be waived by a **waiver-authority** posting a structured comment:

```
GATE-WAIVER
gate: coverage-threshold
reason: Legacy module; writing tests requires full rewrite. Tracked in ANA-99.
approved-by: <waiver-authority username>
expires: 2026-06-01
```

`devflow gate` detects GATE-WAIVER comments and:
1. Validates `approved-by` against the waiver-authority list (see below)
2. Checks `expires` date — expired waivers are ignored
3. Records waiver in `verification-manifest.json` under `waivers[]`
4. Allows gate to pass
5. Posts acknowledgement comment

### Waiver Authority

Defined in `devflow.yaml`:
```yaml
governance:
  waiver_authority:
    - paulrussell     # Paperclip user identifier
    - teamlead        # role-based if Paperclip supports it
```

If `waiver_authority` is not set in devflow.yaml, any comment from a human user (not an agent) is accepted. This is the permissive default; teams should configure the allowlist.

### Waivable vs Non-Waivable

| Gate | Waivable | Who |
|---|---|---|
| Coverage threshold | Yes | waiver-authority |
| Mermaid syntax (diagrams not applicable) | Yes | waiver-authority |
| Security severity high | Yes + justification | waiver-authority |
| Security severity critical | No | Cannot be waived |
| Iron Law (test output missing) | No | Cannot be waived |
| Artifact contract (missing artifact) | No | Cannot be waived |
| Reviewer FAIL → QA blocked | No (reviewer must re-run or builder must fix) | Cannot be waived |

---

## 11. Model Tier Enforcement

### State Metadata (not inline comments)

Declared in Paperclip state document before phase begins:

```json
{
  "phase": "plan",
  "model_tier": "opus",
  "model_tier_justification": "Architecture decisions for connector schema design",
  "model_tier_approved": true
}
```

`devflow orient` checks: if `model_tier = "opus"` and `model_tier_justification` is absent or empty → exit 2 (warning), post comment. Phase proceeds but warning is logged in verification-manifest.

### Policy Table

| Task | Tier | Justification required |
|---|---|---|
| File search, grep, codebase reading | Haiku | No |
| Standard implementation | Sonnet | No |
| Architecture decisions, ADRs | Opus | Yes — logged in state + ADR |
| Security review analysis | Opus | Yes — logged in state + security-review.md |
| Complex debugging, root-cause | Opus | Yes — logged in state + tdd-summary.md |
| Writer/Reviewer pass | Sonnet | No |
| Parallel sub-investigations | Sonnet/Haiku workers | No |

### Config (`devflow/config.py`)

```python
DEVFLOW_MODEL_HAIKU = os.getenv("DEVFLOW_MODEL_HAIKU", "claude-haiku-4-5-20251001")
DEVFLOW_MODEL_SONNET = os.getenv("DEVFLOW_MODEL_SONNET", "claude-sonnet-4-6")
DEVFLOW_MODEL_OPUS = os.getenv("DEVFLOW_MODEL_OPUS", "claude-opus-4-6")
```

`devflow/api.py`: accept `model` parameter; default to `DEVFLOW_MODEL_SONNET`.

---

## 12. Artifact Publisher

### `devflow publish-artifacts --issue-id <id> --slug <slug> --phase <phase>`

```
For each artifact in artifact-contract.md for this phase:
  1. Check local file exists
  2. GET /api/issues/{id}/documents/{key} to fetch current revisionId
  3. PUT /api/issues/{id}/documents/{key} with content + revisionId
  4. On 409 conflict: re-fetch revisionId, retry once
  5. On persistent failure after 3 retries:
     - Non-critical artifact (diagrams): log warning in verification-manifest.warnings[]
     - Critical artifact (security-review with severity ≥ medium, review-report, verification-manifest): post blocking comment, do NOT transition issue
  6. Record each uploaded artifact + revisionId in verification-manifest.json
```

Critical vs non-critical is defined in `docs/artifact-contract.md` per artifact (a `blocking_upload` boolean field).

---

## 13. Multi-Stack and Tooling Prerequisites

### v3 Scope

v3 targets **Python and TypeScript** stacks. Go, Java, and other languages are out of scope for initial implementation. This is noted in `docs/guidelines.md`.

**Plugin mechanism for future stacks:** `devflow.yaml` can declare a `qa.coverage_command` override:
```yaml
qa:
  coverage_command: "go test ./... -coverprofile=coverage.out && go tool cover -func=coverage.out"
  coverage_pct_regex: "total:\\s+\\(statements\\)\\s+(\\d+\\.\\d+)%"
```
`devflow seal --completing qa` uses the override if present, else defaults to `coverage.py` (Python) or `nyc` (TypeScript).

### Prerequisites Checklist

| Tool | Required for | Check | Install |
|---|---|---|---|
| `mermaid` CLI | Diagram syntax validation | `mermaid --version` | `npm i -g @mermaid-js/mermaid-cli` |
| `coverage.py` | Python coverage | `coverage --version` | `pip install coverage` |
| `nyc` / `c8` | TypeScript coverage | `nyc --version` | `npm i -g nyc` |
| `pytest` | Python tests | `pytest --version` | `pip install pytest` |
| `python -m py_compile` | Python syntax | Built-in | N/A |
| `bash -n` | Bash syntax | Built-in | N/A |
| `npx tsc --noEmit` | TypeScript syntax | `tsc --version` | `npm i -g typescript` |
| Paperclip API | All agent operations | `curl $PAPERCLIP_API_URL/health` | See runbook-prefect-creds.md |
| `git` | git-blame, log | `git --version` | Standard |

`devflow orient` runs tool availability check on first heartbeat. Missing optional tools (mermaid, coverage) → warning + seal skips that validation with note. Missing required tools (pytest or tsc, Paperclip API) → hard block.

---

## 14. Metrics Instrumentation

### Data Source: `verification-manifest.json`

Every completed feature produces a `verification-manifest.json`. `devflow/metrics.py` aggregates these.

### `devflow metrics --slug <slug>` (per feature)

Reads `features/<slug>/ops/verification-manifest.json`. Outputs:
- artifact_contract_met
- iron_law_met
- coverage_pct
- max_security_severity
- waivers count + details
- warnings count

### `devflow metrics --summary` (across all features)

Scans `features/*/ops/verification-manifest.json`. Outputs:

| Metric | Formula | Target |
|---|---|---|
| Iron Law compliance | iron_law_met=true / total features | ≥ 90% |
| Artifact contract compliance | artifact_contract_met=true / total | 100% |
| Avg coverage | mean(coverage_pct) | ≥ 70% |
| Waiver rate | waivers.count / total features | < 20% |
| Security escalations | max_severity ≥ high / total | Track; no hard target |
| Seal failures per phase | aggregated from warnings | Track for process improvement |

### Reporting

`devflow metrics --summary --output metrics-report.md` writes a markdown report. This is the instrumentation for the rollout success metrics in §16.

---

## 15. Canonical Artifact Contract

(`docs/artifact-contract.md` — machine-readable by gate, seal, publish-artifacts)

| Artifact | Local path | Paperclip key | Required sections | Threshold | blocking_upload |
|---|---|---|---|---|---|
| PRD | `specs/prd.md` | `prd` | Goal, Background, Scope, AC, API Contracts, Security Scope | All required | false |
| Plan | `plans/plan.md` | `plan` | Phases, ADRs, Rollback, Verification Commands | All required | false |
| Architecture | `ops/architecture.md` | `architecture` | Component diagram, Sequence diagram | ≥ 2 phases | false |
| TDD Summary | `build/tdd-summary.md` | `tdd-summary` | Phases, Test results (verbatim), Files, Commands | Iron Law regex | false |
| Review Report | `ops/review-report.md` | `review-report` | Decision, Checklist, Findings, AC Coverage | Decision = PASS/FAIL | true |
| QA Evidence | `qa/evidence.md` | `qa-evidence` | Tier, Test output (verbatim), Coverage %, Syntax checks | Coverage threshold | false |
| Security Review | `qa/security-review.md` | `security-review` | OWASP checklist, max_severity, sign-off | Required when triggered | true (if severity ≥ medium) |
| Deploy Steps | `ops/deploy-steps.md` | `deploy-steps` | Steps, Rollback, Health checks, Verification Evidence, Release Notes | All required | false |
| Verification Manifest | `ops/verification-manifest.json` | `verification-manifest` | artifact_contract_met, iron_law_met, waivers[], warnings[] | Required before done | true |

---

## 16. Integration Testing

### Success Path Test

`tests/integration/test_full_pipeline.py`:
1. Create Paperclip test issue with known spec
2. Run full pipeline: Grill → PRD → Plan → Build → Review → QA → Security → Deploy
3. Assert all 9 artifacts present on Paperclip issue
4. Assert verification-manifest: `artifact_contract_met: true`, `iron_law_met: true`
5. Assert artifact content validity (Mermaid syntax, coverage %, security severity enum, Decision field)
6. Assert issue status = done

### Failure Path Tests (gatekeeper recovery)

| Test | Setup | Expected behaviour |
|---|---|---|
| Missing PRD artifact | Skip write-a-prd; run gate for Plan | Gate blocks; recovery runs write-a-prd; gate passes on retry |
| Iron Law not met | Produce tdd-summary with placeholder test output | Seal fails; recovery re-runs TDD; seal passes on retry |
| Coverage below threshold | Produce evidence.md with coverage_pct: 40 | Seal fails with threshold error; waiver applied; seal passes with waiver in manifest |
| Security severity high | Produce security-review.md with max_severity: high | Gate blocks deploy; security escalation subtask created; human comment SECURITY-WAIVER; gate passes |
| Review FAIL | Produce review-report.md with Decision: FAIL | Gate blocks QA; builder subtask reopened; findings posted |
| Artifact upload conflict | Stub Paperclip API to return 409 on first PUT | Publisher retries; succeeds on second attempt |
| Persistent upload failure (critical artifact) | Stub API to always return 500 | Publisher posts blocking comment; issue not transitioned to done |
| Waiver from unauthorised user | Post GATE-WAIVER from agent (not human) | Waiver rejected; gate remains blocked |
| Waiver expired | Post GATE-WAIVER with past expires date | Waiver ignored; gate remains blocked |

---

## 17. Rollout Phases

| Phase | Scope | Success metric | Instrumentation |
|---|---|---|---|
| Pilot | 1 new feature, manual `devflow seal` calls | All 9 artifacts produced; 0 manual bypasses | `devflow metrics --slug <slug>` |
| Validation | 3 features fully autonomous | Iron Law 100%; artifact contract 100%; coverage ≥ threshold or waived with justification | `devflow metrics --summary` |
| Standard | All new Paperclip issues | Iron Law ≥ 90%; waiver rate < 20%; 0 hard blocks due to missing artifacts (auto-recovery handles) | Weekly metrics report |
| Retrospective (after 10 features) | All | Update guidelines version; adjust thresholds; capture new gotchas | Commit guidelines.md v1.1.0 |

---

## 18. Execution Sequencing

| # | Workstream | Effort | Sessions | Quick win | Dependency |
|---|---|---|---|---|---|
| 1 | Traceability matrix | Small | 1 | ✓ | None |
| 2 | Artifact contract (`docs/artifact-contract.md`) | Small | 1 | ✓ | None |
| 3 | Iron Law gate in tdd skill | Small | 1 | ✓ | None |
| 4 | `devflow orient` CLI | Medium | 1 | | WS1 |
| 5 | `devflow gate` + `devflow seal` CLI | Large | 2 | | WS2 |
| 6 | `devflow publish-artifacts` CLI | Medium | 1 | | WS2 |
| 7 | `devflow migrate-v3` CLI | Medium | 1 | | WS5 |
| 8 | `devflow metrics` CLI | Small | 1 | | WS5 |
| 9 | New skills: security-review, architecture-diagrams, code-review, qa, deploy | Large | 3–4 | | WS5 |
| 10 | Agent refactor: feature/builder/reviewer/qa/sre | Large | 2 | | WS9 |
| 11 | PRD + plan + tdd skill modifications | Medium | 1–2 | | WS9 |
| 12 | Model tier config + state enforcement | Small | 1 | | None |
| 13 | Waiver system in `devflow gate` | Medium | 1 | | WS5 |
| 14 | Integrated `docs/guidelines.md` (versioned) | Medium | 1 | | WS1–11 |
| 15 | Integration tests (success + failure paths) | Medium | 1–2 | | All above |
| 16 | Pilot rollout | — | ongoing | | WS15 |

---

## 19. Critical Files Reference

| File | Role |
|---|---|
| `agents/devflow-feature/AGENTS.md` | Orchestrator — declarative |
| `agents/devflow-builder/AGENTS.md` | NEW |
| `agents/devflow-reviewer/AGENTS.md` | NEW |
| `agents/devflow-qa/AGENTS.md` | NEW |
| `agents/devflow-sre/AGENTS.md` | Existing — Deploy |
| `skills/tdd/SKILL.md` | Iron Law + git-blame + cognitive debt |
| `skills/write-a-prd/SKILL.md` | PRD template + API contracts + security scope |
| `skills/prd-to-plan/SKILL.md` | Plan template + ADR + rollback |
| `skills/architecture-diagrams/SKILL.md` | NEW — Mermaid |
| `skills/security-review/SKILL.md` | NEW — OWASP + severity |
| `skills/code-review/SKILL.md` | NEW — Writer/Reviewer |
| `skills/qa/SKILL.md` | NEW — Tier 1/2/3 evidence |
| `skills/deploy/SKILL.md` | NEW — Deploy + release notes |
| `devflow/orient.py` | NEW |
| `devflow/gatekeeper.py` | NEW — gate + seal |
| `devflow/artifact_publisher.py` | NEW |
| `devflow/metrics.py` | NEW |
| `devflow/config.py` | Model tier env vars |
| `devflow/api.py` | Model parameter |
| `docs/artifact-contract.md` | NEW — canonical artifact spec |
| `docs/guidelines-traceability.md` | NEW — coverage matrix |
| `docs/model-routing-policy.md` | NEW |
| `docs/guidelines.md` | NEW — versioned integrated standard |
| `skills/connector-build/SKILL.md` | NEW — connector blueprint |
| `agents/devflow-ceo/AGENTS.md` | NEW — CEO orchestrator |

---

## 20. Connector Skills & Artifact Contract

### Design Principle: Connector Support Is Skill-Driven, Not Agent-Driven

There are no separate connector agents. The general `devflow-builder`, `devflow-reviewer`, and `devflow-qa` agents handle all feature types. When the PRD/Plan has `feature_type: connector`, these agents **call the connector-specific skills** in addition to their standard skills. This keeps the agent roster stable while specialised logic stays encapsulated and testable.

### `skills/connector-build/SKILL.md` — Canonical Connector Blueprint

**Invoked by:** `devflow-builder` when `state.feature_type = "connector"`

**Enforces the following connector contract (each item is checked by `devflow seal --completing build` for connector features):**

| Component | Requirement | Validated by |
|---|---|---|
| Schema definition | `connectors/<name>/schemas.py` — Pydantic models for source + destination | Seal: file exists + imports Pydantic |
| Schema Gate (first task) | Prefect flow first task validates source schema before any data processed | Seal: regex check for `SchemaValidationError` raise pattern |
| Idempotency | Each extract/load task carries `idempotency_key = sha256(source_id + run_date)` | Seal: regex check for `idempotency_key` in connector module |
| Idempotency test | Unit test: run flow twice with same input, assert row count = single-run count | Seal: test file exists; test name matches idempotency pattern |
| Contract test | `tests/connectors/test_<name>_contract.py` — verifies source API still returns expected fields | Seal: file exists |
| Logging | Structured logging on extract, transform, load; log source record count | Seal: logging import + count log in module |
| Retries | Prefect task retry config present (≥ 1 retry, delay ≥ 1s) | Seal: regex check for `retries=` in flow |
| Observability | Flow emits at minimum: records_extracted, records_loaded, errors_skipped as Prefect artifacts | Seal: artifact emit pattern present |
| Docs | `connectors/<name>/README.md` — describes source, destination, schedule, schema, run instructions | Seal: file exists, ≥ 3 sections |

**Output artifact: `build/connector-checklist.md`**

```markdown
# Connector Build Checklist: <feature-slug>

**Connector name:** <name>
**Timestamp:** ISO-8601

| Component | Status | Notes |
|---|---|---|
| Schema definition (schemas.py) | PASS/FAIL | |
| Schema Gate (first Prefect task) | PASS/FAIL | |
| Idempotency key | PASS/FAIL | |
| Idempotency test | PASS/FAIL | |
| Contract test | PASS/FAIL | |
| Structured logging | PASS/FAIL | |
| Retry config | PASS/FAIL | |
| Observability artifacts | PASS/FAIL | |
| Connector README | PASS/FAIL | |

**Overall:** PASS / FAIL
```

### Connector Review Integration (`skills/code-review/SKILL.md` extension)

When `state.feature_type = "connector"`, the reviewer appends a **Connector Review** section to `review-report.md`:

```
## Connector-Specific Checks (if applicable)
[ ] Schema Gate is genuinely first — no data processing before validation
[ ] Idempotency key is deterministic — same inputs always produce same key
[ ] Contract test covers all fields the flow depends on (not just "any response")
[ ] Retry config uses reasonable delay — not hammering a failing API
[ ] Observability: records_extracted + records_loaded both logged (not just one)
[ ] README explains how to run the flow manually (not just automated)
[ ] No silent exception swallowing in extract/load tasks
```

All connector checklist items must be PASS for the review Decision to be PASS.

### Connector QA (`skills/qa/SKILL.md` extension)

When `state.feature_type = "connector"`, `devflow-qa` additionally:
1. Runs `pytest tests/connectors/test_<name>_contract.py` — contract test
2. Runs the idempotency test
3. Records results in `qa/evidence.md` under a **Connector QA** section
4. If contract test fails: posts findings, sets security-review.md note about API contract breach (potential data risk)

### Connector Artifact Contract Addition

Appended to `docs/artifact-contract.md` for `feature_type: connector`:

| Artifact | Local path | Paperclip key | Required sections | blocking_upload |
|---|---|---|---|---|
| Connector Checklist | `build/connector-checklist.md` | `connector-checklist` | All component rows; Overall = PASS | true |
| Connector README | `connectors/<name>/README.md` | `connector-readme` | Source, Destination, Schedule, Schema, Run instructions | true |
| Schema file | `connectors/<name>/schemas.py` | (local only; not uploaded) | Pydantic models present | N/A |
| Contract test | `tests/connectors/test_<name>_contract.py` | (local only) | Test file present | N/A |

### Connector Gate/Seal Additions

`devflow gate --entering build` (connector): additionally checks that `connector_scaffold` has been run (connector directory exists).

`devflow seal --completing build` (connector): runs connector checklist validations in addition to standard Iron Law.

`devflow gate --entering deploy` (connector): additionally checks contract test passed in QA evidence.

---

## 21. Agent Hierarchy: CEO Orchestration

### Overview

```
Paperclip Board / Human
         │
   devflow-ceo (CEO agent)
         │
   devflow-feature (Orchestrator)
         │
   ┌─────┼──────────┬───────────┐
builder reviewer  qa+security  sre
```

### CEO Agent (`agents/devflow-ceo/AGENTS.md`)

**Responsibility:** Top-level backlog management, agent roster health, escalation routing. The CEO does not write code. It assigns work and monitors pipeline health.

**Functions:**
1. **Backlog triage:** Reviews new Paperclip issues. Assigns `feature_type` (feature / bugfix / connector). Routes to `devflow-feature` orchestrator.
2. **Roster health:** Monitors agent subtask queues. Posts a check-in comment and reassigns if thresholds exceeded.
3. **Escalation routing:** Receives security severity high/critical escalations. Notifies human via CCE `/msg` (see prerequisites below). Creates human-assignment subtask.
4. **Metrics awareness:** Periodically checks `devflow metrics --summary`. If thresholds breached, posts team alert.
5. **Agent re-configuration:** If a new agent type is introduced (e.g., `devflow-data-engineer`), CEO AGENTS.md is the single place updated to add it to the routing table.

### CEO Intervention Thresholds (testable)

| Signal | Threshold | CEO action |
|---|---|---|
| Agent `in_progress` duration | Build > 2h, Review > 1h, QA > 2h, Deploy > 1h | Post check-in comment; if no progress after 30 min, reassign subtask |
| Seal failure count (same phase) | > 3 failures on same phase for same issue | Post escalation comment; set issue to `blocked`; notify human |
| Fix-break-fix detection (from orient) | Logged in state for same phase | CEO checks on next heartbeat; posts recommendation to start fresh session |
| Iron Law compliance | < 80% across last 10 features | Post team alert to Paperclip board; flag for retrospective |
| Artifact contract compliance | < 100% across last 10 features | Post team alert; block new issue assignments until resolved |
| Orient warnings (model tier without justification) | > 2 per feature | Post reminder comment on issue |

These thresholds are configurable in `devflow.yaml` under `governance.ceo_thresholds`.

### Human Escalation Prerequisites (`devflow /msg`)

`devflow /msg` requires CCE (Claude Code Enhanced) messaging to be configured. Before v3 rollout:
- Confirm CCE team messaging is active (`devflow orient` will warn if not configured)
- For high/critical security blocks: if CCE messaging is unavailable, CEO falls back to posting a Paperclip `@mention` comment with `ESCALATION-REQUIRED` prefix
- Email integration is **out of scope for v3** and tracked as a future enhancement

**Does NOT do:** Write code, run tests, produce feature artifacts, modify issue content beyond status/assignee.

### Legacy Agent Retirement

| Legacy agent | Status | Replacement |
|---|---|---|
| `devflow-feature` (all-in-one monolith) | ✗ Retired | `devflow-feature` (orchestrator only) + scoped phase agents |
| `devflow-connector-builder` (v2 connector specialist) | ✗ Retired | `devflow-builder` + `skills/connector-build/SKILL.md` |
| `devflow-prefect-qa` (v2 Prefect-specific QA) | ✗ Retired | `devflow-qa` + connector QA extension in qa skill |
| `devflow-sre` (v2) | ~ Reimagined | `devflow-sre` (extended with deploy skill, release notes) |

### CEO Re-hires / Reconfigures

When v3 launches, the CEO agent:
1. Reads the current company agent roster: `GET /api/companies/{id}/agents`
2. Checks for legacy agents (devflow-connector-builder, devflow-prefect-qa)
3. If found: posts retirement notice to any open issues assigned to them, reassigns to v3 equivalents
4. Registers new agents (devflow-builder, devflow-reviewer, devflow-qa) if not present
5. Updates its own routing table in state document

This is a one-time `devflow ceo-init` command run as part of the v3 rollout (see §22).

---

## 22. Paperclip Cleanup & Reset

### Before v3 Rollout: Triage Existing Issues

Run `devflow ceo-init --dry-run` to audit the current state:
- Lists all open Paperclip issues and their current status
- Classifies each: `migrate` (keep + upgrade) | `archive` (close with note) | `ignore` (already done)

### Step-by-Step Cleanup

**Step 1: Export artifacts from existing issues**
```bash
devflow export-artifacts --all-open --output ./archive/pre-v3/
```
For each open issue: downloads all existing Paperclip documents to `archive/pre-v3/<issue-id>/`. Preserves everything before any changes.

**Step 2: Decide per-issue fate**

| Issue state | Action |
|---|---|
| `done` | Archive — no migration needed |
| `blocked` (pre-v3) | Archive with note: "Blocked under v2; reopen as new v3 issue if still relevant" |
| `in_progress` with meaningful artifacts | Migrate: run `devflow sync <id> --migrate-v3 --apply` |
| `todo` with no progress | Archive; create fresh v3 issue from PRD template |
| `in_review` | Migrate if plan exists; archive if only title/description |

**Step 3: Run migration for kept issues**
```bash
devflow sync <issue-id> --migrate-v3 --apply
```
(Per §1 spec — maps phases, stubs missing artifacts, posts migration comment.)

**Step 4: Run `devflow ceo-init`**
```bash
devflow ceo-init --apply
```
- Retires legacy agents
- Registers v3 agents
- Posts a pinned comment to the Paperclip board: "v3 pipeline active as of <date>"

**Step 5: Create v3 issue templates**

In Paperclip (or as `docs/issue-templates/`):
- `feature-issue-template.md` — PRD fields pre-filled, feature_type selector
- `connector-issue-template.md` — PRD fields + connector-specific fields (source, destination, schedule)
- `bugfix-issue-template.md` — Bug report fields + triage checklist

### Metrics Treatment of Pre-v3 Issues

`devflow metrics --summary` by default:
- **Excludes** issues where `verification-manifest.json` has `"schema_version": null` (unmigrated pre-v3)
- **Tags** migrated issues as `"schema_version": "v3-migrated"` — included in metrics but with a `migrated: true` flag in summary output

This ensures compliance metrics reflect v3 pipeline health, not legacy debt.

---

## 23. Updated Execution Sequencing (v0.6)

**Note:** Cleanup (WS1) must complete before any code changes begin. It establishes the clean Paperclip baseline that all subsequent work depends on.

**Progress last updated: 2026-03-30. Branch: `v3-paperclip`. Commit: `c61303e`.**

| # | Workstream | Status | Key files |
|---|---|---|---|
| 1 | **Paperclip cleanup / `devflow ceo-init`** | ✅ Done | `devflow/cli.py` (`export-artifacts`, `ceo-init` commands); `paperclip.py` (`list_agents`, `list_documents`) |
| 2 | Traceability matrix | ✅ Done | `docs/guidelines-traceability.md` |
| 3 | Artifact contract (`docs/artifact-contract.md`) | ✅ Done | `docs/artifact-contract.md` |
| 4 | Iron Law gate in tdd skill | ✅ Done | `skills/tdd/SKILL.md` (Iron Law + cognitive debt + git-blame checklists; tdd-summary template updated) |
| 5 | `devflow orient` CLI | ✅ Done | `devflow/orient.py`; `devflow/cli.py` (`orient` command); `paperclip.py` (`list_comments`) |
| 6 | `devflow gate` + `devflow seal` CLI | ✅ Done | `devflow/gatekeeper.py`; `devflow/cli.py` (`gate`, `seal` commands) |
| 7 | `devflow publish-artifacts` CLI | ✅ Done | `devflow/artifact_publisher.py`; `devflow/cli.py` |
| 8 | `devflow migrate-v3` CLI | ✅ Done | `devflow/migrate.py`; `devflow/cli.py` |
| 9 | `devflow metrics` CLI | ✅ Done | `devflow/metrics.py`; `devflow/cli.py` |
| 10 | New skills: security-review, architecture-diagrams, code-review, qa, deploy | ✅ Done | `skills/security-review/SKILL.md`, `skills/architecture-diagrams/SKILL.md`, `skills/code-review/SKILL.md`, `skills/qa/SKILL.md`, `skills/deploy/SKILL.md` |
| 11 | Connector skills: connector-build + extensions | ✅ Done | `skills/connector-build/SKILL.md` |
| 12 | Agent refactor: feature/builder/reviewer/qa/sre + CEO | ✅ Done | `agents/devflow-feature/AGENTS.md` (rewritten), `agents/devflow-builder/AGENTS.md`, `agents/devflow-reviewer/AGENTS.md`, `agents/devflow-qa/AGENTS.md`, `agents/devflow-sre/AGENTS.md`, `agents/devflow-ceo/AGENTS.md` |
| 13 | PRD + plan + tdd skill modifications | ✅ Done | `skills/write-a-prd/SKILL.md` (v3 template: Goal/Background/Scope/AC/Security Scope/API Contracts); `skills/prd-to-plan/SKILL.md` (Phases/ADRs/Rollback/Verification Commands); `skills/tdd/SKILL.md` (done WS4) |
| 14 | Model tier config + state enforcement | ✅ Done | `devflow/config.py` (model_haiku/sonnet/opus); `devflow/api.py` (per-call model override) |
| 15 | Waiver system in `devflow gate` | ✅ Done | `devflow/waivers.py` (parse/validate/find); `devflow/gatekeeper.py` + `devflow/cli.py` wired; 31 tests |
| 16 | Integrated `docs/guidelines.md` (versioned) | ✅ Done | `docs/guidelines.md` v1.0.0 — 14 sections; covers philosophy, phases, Iron Law, tiers, waivers, model routing, v2 practices |
| 17 | Integration tests | 🔲 Todo | `tests/integration/` |
| 18 | Pilot rollout (1 connector feature) | 🔲 Todo | Depends on WS17 |
