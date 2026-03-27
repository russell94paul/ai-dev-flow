# ai-dev-flow

A structured AI-driven development workflow. Transforms ad-hoc prompting into a repeatable, artifact-producing process.

---

## Commands

### `ai init`

Runs an interactive manifest wizard in the terminal. Detects project capabilities (requirements.txt, Prefect, pytest, Docker) and prompts for configuration. Writes a `devflow.yaml` manifest to the branch root in your notes vault.

```bash
ai init
# → detects capabilities, prompts for config
# → writes <NOTES_ROOT>/<repo>/<branch>/devflow.yaml
```

See [docs/manifest.md](docs/manifest.md) for the full schema.

---

### `ai feature "<idea>"`

Runs the GRILL → PRD → DIAGRAM → PLAN lifecycle in Claude chat.

- Grills you on requirements one question at a time
- Produces a structured PRD
- Generates Mermaid system-context and sequence diagrams
- Breaks the PRD into a phased implementation plan with acceptance criteria
- Writes artifacts to the notes vault under `specs/` and `plans/`

When the plan is confirmed, Claude prints:
```
PLAN COMPLETE. To begin TDD run: ai tdd "<feature-slug>"
```

---

### `ai tdd "<feature-slug>"`

Hands off to the Claude Code CLI for TDD implementation.

- Reads `./<feature-slug>/plan.md` from the current directory (errors if missing)
- Assembles a prompt with git guardrails + the TDD skill + the plan
- Pipes the prompt directly into the Claude Code CLI (`claude.cmd`)
- No clipboard or GUI — runs in your terminal

---

### `ai new-project "<idea>"`

Decomposes a project idea into structured feature stubs.

- Conducts a scoping interview (one question at a time)
- Proposes 3–8 features with slugs, summaries, and rationale
- Asks for confirmation before writing anything
- Writes `features/<slug>/intake/stub.md` stubs to your notes vault
- Prints suggested `ai feature` commands in dependency order

---

### `ai prep <slug>`

Runs bootstrap commands and starts services defined in `devflow.yaml`. Writes a prep log to `intake/prep.md` and updates `state.json`.

```bash
ai prep "sample-sync"
# → runs env.bootstrap commands
# → starts and health-checks services
# → writes intake/prep.md
```

---

### `ai qa <slug>`

Runs all QA suites defined in `devflow.yaml`. Writes per-suite artifacts and generates `qa/evidence.md`.

```bash
ai qa "sample-sync"
# → runs each qa.suites[].command
# → writes qa/unit.md, qa/smoke.md etc.
# → generates qa/evidence.md
```

---

### `ai deploy <slug>`

Runs deploy steps defined in `devflow.yaml`. Writes a deploy log to `build/deploy.md`.

```bash
ai deploy "sample-sync"
# → runs deploy.steps commands
# → writes build/deploy.md
```

---

### `ai prefect-run <slug>`

Starts the Prefect sandbox, runs the flow, executes assertions, and generates evidence.

```bash
ai prefect-run "sample-sync"
# → starts prefect.sandbox_start
# → runs prefect.run_command
# → runs prefect.assertions[]
# → writes qa/prefect-run.md, qa/assertions.md, qa/evidence.md
```

---

### `ai state clean <slug>`

Removes `state.json` for a feature slug, resetting tracked command history.

```bash
ai state clean "sample-sync"
# → removes <branch-root>/features/sample-sync/state.json
```

---

### `ai run <slug>`

Runs the full feature pipeline automatically, skipping stages already recorded as complete in `state.json`.

Stage order: `prep` → `feature` → `tdd` → `qa` → `prefect` → `deploy`

**Note:** `feature` and `tdd` still require human interaction (Claude GUI/CLI). `ai run` launches them and pauses until you re-run after completion.

```bash
ai run "sample-sync"

# Flags
ai run "sample-sync" --from qa               # start at qa, skip earlier stages
ai run "sample-sync" --to deploy             # stop after deploy
ai run "sample-sync" --skip-tdd              # skip TDD stage entirely
ai run "sample-sync" --skip-qa               # skip QA
ai run "sample-sync" --skip-prefect          # skip Prefect run
ai run "sample-sync" --skip-deploy           # skip deploy

# Combine flags
ai run "sample-sync" --skip-tdd --skip-qa --skip-prefect --skip-deploy
# → runs prep + feature only
```

Writes a stage log to `features/<slug>/ops/run-log.md`.

---

### `ai loop`

Iterates over the feature backlog (`features/index.json`) in priority order and calls `ai run` for each feature.

```bash
ai loop                          # run all features to their configured goal
ai loop --goal qa                # only run features up to the qa stage
ai loop --limit 3                # process at most 3 features per run
ai loop --goal prep --limit 1    # prep one feature from the backlog
ai loop --skip-qa                # forward --skip-qa to every ai run call
ai loop --stop-on-fail           # abort the loop on the first failure
```

After each feature run, `features/index.json` is updated with:
- `last_run` — ISO 8601 timestamp
- `status` — `pass`, `fail`, or `pending`
- `last_stage` — last stage completed
- `evidence` — path to `qa/evidence.md` if present

Prints a summary table at the end.

See [docs/manifest.md](docs/manifest.md) for the `features/index.json` schema.

---

### `ai <skill-name>`

Dispatches a single skill from `skills/` into Claude chat.

Examples:
```bash
ai grill-me
ai write-a-prd
ai prd-to-plan
ai triage-issue
```

---

## Prerequisites

