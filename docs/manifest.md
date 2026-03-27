# devflow.yaml — Manifest Schema

The manifest captures project-level tooling configuration for a specific repo + branch combination. It is written once by `ai init` and consumed by `ai prep`, `ai qa`, `ai deploy`, and `ai prefect-run`.

---

## Location

```
<NOTES_ROOT>/<repo>/<branch>/devflow.yaml
```

Example (with `AI_DEV_FLOW_NOTES_ROOT=/c/Users/PaulRussell/Documents/ai-dev-flow`):

```
/c/Users/PaulRussell/Documents/ai-dev-flow/my-app/main/devflow.yaml
```

---

## Fields

### `env`

| Field | Type | Description |
|-------|------|-------------|
| `venv` | string | Path to the virtual environment directory (e.g. `.venv`) |
| `bootstrap` | list[string] | Commands to run during `ai prep` to set up the environment |

### `services[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name for the service |
| `start` | string | Shell command to start the service |
| `health` | string (optional) | Shell command to verify the service is running; non-zero exit = unhealthy |

### `qa.suites[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name for the suite (e.g. `Unit`, `Smoke`) |
| `command` | string | Shell command to run the suite |
| `artifact` | string | Relative path (from branch root) to write the output. Use `%slug%` as a placeholder for the feature slug. |

### `deploy.steps`

| Field | Type | Description |
|-------|------|-------------|
| `steps` | list[string] | Ordered deploy commands. Run sequentially by `ai deploy`. |

### `prefect`

| Field | Type | Description |
|-------|------|-------------|
| `sandbox_start` | string (optional) | Command to start the local Prefect sandbox (e.g. `docker compose -f scripts/prefect-sandbox.yml up -d`) |
| `run_command` | string (optional) | Command to execute the Prefect flow |
| `assertions[]` | list (optional) | Post-run assertions (see below) |

### `prefect.assertions[]`

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Assertion label |
| `command` | string | Shell command; zero exit = pass |
| `artifact` | string | Relative artifact path (supports `%slug%`) |

---

## The `%slug%` placeholder

In `qa.suites[].artifact` and `prefect.assertions[].artifact`, the string `%slug%` is replaced at runtime with the feature slug passed to the command (e.g. `ai qa "sample-sync"` → slug `sample-sync`).

This allows a single manifest to cover many features without duplication.

---

## Complete example

```yaml
env:
  venv: .venv
  bootstrap:
    - pip install -r requirements.txt

services:
  - name: api
    start: uvicorn app.main:app --port 8000 &
    health: curl -sf http://localhost:8000/health

qa:
  suites:
    - name: Unit
      command: pytest tests/unit
      artifact: features/%slug%/qa/unit.md
    - name: Smoke
      command: pytest tests/smoke
      artifact: features/%slug%/qa/smoke.md

deploy:
  steps:
    - docker build -t my-app .
    - docker push registry/my-app:latest

prefect:
  sandbox_start: docker compose -f scripts/prefect-sandbox.yml up -d
  run_command: python flows/sync_flow.py
  assertions:
    - name: rows_emitted
      command: python scripts/assert_rows.py --min 10
      artifact: features/%slug%/qa/assertions.md
```

---

## `features/index.json` — Backlog schema

Lives at `<NOTES_ROOT>/<repo>/<branch>/features/index.json`. Consumed by `ai loop`.

```json
{
  "features": [
    {
      "slug": "sample-sync",
      "priority": 1,
      "goal": "deploy",
      "last_run": null,
      "status": "pending",
      "last_stage": null,
      "evidence": null
    },
    {
      "slug": "sample-report",
      "priority": 2,
      "goal": "qa",
      "last_run": null,
      "status": "pending",
      "last_stage": null,
      "evidence": null
    }
  ]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `slug` | string | Feature slug — must match the directory name under `features/` |
| `priority` | integer | Execution order; lower runs first. Ties sorted alphabetically by slug. |
| `goal` | string | Furthest stage to attempt: `prep`, `feature`, `tdd`, `qa`, `prefect`, `deploy` |
| `last_run` | string \| null | ISO 8601 timestamp of the last `ai loop` run — written by `ai loop` |
| `status` | string | `pending`, `pass`, or `fail` — written by `ai loop` |
| `last_stage` | string \| null | Last stage completed — written by `ai loop` |
| `evidence` | string \| null | Path to `qa/evidence.md` if present — written by `ai loop` |

### Stage order (for `goal` and `ai run --to`)

`prep` → `feature` → `tdd` → `qa` → `prefect` → `deploy`

---

## `ai backlog-add` — Seeding the index from stubs

After `ai new-project` writes `features/<slug>/intake/stub.md` files, run `ai backlog-add` to register them in `features/index.json`.

The command scans for any slug directory that has an `intake/stub.md` but no entry in the index, then prompts:

1. **Default goal** for all new features (bulk, e.g. `deploy`)
2. **Starting priority** (auto-increments from the current max)
3. **Per-feature overrides** — press Enter to accept the bulk default

This keeps `ai new-project` as a pure Claude-driven ideation step while giving you explicit control over what enters the execution backlog and at what priority.

---

## `ai run` — Stage pipeline

`ai run <slug>` runs stages sequentially. Each stage maps to an existing CLI mode:

| Stage | CLI mode | Completion signal |
|-------|----------|-------------------|
| `prep` | `ai prep` | `'prep' in state.completed` |
| `feature` | `ai feature` | `plans/plan.md` exists |
| `tdd` | `ai tdd` | `build/tdd-summary.md` exists |
| `qa` | `ai qa` | `state.qa.unit == 'pass'` |
| `prefect` | `ai prefect-run` | `state.qa['prefect-run'] == 'pass'` |
| `deploy` | `ai deploy` | `state.deploy.status == 'success'` |

Already-complete stages are skipped. Interactive stages (`feature`, `tdd`) launch the Claude GUI/CLI and pause — re-run `ai run` after the session to continue.

Writes `features/<slug>/ops/run-log.md` summarising stage statuses and timestamps.

### Flags

| Flag | Description |
|------|-------------|
| `--from <stage>` | Start at this stage (skip all earlier) |
| `--to <stage>` | Stop after this stage |
| `--skip-tdd` | Skip the `tdd` stage entirely |
| `--skip-qa` | Skip the `qa` stage entirely |
| `--skip-prefect` | Skip the `prefect` stage entirely |
| `--skip-deploy` | Skip the `deploy` stage entirely |

---

## `ai loop` — Backlog automation

Loads `features/index.json`, filters by `--goal`, sorts by priority, and calls `ai run <slug> --to <goal>` for each entry. After each run, updates `index.json` with `last_run`, `status`, `last_stage`, and `evidence`.

### Flags

| Flag | Description |
|------|-------------|
| `--goal <stage>` | Only run features whose `goal ≥ stage`; also sets `--to <stage>` for each run (default: `deploy`) |
| `--limit N` | Process at most N features per invocation |
| `--stop-on-fail` | Abort the loop on the first failing feature |
| `--skip-tdd` | Forwarded to every `ai run` call |
| `--skip-qa` | Forwarded to every `ai run` call |
| `--skip-prefect` | Forwarded to every `ai run` call |
| `--skip-deploy` | Forwarded to every `ai run` call |

**Human-approval note:** `ai run` (and therefore `ai loop`) still requires human interaction for `feature` (Claude GUI) and `tdd` (Claude Code CLI) stages. Everything else — `prep`, `qa`, `prefect`, `deploy` — runs fully automatically.
