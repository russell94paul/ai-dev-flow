# WS18 Pilot Runbook — Manual Connector Feature (CLI Layer)
**Version:** 1.1
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
export PATH="/path/to/ai-dev-flow/bin:$PATH"
# or just alias it:
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

State is stored in two places depending on your setup:

- **With Paperclip** (`PAPERCLIP_API_KEY` set + `--issue-id`): state loads from and
  saves to the Paperclip issue document automatically.
- **Without Paperclip** (local-only pilot): state falls back to
  `features/<slug>/ops/state.json`. You edit this file manually between phases
  for fields that aren't auto-written by seal (e.g. `prd_complete`, `plan_approved`).

The pilot works either way. If you have `PAPERCLIP_API_KEY` set, add
`--issue-id $ISSUE_ID` to every `gate`, `seal`, and `orient` command and state
stays in Paperclip automatically.

---

## Before You Start

### Prerequisites

| Item | Check |
|---|---|
| `devflow --help` returns usage | See above |
| Connector repo checked out locally | Branch for the new feature |
| Paperclip issue created (optional for CLI layer pilot) | Note the UUID if using |

### Set your variables

```bash
SLUG=my-connector-v2        # short kebab-case slug — your choice
ISSUE_ID=abc-123-...        # Paperclip issue UUID (omit if local-only pilot)
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

Adjust `deploy.steps` to match how this connector is actually deployed. Remove steps
that don't apply.

---

## Step 1 — Initialise Feature Directory

There is no `devflow init` command — create the directory and initial state manually:

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
devflow orient --slug $SLUG          # optional; checks session health
```

When ready, mark grill complete in the state file:

```bash
python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['grill_complete']=True; json.dump(s,open(p,'w'),indent=2)
"
```

Seal:
```bash
devflow seal --completing grill --slug $SLUG
```

Expected: `✓ grill sealed`

---

## Step 3 — PRD Phase

### Gate
```bash
devflow gate --entering prd --slug $SLUG
```
Expected: `✓ gate passed`

### Write the PRD

Run `/write-a-prd` (skill) targeting `features/$SLUG/specs/prd.md`.

Required sections (seal validates all five):
- `## Goal`
- `## Background`
- `## Scope`
- `## Acceptance Criteria`
- `## Security Scope` ← state explicitly whether security review is triggered

### Seal
```bash
devflow seal --completing prd --slug $SLUG
```

On failure, fix the missing sections and re-run.

### Mark state + publish
```bash
python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['prd_complete']=True; json.dump(s,open(p,'w'),indent=2)
"

# Only if PAPERCLIP_API_KEY is set:
devflow publish-artifacts --phase prd --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 4 — Plan Phase

### Gate
```bash
devflow gate --entering plan --slug $SLUG
```

### Write the plan

Run `/prd-to-plan` → `features/$SLUG/plans/plan.md`
Run `/architecture-diagrams` → `features/$SLUG/ops/architecture.md`

`plan.md` required sections: `## Phases`, `## ADRs`, `## Rollback`, `## Verification Commands`

Diagram requirement: ≥ 2 Mermaid diagrams, or `## Diagrams — N/A` with justification.

### Seal
```bash
devflow seal --completing plan --slug $SLUG
# If diagrams not applicable:
devflow seal --completing plan --slug $SLUG --waive-diagrams
```

### Mark state + publish
```bash
python -c "
import json; p='features/$SLUG/ops/state.json'
s=json.load(open(p)); s['plan_approved']=True; json.dump(s,open(p,'w'),indent=2)
"
# Note: in the agent layer, plan_approved is set after a human reviews and approves
# the plan in Paperclip. For the manual pilot, set it yourself once you're happy.

devflow publish-artifacts --phase plan --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 5 — Build Phase

### Gate
```bash
devflow gate --entering build --slug $SLUG --feature-type connector
```

This also checks `connectors/<name>/` scaffold exists. Create it if absent:
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

### Seal
```bash
devflow seal --completing build --slug $SLUG
```

State updates (`iron_law_met: true`) are written automatically on pass.

### Publish
```bash
devflow publish-artifacts --phase build --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 6 — Review Phase

### Gate
```bash
devflow gate --entering review --slug $SLUG
```

### Run code-review skill (fresh context — do not reuse build session)

Provide only: `specs/prd.md`, `plans/plan.md`, `build/tdd-summary.md`, `git diff main...HEAD`

```
/code-review    → features/$SLUG/ops/review-report.md
```