- **Claude CLI** (`claude.cmd`) installed and on PATH via npm
- **AutoHotkey** (Windows) configured — used to paste prompts into the Claude GUI for chat-based workflows (`feature`, `new-project`, single skills)
- **Git Bash or WSL** to run the `ai` script

New here? See the full setup and walkthrough: **[docs/how-to-run-real-feature.md](docs/how-to-run-real-feature.md)**

---

## Notes storage

All markdown artifacts produced by `ai feature` and `ai tdd` land in a dedicated notes directory, completely separate from your source repo.

### Default behavior

Without any configuration, artifacts are written alongside your project (inside `CALLER_DIR`), preserving the original layout.

### Redirecting to Obsidian (or any notes root)

Set `AI_DEV_FLOW_NOTES_ROOT` to your vault or notes folder:

```bash
export AI_DEV_FLOW_NOTES_ROOT="C:\Users\PaulRussell\Obsidian\AI-Dev-Flow"
```

Add that line to your `~/.bashrc` or `~/.zshrc` to make it permanent.

### Folder structure

All commands write into the same vault hierarchy, organized by repo and branch so notes from different projects never collide:

```
<NOTES_ROOT>/
  <repo>/
    <branch>/
      devflow.yaml           ← written by ai init
      devflow.md             ← human-readable companion (Obsidian)
      features/
        index.json           ← backlog for ai loop
        <slug>/
          intake/
            stub.md          ← ai new-project
            prep.md          ← ai prep
          specs/
            prd.md           ← ai feature
            diagram.md       ← ai feature (DIAGRAM phase)
          plans/
            plan.md          ← ai feature
          build/
            tdd-summary.md   ← ai tdd
            deploy.md        ← ai deploy
          qa/
            unit.md          ← ai qa
            smoke.md         ← ai qa
            prefect-run.md   ← ai prefect-run
            assertions.md    ← ai prefect-run
            evidence.md      ← ai qa / ai prefect-run
          ops/
            run-log.md       ← ai run
          state.json         ← maintained by all commands
```

`ai new-project` seeds the `intake/stub.md` for each feature it produces. Running `ai feature "<slug>"` on any of those slugs then fills in the remaining subfolders alongside it.

Example with `AI_DEV_FLOW_NOTES_ROOT=/c/Users/PaulRussell/Documents/ai-dev-flow`:

```
Documents\ai-dev-flow\
  my-app\
    main\
      features\
        auth\
          intake\stub.md
          specs\prd.md
          plans\plan.md
          build\tdd-summary.md
```

---

## Manifest

`devflow.yaml` captures the project tooling config for a repo + branch. Run `ai init` once per project to create it.

```yaml
env:
  venv: .venv
  bootstrap:
    - pip install -r requirements.txt
qa:
  suites:
    - name: Unit
      command: pytest tests/unit
      artifact: features/%slug%/qa/unit.md
prefect:
  sandbox_start: docker compose -f scripts/prefect-sandbox.yml up -d
  run_command: python flows/sync_flow.py
  assertions:
    - name: rows_emitted
      command: python scripts/assert_rows.py --min 10
      artifact: features/%slug%/qa/assertions.md
```

The `%slug%` placeholder in artifact paths is replaced at runtime with the feature slug. Full schema: [docs/manifest.md](docs/manifest.md).

---

## How it works

Chat-based phases (GRILL → PRD → DIAGRAM → PLAN) run in the Claude GUI where you have a conversation. The `ai` script assembles the right skill prompts, copies them to the clipboard, opens Claude, and pastes automatically via AutoHotkey.

The TDD phase runs in the Claude Code CLI (`ai tdd`) so shell commands and file edits execute in your terminal with full tool access.

See `docs/system.md` for the full architecture.

---

## Smoke Testing

A sandbox project and helper script let you exercise all workflows without touching a real repo.

### Prep the workspace

```bash
bash scripts/devflow-smoke.sh
```

This copies `sandbox/sample-app/` into `/tmp/devflow-smoke` (refreshing it each run) and prints step-by-step test instructions.

### Manual steps (run from `/tmp/devflow-smoke`)

```bash
# 1. Full feature lifecycle
ai feature "sample sync"
# → writes ./sample-sync/PRD.md and ./sample-sync/plan.md after each phase

# 2. TDD handoff (requires plan.md from step 1)
ai tdd "sample-sync"
# → writes prompt to /tmp/devflow-tdd-sample-sync.md
# → copies @/tmp/devflow-tdd-sample-sync.md to clipboard
# → opens a new Claude Code window via Start-Process
# → AutoHotkey pastes the @file message automatically (~6 s delay)
# → fallback path printed in terminal if AHK misses

# 3. New-project decomposition
ai new-project "Sample AI app"
# → writes features/<slug>/intake/stub.md stubs to notes vault after confirmation

# 4. Error path — tdd without a plan
ai tdd "no-such-feature"
# → prints: ❌ No plan found at ./no-such-feature/plan.md
```

> **Reminder:** `ai tdd` requires `./<slug>/plan.md` to exist in the current directory. Run `ai feature` first and complete the PLAN phase to generate it.
>
> After TDD completes, the terminal shows a short summary line and the full QA record is saved to `./<slug>/tdd-summary.md` (timestamp, phases, test results, files touched, commands run, design notes).

---

## Extending the system

Add a new skill:
```
skills/
  your-skill/
    SKILL.md
```

Then call it with:
```bash
ai your-skill
```

See `skills/write-a-skill/SKILL.md` for the skill authoring guide.
