# WS18 Pilot Runbook — Manual Connector Feature (CLI Layer)
**Version:** 1.0
**Purpose:** Step-by-step guide for manually running one connector feature through
the full v3 pipeline using the `devflow` CLI. No Paperclip agent automation required.
This proves the gate/seal/publish machinery before handing off to agents.

**Time estimate:** 2–4 hours for a real connector; 30 min for a smoke test.

---

## Before You Start

### How to run devflow

`ai-dev-flow` sits as a sibling directory above your other repos. Run all `devflow`
commands from inside the connector repo using the sibling path:

```bash
alias devflow="python /path/to/ai-dev-flow/devflow/cli.py"
# or add to your shell profile:
export PATH="/path/to/ai-dev-flow:$PATH"
```

Verify it works:
```bash
devflow --help
```

### Prerequisites

| Item | Check |
|---|---|
| `devflow --help` returns usage | See above |
| Connector repo checked out locally | Branch for the new feature |
| Paperclip issue created for the feature | Note the issue ID (UUID) |

### Decide Your Slug

Pick a short kebab-case slug for the feature. This becomes the directory name and
identifies the feature in all artifacts and metrics.

```
SLUG=my-connector-v2        # example — change this
ISSUE_ID=abc-123-...        # Paperclip issue UUID
```

All `devflow` commands below are run from inside the connector repo.

---

## Step 0 — Add devflow.yaml to Connector Repo

Create `devflow.yaml` at the **repo root** of the connector repo. This file is not
committed unless you want it permanently; it can live in a local branch or be
gitignored during the pilot.

```yaml
# devflow.yaml — connector repo pilot config
project:
  slug: my-connector-v2       # matches your $SLUG

stack: python                  # python | typescript

qa:
  coverage_command: pytest --cov=src --cov-report=term-missing
  coverage_threshold: 70       # % — override if needed

security:
  trigger_patterns:
    add: []                    # add extra patterns if needed
    remove: []

deploy:
  steps:
    - name: run migrations
      command: alembic upgrade head   # remove if no migrations
    - name: deploy prefect flow
      command: prefect deploy --all
    - name: smoke test
      command: python -m pytest tests/smoke/ -x

governance:
  waiver_authority:
    - paulrussell               # Paperclip username(s) who can grant waivers
```

**Adjust the `deploy.steps` section** to match how this connector is actually deployed.
Remove steps that don't apply.

---

## Step 1 — Initialise Feature Directory

```bash
cd $CONNECTOR_REPO
devflow init $ISSUE_ID --slug $SLUG
```

Expected output:
```
✓ Created features/$SLUG/
✓ State initialised: phase=grill, feature_type=connector
```

Verify:
```bash
ls features/$SLUG/
# → state.json (or Paperclip state if connected)
```

---

## Step 2 — Grill Phase

Orient and confirm the problem statement is clear before writing anything.

```bash
devflow orient $ISSUE_ID
```

Check the output for warnings (session age, unread comments). Address any before
continuing.

When satisfied:
```bash
devflow state set $ISSUE_ID grill_complete true
devflow seal $ISSUE_ID --completing grill
```

Expected: `✓ grill sealed`

---

## Step 3 — PRD Phase

### 3a. Gate (entering prd)
```bash
devflow gate $ISSUE_ID --entering prd
```
Expected: `✓ gate passed — entering prd`

### 3b. Run the PRD skill

In your AI tool of choice (Paperclip manually, or Claude directly), run:
```
/write-a-prd
```
targeting `features/$SLUG/specs/prd.md`. The skill writes the file locally.

Required sections (seal validates all five):
- `## Goal`
- `## Background`
- `## Scope`
- `## Acceptance Criteria`
- `## Security Scope` ← state explicitly whether security review is triggered

For a connector: add `## API Contract` if the connector exposes any HTTP endpoints.

### 3c. Seal
```bash
devflow seal $ISSUE_ID --completing prd
```

On pass:
```
✓ prd sealed — specs/prd.md valid
```

On failure, fix the missing sections and re-run seal.

### 3d. Set state + publish
```bash
devflow state set $ISSUE_ID prd_complete true
devflow publish-artifacts $ISSUE_ID --phase prd
```

---

## Step 4 — Plan Phase