Must contain `**Decision:** PASS` or `**Decision:** FAIL`.

### If Decision = FAIL

Fix the findings, re-run TDD, re-run the review skill. Do not skip findings.

### Seal + mark state + publish
```bash
devflow seal --completing review --slug $SLUG

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
devflow gate --entering qa --slug $SLUG
```

### Run QA skill

Connector minimum: **Tier 3** (unit + integration + contract tests).

```
/qa    → features/$SLUG/qa/evidence.md
```

`evidence.md` must contain:
- `**Tier:** 3`
- `**coverage_pct:** <number>` — run `pytest --cov` and record exactly
- `## Test Output` — verbatim pytest output
- `## Connector QA` — contract test result must show PASS

### Seal
```bash
devflow seal --completing qa --slug $SLUG
# If coverage < 70% with justification:
devflow seal --completing qa --slug $SLUG --waive-coverage
```

### Publish
```bash
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

### Run security-review skill (Opus tier required — use the most capable model)

```
/security-review    → features/$SLUG/qa/security-review.md
```

Must contain `**max_severity:** <level>` and `**sign_off:** <agent-id>`.

### Seal
```bash
devflow seal --completing security --slug $SLUG
```

State update (`max_severity`) is written automatically.

### If max_severity = high

Post a `GATE-WAIVER` comment on the Paperclip issue before proceeding:

```
GATE-WAIVER
gate: security-severity
reason: <justification>
approved-by: paulrussell
expires: YYYY-MM-DD
```

### If max_severity = critical

Hard stop. Fix the code. This cannot be waived.

### Publish
```bash
devflow publish-artifacts --phase security --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 9 — Deploy Phase

### Gate
```bash
devflow gate --entering deploy --slug $SLUG
```

Checks: `max_severity ≤ medium` (or GATE-WAIVER), `qa/evidence.md` present with
`## Connector QA` section, `security-review.md` present if triggered.

### Run deploy skill

```
/deploy    → features/$SLUG/ops/deploy-steps.md
```

Must contain `## Steps`, `## Rollback` (≥ 1 step), `## Health Checks` (≥ 1 command).

### Seal + publish
```bash
devflow seal --completing deploy --slug $SLUG
devflow publish-artifacts --phase deploy --slug $SLUG --issue-id $ISSUE_ID
```

---

## Step 10 — Done

```bash
# Seal done — writes artifact_contract_met: true to manifest
devflow seal --completing done --slug $SLUG

# Final gate check
devflow gate --entering done --slug $SLUG

# Publish final manifest
devflow publish-artifacts --phase done --slug $SLUG --issue-id $ISSUE_ID

# Metrics
devflow metrics --slug $SLUG
```

Expected metrics output:
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
| `gate blocked: state.prd_complete is not set` | Forgot to update state.json | Run the python state-update one-liner for `prd_complete` |
| `Iron Law check failed` | `## Test Output` has no regex match | Paste verbatim pytest output; must contain `N passed` |
| `gate blocked: connectors/ directory does not exist` | Connector scaffold missing | `mkdir -p connectors/$SLUG` |
| `gate blocked: max_severity is 'high'` | Security findings | Post `GATE-WAIVER` comment on Paperclip issue |
| `gate blocked: max_severity is 'critical'` | Critical security finding | Fix the code — cannot be waived |
| `publish-artifacts: BLOCKED` | Critical artifact upload failed | Check `PAPERCLIP_API_KEY`; retry |
| `coverage_pct below threshold` | Tests cover < 70% | Write more tests or `--waive-coverage` with justification |
| `## Connector QA section missing` | QA skill missed connector checks | Re-run `/qa` with connector context |
| `devflow: command not found` | CLI not on PATH | Check your alias or `pip install -e .` |

---

## Success Criteria

The pilot is complete when:

- [ ] All 9 artifacts present in `features/$SLUG/`
- [ ] `devflow metrics --slug $SLUG` shows `artifact_contract_met: true`
- [ ] `iron_law_met: true`
- [ ] `coverage_pct ≥ 70` (or waiver recorded)
- [ ] `max_severity ≤ medium` (or `high` with valid waiver)
- [ ] 0 phases manually bypassed

Once all criteria pass, proceed to the agent layer: create a connector issue in
Paperclip and let `devflow-feature` → `devflow-builder` → `devflow-reviewer` →
`devflow-qa` → `devflow-sre` run end-to-end without manual intervention.
