---
name: deploy
description: Execute the deploy steps from devflow.yaml, run health checks, and produce ops/deploy-steps.md. Use when the deploy phase begins, the user asks to deploy, or devflow gate confirms deploy preconditions are met.
---

# Deploy

Produces `ops/deploy-steps.md` for the current feature. Called by `devflow-sre` during the Deploy phase.

## Preconditions

Before running any deploy step, confirm the gate has passed:

```bash
devflow gate --entering deploy --slug <slug> --issue-id <id>
```

Gate verifies:
- `qa/evidence.md` is present
- `qa/security-review.md` is present (if `state.security_triggered = true`)
- `state.max_severity` ≤ medium (or a valid waiver is present)

**Do not proceed if the gate returns exit 1.**

## Inputs

1. `plans/plan.md` — `## Verification Commands` section (post-deploy checks specified by the planner)
2. `devflow.yaml` — `deploy.steps[]` (ordered deploy commands for this project)
3. `qa/evidence.md` — tier + coverage confirmation
4. `qa/security-review.md` — max_severity confirmation (if triggered)

## Process

### Step 1: Read deploy steps

Load `deploy.steps[]` from `devflow.yaml`. If no deploy steps are configured, document that in `ops/deploy-steps.md` and skip to Step 4.

```yaml
# Example devflow.yaml deploy section
deploy:
  steps:
    - name: "Database migrations"
      command: "python manage.py migrate"
      health_check: "python manage.py check --database default"
    - name: "Restart application"
      command: "systemctl restart myapp"
      health_check: "curl -sf http://localhost:8000/health"
  rollback:
    - "systemctl stop myapp"
    - "python manage.py migrate --fake <previous-migration>"
    - "systemctl start myapp"
```

### Step 2: Validate prerequisites

```
[ ] All deploy commands exist in the current environment (which/where check)
[ ] Rollback procedure is documented (devflow.yaml deploy.rollback[] or plans/plan.md ## Rollback)
[ ] Health check commands are runnable
[ ] Target environment is confirmed (dev/staging/prod)
```

### Step 3: Execute steps sequentially

For each step in `deploy.steps[]`:

1. Print the step name and command
2. Execute the command
3. Capture stdout/stderr
4. If a `health_check` is defined for this step: run it immediately after
5. If the health check fails or the step exits non-zero:
   - **Stop immediately** — do not continue to the next step
   - Execute the rollback procedure (Step 4)
   - Post findings to Paperclip and exit

Record each step's result (command, status, duration) in the artifact.

### Step 4: Rollback procedure

Rollback is triggered when any step or health check fails. Execute rollback steps from `devflow.yaml deploy.rollback[]` or `plans/plan.md ## Rollback` in order.

After rollback:
- Post a comment to the Paperclip issue describing which step failed and the rollback outcome
- Set issue status to `blocked`
- Do not mark the deploy phase as complete

### Step 5: Post-deploy verification

Run verification commands from `plans/plan.md ## Verification Commands`. Record each command's output and pass/fail result.

### Step 6: Write the artifact

Write `ops/deploy-steps.md` (relative to the feature root). Overwrite on each run.

## Output artifact: `ops/deploy-steps.md`

```markdown
# Deploy Steps: <feature-slug>

**Deployed at:** <ISO 8601>
**Environment:** <dev|staging|prod>
**Branch:** <branch>
**Commit:** <full sha>

## Steps Executed
| # | Name | Command | Status | Duration |
|---|---|---|---|---|
| 1 | <step name> | `<command>` | PASS/FAIL | <Xs> |

## Health Checks
| Check | Command | Result |
|---|---|---|
| <check name> | `<command>` | PASS/FAIL |

## Rollback
Steps to revert if deploy fails:
1. `<rollback command>`
2. `<rollback command>`

## Verification Evidence
| Command | Output (excerpt) | Pass? |
|---|---|---|
| `<verification command>` | <first line of output> | PASS |

## Release Notes
### What changed
- <one bullet per Acceptance Criterion delivered>

### Breaking changes
- <none | description>

### Known issues
- <none | description>
```

**Fill every section. Do not leave placeholder text.** The `## Rollback` section must contain ≥ 1 actual rollback step. The `## Health Checks` section must contain ≥ 1 check.

## Seal validation

`devflow seal --completing deploy` checks:
- `## Rollback` section present with ≥ 1 non-empty line
- `## Health Checks` section present with ≥ 1 non-empty line

If seal fails: add the missing section(s) based on actual deploy evidence and re-run seal.

## Escalation paths

| Situation | Action |
|---|---|
| Step fails, rollback succeeds | Post findings; set issue to blocked; notify human |
| Step fails, rollback also fails | Post CRITICAL findings; notify team immediately; do not attempt further automation |
| Health check fails post-deploy | Treat as step failure — trigger rollback |
| Verification command fails | Post warning; human confirmation required before marking done |