### 4a. Gate
```bash
devflow gate $ISSUE_ID --entering plan
```

### 4b. Run skills
```
/prd-to-plan       → features/$SLUG/plans/plan.md
/architecture-diagrams → features/$SLUG/ops/architecture.md
```

`plan.md` required sections: `## Phases`, `## ADRs`, `## Rollback`, `## Verification Commands`

Diagram requirement: ≥ 2 Mermaid diagrams, OR add `## Diagrams — N/A` with justification.

### 4c. Seal
```bash
devflow seal $ISSUE_ID --completing plan
```

If Mermaid syntax fails and diagrams are not applicable:
```bash
devflow seal $ISSUE_ID --completing plan --waive-diagrams
```

### 4d. Request plan approval

Post the plan to Paperclip for human review. Once approved:
```bash
devflow state set $ISSUE_ID plan_approved true
devflow publish-artifacts $ISSUE_ID --phase plan
```

---

## Step 5 — Build Phase

### 5a. Gate
```bash
devflow gate $ISSUE_ID --entering build
```

For a connector this also checks `connectors/<name>/` scaffold exists. Create it if absent:
```bash
mkdir -p connectors/$SLUG/
```

### 5b. Run TDD skill (+ connector-build)

```
/tdd              → build/tdd-summary.md (Iron Law required)
/connector-build  → ops/connector-checklist.md (all 9 rows must be PASS)
```

Iron Law: `## Test Output` section must contain `PASSED N` or `N passed` from the real
test runner. Do not write this section by hand — copy verbatim from terminal output.

### 5c. Seal
```bash
devflow seal $ISSUE_ID --completing build
```

Common failure: Iron Law regex not matched. Check `## Test Output` contains the exact
pytest/unittest output line (e.g. `47 passed in 2.31s`).

### 5d. Publish
```bash
devflow publish-artifacts $ISSUE_ID --phase build
```

---

## Step 6 — Review Phase

### 6a. Gate
```bash
devflow gate $ISSUE_ID --entering review
```

### 6b. Run code-review skill (fresh context — do not reuse build session)

Open a new conversation with no prior context. Provide only:
- `features/$SLUG/specs/prd.md`
- `features/$SLUG/plans/plan.md`
- `features/$SLUG/build/tdd-summary.md`
- `git diff main...HEAD` output

```
/code-review    → ops/review-report.md
```

`review-report.md` must contain `**Decision:** PASS` or `**Decision:** FAIL`.

### 6c. If Decision = FAIL

Read the `## Findings` section. Fix the issues in the code, re-run TDD, then re-run
the review skill. Do not skip findings.

### 6d. Seal + publish
```bash
devflow seal $ISSUE_ID --completing review
devflow state set $ISSUE_ID review_passed true
devflow publish-artifacts $ISSUE_ID --phase review
```

---

## Step 7 — QA Phase

### 7a. Gate
```bash
devflow gate $ISSUE_ID --entering qa
```

### 7b. Run QA skill

Connector minimum: **Tier 3** (unit + integration + contract tests).

```
/qa    → qa/evidence.md
```

`evidence.md` must contain:
- `**Tier:** 3`
- `**coverage_pct:** <number>` — run `pytest --cov` and record the result
- `## Test Output` — verbatim pytest output
- `## Connector QA` — contract test result must show PASS

Coverage threshold for connectors: 70%. If below:
```bash
devflow seal $ISSUE_ID --completing qa --waive-coverage
# Only use if you have a legitimate reason; posts a waiver record to the manifest
```

### 7c. Seal + publish
```bash
devflow seal $ISSUE_ID --completing qa
devflow publish-artifacts $ISSUE_ID --phase qa
```

---

## Step 8 — Security Phase (parallel with QA)

Run security review in a fresh context at the same time as QA (or immediately after).

### 8a. Check if security review is triggered

Look at `features/$SLUG/specs/prd.md → ## Security Scope`. If the PRD says security
review is triggered, or if any changed file matches a trigger pattern (auth, middleware,
schema changes, new API endpoints, PII keywords), proceed.

If not triggered:
```bash
devflow state set $ISSUE_ID security_triggered false
# Skip to Step 9
```

### 8b. Run security-review skill (Opus tier required)

```
/security-review    → qa/security-review.md
```

