# WS18 Pilot Runbook — Manual Connector Feature (CLI Layer)
**Version:** 1.2
**Purpose:** Step-by-step guide for manually running one connector feature through
the full v3 pipeline using the `devflow` CLI. No Paperclip agent automation required.
This proves the gate/seal/publish machinery before handing off to agents.

**Time estimate:** 2–4 hours for a real connector; 30 min for a smoke test.

---

## How devflow CLI Works

### Running commands

`ai-dev-flow` sits as a sibling directory above your other repos. Run all `devflow`
commands from inside the connector repo. You have two options:

**Option A — entry point script (recommended):**
```bash
# Add to your shell profile (~/.bashrc or ~/.bash_profile)
alias devflow="python /path/to/ai-dev-flow/devflow/cli.py"
```

**Option B — installed package:**
```bash
cd /path/to/ai-dev-flow && pip install -e .
# then `devflow` works from any directory
```

Verify:
```bash
devflow --help
```

### State management

State is stored in Paperclip (`PAPERCLIP_API_KEY` set + `--issue-id` on every command).
The `--issue-id` flag is required throughout this runbook — it is how state fields
written by seal (`iron_law_met`, `max_severity`, etc.) land in Paperclip and are
readable by the agent layer when you hand over.

Fields that aren't auto-written by seal (`prd_complete`, `plan_approved`,
`review_passed`) must be set via the Paperclip state document directly or using the
one-liners provided in each step.

---

## Before You Start

### Prerequisites

| Item | Check |
|---|---|
| `devflow --help` returns usage | See setup above |
| `PAPERCLIP_API_KEY` set in environment | `echo $PAPERCLIP_API_KEY` |
| Connector repo checked out locally | Branch for the new feature |
| Paperclip issue created for this feature | Note the UUID |

### Set your variables

```bash
SLUG=my-connector-v2        # short kebab-case slug — your choice
ISSUE_ID=abc-123-...        # Paperclip issue UUID — required
```

All `devflow` commands below are run from inside the connector repo.

---

## Step 0 — Add devflow.yaml to Connector Repo

Create `devflow.yaml` at the **repo root** of the connector repo.

```yaml
# devflow.yaml — connector repo pilot config
project:
  slug: my-connector-v2       # matches your $SLUG

stack: python

qa:
  coverage_command: pytest --cov=src --cov-report=term-missing
  coverage_threshold: 70

deploy:
  steps:
    - name: deploy prefect flow
      command: prefect deploy --all
    - name: smoke test
      command: python -m pytest tests/smoke/ -x

governance:
  waiver_authority:
    - paulrussell
```

Adjust `deploy.steps` to match how this connector is actually deployed.

---

## Step 1 — Initialise Feature Directory

```bash
mkdir -p features/$SLUG/ops

cat > features/$SLUG/ops/state.json << 'EOF'
{
  "schema_version": "v3",
  "feature_type": "connector",
  "slug": "my-connector-v2"
}
EOF
```

Replace `my-connector-v2` with your actual `$SLUG`.

---

## Step 2 — Grill Phase

```bash
devflow orient --slug $SLUG --issue-id $ISSUE_ID
```

When satisfied, mark grill complete and seal:

```bash
python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['grill_complete']=True; json.dump(s,open(p,'w'),indent=2)
"

devflow seal --completing grill --slug $SLUG --issue-id $ISSUE_ID
```

Expected: `✓ grill sealed`

---

## Step 3 — PRD Phase

### Gate
```bash
devflow gate --entering prd --slug $SLUG --issue-id $ISSUE_ID
```

### Write the PRD

Run `/write-a-prd` → `features/$SLUG/specs/prd.md`

Required sections:
- `## Goal`
- `## Background`
- `## Scope`
- `## Acceptance Criteria`
- `## Security Scope` ← state explicitly whether security review is triggered

### Seal + mark state + publish
```bash
devflow seal --completing prd --slug $SLUG --issue-id $ISSUE_ID

python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['prd_complete']=True; json.dump(s,open(p,'w'),indent=2)
"

devflow publish-artifacts --phase prd --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 4 — Plan Phase

### Gate
```bash
devflow gate --entering plan --slug $SLUG --issue-id $ISSUE_ID
```

### Write the plan

Run `/prd-to-plan` → `features/$SLUG/plans/plan.md`
Run `/architecture-diagrams` → `features/$SLUG/ops/architecture.md`

Required sections in `plan.md`: `## Phases`, `## ADRs`, `## Rollback`, `## Verification Commands`

Diagram requirement: ≥ 2 Mermaid diagrams, or `## Diagrams — N/A` with justification.

### Seal + mark state + publish
```bash
devflow seal --completing plan --slug $SLUG --issue-id $ISSUE_ID
# If diagrams not applicable:
devflow seal --completing plan --slug $SLUG --issue-id $ISSUE_ID --waive-diagrams

python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['plan_approved']=True; json.dump(s,open(p,'w'),indent=2)
"
# In the agent layer, plan_approved is set after human review in Paperclip.
# For the manual pilot, set it once you're satisfied with the plan.

devflow publish-artifacts --phase plan --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 5 — Build Phase

### Gate
```bash
devflow gate --entering build --slug $SLUG --issue-id $ISSUE_ID --feature-type connector
```

Connector check: `connectors/<name>/` scaffold must exist:
```bash
mkdir -p connectors/$SLUG
```

### Run TDD + connector-build skills

```
/tdd             → features/$SLUG/build/tdd-summary.md
/connector-build → features/$SLUG/ops/connector-checklist.md
```

Iron Law: `## Test Output` must contain verbatim pytest output with `N passed`.
Copy from terminal — do not write this by hand.

