# Guidelines Traceability Matrix
**Version:** 1.0 — WS2 baseline
**Source:** ALDC Agentic Coding Guidelines v0.2 (March 2026)
**Purpose:** Scope audit trail — maps every ALDC requirement to an artifact, workstream, and status.

---

## Coverage Legend

| Symbol | Meaning |
|---|---|
| ✓ | Fully covered |
| ~ | Partially covered |
| ✗ | Not yet covered |

---

## ALDC §1 — Philosophy

| Requirement | Covered? | Enforcement | Workstream |
|---|---|---|---|
| Plan-then-execute with verification | ✓ | gate → work → seal lifecycle | WS6 |
| Verification over trust (tests prove it works) | ~ | Iron Law gate in tdd skill (build seal) | WS4 |
| Context is the constraint — manage it actively | ~ | orient proxy signals (session age, heartbeat count, fix-break-fix) | WS5 |
| Agent is only as good as the system around it | ✓ | Phase structure + artifact gates enforce this structurally | — |

### Numbers Behind the Discipline (advisory — not code-enforced)

| Metric | Value | Where referenced |
|---|---|---|
| First-attempt success rate | ~33% | docs/guidelines.md (WS16) |
| AI-co-authored security vulnerability rate | 2.74× human rate | security-review skill trigger rationale (WS10) |
| Token savings in healthy code | ~50% | Iron Law rationale in tdd skill (WS4) |
| Context quality degradation threshold | ~40% context utilisation | orient advisory warning; not a gate (proxy signals used instead) |

---

## ALDC §2 — Workflow Phases

| ALDC Phase | Covered? | Artifact | Missing / Action | Workstream |
|---|---|---|---|---|
| Orient | ~ | None | `devflow orient` CLI + Orient protocol in every AGENTS.md | WS5 |
| Plan (PRD) | ✓ | `prd/prd.md` | Add: API contract (when endpoints change) | WS13 |
| Plan (Plan) | ✓ | `plans/plan.md` | Add: Mermaid diagrams, ADRs, rollback steps, verification commands | WS13 |
| Implement | ✓ | `build/tdd-summary.md` | Add: Iron Law gate, git-blame checklist, cognitive debt check | WS4, WS13 |
| Verify (QA) | ~ | `qa/evidence.md` | Add: Tier 1/2/3 declaration, coverage %, verbatim test output | WS10, WS13 |
| Verify (Security) | ✗ | `ops/security-review.md` | New security-review skill; file-pattern triggers | WS10 |
| Verify (Review) | ✗ | `ops/review-report.md` | Writer/Reviewer protocol; devflow-reviewer agent | WS10, WS12 |
| Commit & Communicate | ~ | `ops/deploy-steps.md` | Add: rollback procedure, health-check commands, release notes | WS10, WS13 |

---

## ALDC §3 — Context Management

| Requirement | Covered? | Enforcement | Workstream |
|---|---|---|---|
| Fresh context per phase (no context pollution) | ~ | Each agent starts a new Paperclip heartbeat | WS12 |
| 40% context utilisation threshold (advisory) | ~ | orient warns on proxy signals; not directly measurable | WS5 |
| Session age tracking | ✗ | `devflow orient` — session age proxy signal | WS5 |
| Heartbeat count tracking | ✗ | `devflow orient` — heartbeat_count proxy signal | WS5 |
| Fix-break-fix detection | ✗ | `devflow orient` — seal retry count proxy signal | WS5 |
| Summarise and restart on long sessions | ✗ | orient warning (advisory); CEO checks on next heartbeat | WS5, WS12 |

---

## ALDC §4 — Standards

### Iron Law

| Requirement | Covered? | Enforcement | Workstream |
|---|---|---|---|
| Tests pass before any commit | ✗ | Iron Law gate in tdd skill; `devflow seal --completing build` validates regex match | WS4 |
| Test output verbatim in artifact | ✗ | tdd-summary.md required section; seal validates regex | WS4 |
| No `# type: ignore` / `noqa` without comment | ✗ | Iron Law checklist in tdd skill | WS4 |
| No commented-out code | ✗ | Iron Law checklist in tdd skill | WS4 |

### Tier System

| Requirement | Covered? | Enforcement | Workstream |
|---|---|---|---|
| Tier 1 — syntax + unit tests | ✗ | evidence.md Tier field; seal validates | WS10, WS13 |
| Tier 2 — integration tests | ✗ | evidence.md Tier field; seal validates | WS10, WS13 |
| Tier 3 — end-to-end / contract tests | ✗ | evidence.md Tier field; seal validates | WS10, WS13 |
| Coverage thresholds (70% new, 60% bugfix, non-decreasing refactor) | ✗ | QA seal; waivable | WS10 |