`security-review.md` must contain:
- `**max_severity:** none|low|medium|high|critical`
- `**sign_off:** <agent-id>`

### 8c. Seal + publish
```bash
devflow seal $ISSUE_ID --completing security
devflow publish-artifacts $ISSUE_ID --phase security
```

State is automatically updated: `max_severity = <value from seal>`

### 8d. If max_severity = high

The deploy gate will block. A human must post a `GATE-WAIVER` comment on the Paperclip
issue before proceeding:

```
GATE-WAIVER
gate: security-severity
reason: <justification — tracked in which ticket>
approved-by: paulrussell
expires: YYYY-MM-DD
```

### 8e. If max_severity = critical

**Hard stop.** Do not proceed. Escalate to the team. The deploy gate cannot be waived
for critical severity — the code must be fixed.

---

## Step 9 — Deploy Phase

### 9a. Gate
```bash
devflow gate $ISSUE_ID --entering deploy
```

This checks:
- `max_severity ≤ medium` OR valid `GATE-WAIVER` comment present
- `qa/evidence.md` exists
- `qa/evidence.md` has `## Connector QA` section with contract test PASS
- `qa/security-review.md` exists (if `security_triggered = true`)

### 9b. Run deploy skill

```
/deploy    → ops/deploy-steps.md
```

The deploy skill executes the steps defined in `devflow.yaml → deploy.steps` in order,
capturing timestamps and health check output.

`deploy-steps.md` must contain:
- `## Steps` with ≥ 1 executed step + timestamp
- `## Rollback` with ≥ 1 rollback command
- `## Health Checks` with ≥ 1 command run post-deploy with output

### 9c. Seal + publish
```bash
devflow seal $ISSUE_ID --completing deploy
devflow publish-artifacts $ISSUE_ID --phase deploy
```

---

## Step 10 — Done

### 10a. Seal done
```bash
devflow seal $ISSUE_ID --completing done
```

This writes `artifact_contract_met: true` to `verification-manifest.json` and updates
the manifest on disk.

### 10b. Gate done (final validation)
```bash
devflow gate $ISSUE_ID --entering done
```

Expected:
```
✓ gate passed — all artifact contract conditions met
```

### 10c. Publish final manifest
```bash
devflow publish-artifacts $ISSUE_ID --phase done
```

### 10d. Metrics
```bash
devflow metrics --slug $SLUG
```

Expected output:
```
feature: my-connector-v2
  iron_law_met:          true
  artifact_contract_met: true
  coverage_pct:          74.2
  max_severity:          low
  waivers:               0
  warnings:              1
```

If all checks pass: close the Paperclip issue and move to the Validation phase
(3 fully autonomous runs).

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gate blocked: state.prd_complete is not set` | Forgot `devflow state set` | `devflow state set $ISSUE_ID prd_complete true` |
| `Iron Law check failed` | `## Test Output` has no regex match | Paste verbatim pytest output; check for `N passed` pattern |
| `artifact missing: connectors/` | Connector scaffold not created | `mkdir -p connectors/$SLUG` |
| `gate blocked: max_severity is 'high'` | Security found high severity findings | Post `GATE-WAIVER` comment on Paperclip issue |
| `publish-artifacts: BLOCKED` | Critical artifact upload failed 3 times | Check Paperclip API connectivity; retry |
| `coverage_pct below threshold` | Tests cover < 70% | Write more tests, or `--waive-coverage` with justification |
| `## Connector QA section missing` | QA skill didn't run connector checks | Re-run `/qa` with connector context; add `## Connector QA` section |

---

## Success Criteria

The pilot is complete when:

- [ ] All 9 artifacts present on Paperclip issue as documents
- [ ] `verification-manifest.json` has `artifact_contract_met: true`
- [ ] `iron_law_met: true` in manifest
- [ ] `coverage_pct ≥ 70` (or waiver recorded with justification)
- [ ] `max_severity ≤ medium` (or `high` with valid waiver)
- [ ] `devflow metrics --slug $SLUG` shows 0 hard blocks
- [ ] 0 phases manually bypassed (no `--skip-gate` flags used)

Once the pilot passes all criteria, proceed to Validation phase:
create 3 more connector issues in Paperclip and let the agents run autonomously
end-to-end without manual intervention.
