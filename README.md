# ai-dev-flow

A structured AI-driven development workflow. Transforms ad-hoc prompting into a repeatable, artifact-producing process.

---

## Commands

### `ai feature "<idea>"`

Runs the GRILL → PRD → PLAN lifecycle in Claude chat.

- Grills you on requirements one question at a time
- Produces a structured PRD
- Breaks the PRD into a phased implementation plan with acceptance criteria
- Writes artifacts to `./<feature-slug>/PRD.md` and `./<feature-slug>/plan.md` in your current directory

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
- Writes `features/<feature-slug>.md` stubs to your current directory
- Prints suggested `ai feature` commands in dependency order

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

## Artifact layout

```
your-project/
  <feature-slug>/
    PRD.md           ← written by `ai feature` (PRD phase)
    plan.md          ← written by `ai feature` (PLAN phase)
    tdd-summary.md   ← written by `ai tdd` on completion
  features/
    <slug>.md        ← written by `ai new-project`
```

---

## How it works

Chat-based phases (GRILL/PRD/PLAN) run in the Claude GUI where you have a conversation. The `ai` script assembles the right skill prompts, copies them to the clipboard, opens Claude, and pastes automatically via AutoHotkey.

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
# → writes features/<slug>.md stubs after confirmation

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

<<<<<<< HEAD
Then call it with:
```bash
ai your-skill
```

See `skills/write-a-skill/SKILL.md` for the skill authoring guide.
=======
Then integrate them into workflows via the CLI.

---

## ⚠️ Notes

* This system is **human-in-the-loop**
* You control all decisions
* Outputs are transparent and inspectable

---

## 💡 Philosophy

> Structure beats prompting.

ai-dev-flow is built on:

* clear thinking
* iterative refinement
* traceable decisions
* developer control

---

## 🤝 Contributing

This project is evolving quickly.

Contributions, ideas, and improvements are welcome.

---

## ⭐ Final Thought

This is not just a tool.

It’s the beginning of a:

> 🧠 **self-improving AI engineering system**
>>>>>>> d3b9a6fe75992239fdc80005b581ebe9e15ed0e1