### Seal + publish
```bash
devflow seal --completing build --slug $SLUG --issue-id $ISSUE_ID
# iron_law_met: true is written to Paperclip state automatically on pass

devflow publish-artifacts --phase build --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 6 — Review Phase

### Gate
```bash
devflow gate --entering review --slug $SLUG --issue-id $ISSUE_ID
```

### Run code-review skill (fresh context — do not reuse build session)

Provide only: `specs/prd.md`, `plans/plan.md`, `build/tdd-summary.md`, `git diff main...HEAD`

```
/code-review    → features/$SLUG/ops/review-report.md
```

Must contain `**Decision:** PASS` or `**Decision:** FAIL`.

If FAIL: fix the findings, re-run TDD, re-run the review. Do not skip findings.

### Seal + mark state + publish
```bash
devflow seal --completing review --slug $SLUG --issue-id $ISSUE_ID

python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['review_passed']=True; json.dump(s,open(p,'w'),indent=2)
"

devflow publish-artifacts --phase review --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 7 — QA Phase

### Gate
```bash
devflow gate --entering qa --slug $SLUG --issue-id $ISSUE_ID
```

### Run QA skill (Tier 3 required for connectors)

```
/qa    → features/$SLUG/qa/evidence.md
```

`evidence.md` must contain:
- `**Tier:** 3`
- `**coverage_pct:** <number>` — run `pytest --cov` and record exactly
- `## Test Output` — verbatim pytest output
- `## Connector QA` — contract test result must show PASS

### Seal + publish
```bash
devflow seal --completing qa --slug $SLUG --issue-id $ISSUE_ID
# If coverage < 70% with justification:
devflow seal --completing qa --slug $SLUG --issue-id $ISSUE_ID --waive-coverage

devflow publish-artifacts --phase qa --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 8 — Security Phase

Check `## Security Scope` in the PRD. If not triggered:
```bash
python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['security_triggered']=False; json.dump(s,open(p,'w'),indent=2)
"
# Skip to Step 9
```

If triggered:

### Run security-review skill (Opus tier — most capable model)

```
/security-review    → features/$SLUG/qa/security-review.md
```

Must contain `**max_severity:** <level>` and `**sign_off:** <agent-id>`.

### Seal + publish
```bash
devflow seal --completing security --slug $SLUG --issue-id $ISSUE_ID
# max_severity is written to Paperclip state automatically on pass

devflow publish-artifacts --phase security --slug $SLUG --issue-id $ISSUE_ID
```

**If max_severity = high:** post a `GATE-WAIVER` comment on the Paperclip issue:
```
GATE-WAIVER
gate: security-severity
reason: <justification>
approved-by: paulrussell
expires: YYYY-MM-DD
```

**If max_severity = critical:** hard stop. Fix the code. Cannot be waived.

---

## Step 9 — Deploy Phase

### Gate
```bash
devflow gate --entering deploy --slug $SLUG --issue-id $ISSUE_ID
```

Checks: `max_severity ≤ medium` (or GATE-WAIVER present), `qa/evidence.md` with
`## Connector QA` PASS, `security-review.md` if triggered.

### Run deploy skill

```
/deploy    → features/$SLUG/ops/deploy-steps.md
```

Must contain `## Steps`, `## Rollback` (≥ 1 step), `## Health Checks` (≥ 1 command).

### Seal + publish
```bash
devflow seal --completing deploy --slug $SLUG --issue-id $ISSUE_ID
devflow publish-artifacts --phase deploy --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 10 — Done

```bash
devflow seal --completing done --slug $SLUG --issue-id $ISSUE_ID
devflow gate --entering done --slug $SLUG --issue-id $ISSUE_ID
devflow publish-artifacts --phase done --slug $SLUG --issue-id $ISSUE_ID
devflow metrics --slug $SLUG
```

Expected:
```
feature: my-connector-v2
  iron_law_met:          true
  artifact_contract_met: true
  coverage_pct:          74.2
  max_severity:          low
  waivers:               0
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `gate blocked: state.prd_complete is not set` | Forgot state one-liner | Run the `prd_complete` one-liner from Step 3 |
| `Iron Law check failed` | `## Test Output` has no regex match | Paste verbatim pytest output; must contain `N passed` |
| `gate blocked: connectors/ directory does not exist` | Scaffold missing | `mkdir -p connectors/$SLUG` |
| `gate blocked: max_severity is 'high'` | Security findings | Post `GATE-WAIVER` comment on Paperclip issue |
| `gate blocked: max_severity is 'critical'` | Critical security finding | Fix the code — cannot be waived |
| `publish-artifacts: BLOCKED` | Critical artifact upload failed | Check `PAPERCLIP_API_KEY`; retry |
| `coverage_pct below threshold` | Tests cover < 70% | Write more tests or `--waive-coverage` with justification |
| `## Connector QA section missing` | QA skill missed connector checks | Re-run `/qa` with connector context |
| `devflow: command not found` | CLI not on PATH | Check alias or `pip install -e .` |

---

## Success Criteria

- [ ] All 9 artifacts present in `features/$SLUG/`
- [ ] `devflow metrics --slug $SLUG` shows `artifact_contract_met: true`
- [ ] `iron_law_met: true`
- [ ] `coverage_pct ≥ 70` (or waiver recorded)
- [ ] `max_severity ≤ medium` (or `high` with valid waiver)
- [ ] 0 phases manually bypassed

Once all criteria pass, proceed to the agent layer: create a connector issue in
Paperclip and let `devflow-feature` → `devflow-builder` → `devflow-reviewer` →
`devflow-qa` → `devflow-sre` run end-to-end without manual intervention.