### Writer/Reviewer

| Requirement | Covered? | Enforcement | Workstream |
|---|---|---|---|
| Reviewer in fresh context (no builder history) | ✗ | devflow-reviewer agent — separate heartbeat | WS12 |
| review-report.md required before QA | ✗ | `devflow gate --entering qa` checks review-report.md presence | WS6 |
| Decision field PASS/FAIL | ✗ | `devflow seal --completing review` validates Decision field | WS6 |
| Reviewer checklist (cognitive debt, OWASP, AC coverage, git blame, Iron Law, no over-engineering) | ✗ | `skills/code-review/SKILL.md` | WS10 |

---

## ALDC §7 — Code Quality

| Requirement | Covered? | Enforcement | Workstream |
|---|---|---|---|
| Cognitive debt — flag functions unexplainable in one sentence | ✗ | Reviewer checklist; FAIL if unfixed | WS10 |
| git blame — no prior fix reverted | ✗ | Reviewer checklist item; tdd skill advisory | WS4, WS10 |
| OWASP scan on changed files | ✗ | security-review skill; triggered by file-pattern rules | WS10 |
| Model tier declaration (Haiku/Sonnet/Opus) | ✗ | state.model_tier metadata; orient warns on undeclared Opus | WS5, WS14 |
| Model tier justification required for Opus | ✗ | orient warning; CEO posts reminder if > 2 per feature | WS5, WS12, WS14 |

---

## v2 Practices (Not in ALDC — Preserved)

| v2 Practice | Covered? | Artifact | Action | Workstream |
|---|---|---|---|---|
| Vertical slice / tracer bullet TDD | ✓ | `plans/plan.md` | Document in guidelines.md | WS13, WS16 |
| Connector gates (contract tests, idempotency) | ~ | `ops/connector-checklist.md` | Connector seal checks; document in guidelines | WS11 |
| Paperclip heartbeat + state checkpoint | ✓ | `state` document (Paperclip) | Extend with v3 schema fields | WS6 |
| Prefect deploy integration | ✓ | `ops/deploy-steps.md` | Extend deploy skill | WS10 |

---

## Gap Summary

### High Priority (blocking or high-risk)

| Gap | Owner | Workstream |
|---|---|---|
| Technical diagrams (Mermaid) — ≥ 2 phases required | `skills/architecture-diagrams/SKILL.md` | WS10 |
| Security review skill + file-pattern triggers | `skills/security-review/SKILL.md` | WS10 |
| Writer/Reviewer protocol + review-report.md | `skills/code-review/SKILL.md` + `devflow-reviewer` | WS10, WS12 |
| `devflow orient` CLI (all proxy signals) | `devflow/orient.py` | WS5 |
| `devflow gate` + `devflow seal` CLI | `devflow/gatekeeper.py` | WS6 |
| Iron Law gate in tdd skill | `skills/tdd/SKILL.md` | WS4 |

### Medium Priority

| Gap | Owner | Workstream |
|---|---|---|
| Rollback plan in plan.md (≥ 1 step required) | `skills/prd-to-plan/SKILL.md` | WS13 |
| Coverage report in evidence.md (70%/60% thresholds) | `skills/qa/SKILL.md` | WS10 |
| ADRs in plan.md (when architectural decisions present) | `skills/prd-to-plan/SKILL.md` | WS13 |
| API contract in prd.md (when endpoints created/changed) | `skills/write-a-prd/SKILL.md` | WS13 |
| devflow metrics CLI | `devflow/metrics.py` | WS9 |
| Model tier enforcement | state metadata + orient | WS14 |
| Waiver system | `devflow gate` | WS15 |

### Low Priority

| Gap | Owner | Workstream |
|---|---|---|
| Performance baseline capture (not a hard gate) | `skills/qa/SKILL.md` | WS10 |
| Integrated guidelines.md (versioned) | ✓ | `docs/guidelines.md` v1.0.0 | WS16 |

---

## Workstream → Coverage Map

| Workstream | ALDC sections addressed |
|---|---|
| WS4 — Iron Law gate | §4 Iron Law, §7 git blame (partial) |
| WS5 — devflow orient | §3 Context management, §7 Model tier |
| WS6 — gate + seal | §2 all phases (enforcement), §4 Tier/Writer-Reviewer |
| WS10 — new skills | §2 Verify, §4 Tier 1/2/3, §7 OWASP/cognitive debt/Reviewer |
| WS12 — agent refactor | §2 Orient, §4 Writer/Reviewer (context isolation) |
| WS13 — skill modifications | §2 Plan/Implement/Verify gaps |
| WS14 — model tier config | §7 Model tier |
| WS16 — guidelines.md | §1 Numbers, v2 practices documentation |
