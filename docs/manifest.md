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
