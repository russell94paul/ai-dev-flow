# How to Run ai-dev-flow Against a Real Project

This guide walks you from a fresh setup to running a full feature lifecycle against your own repository — GRILL → PRD → PLAN in Claude chat, then TDD in Claude Code.

**Audience:** Windows user with a repo and Claude CLI access.
**Time to first run:** ~15 minutes including setup.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Verify your environment](#2-verify-your-environment)
3. [Feature workflow: GRILL, PRD, PLAN](#3-feature-workflow-grill-prd-plan)
4. [TDD handoff](#4-tdd-handoff)
5. [Project workflow: decompose a new idea](#5-project-workflow-decompose-a-new-idea)
6. [Artifact map](#6-artifact-map)
7. [Troubleshooting](#7-troubleshooting)
8. [Next steps after a run](#8-next-steps-after-a-run)

---

## 1. Prerequisites

### 1.1 Windows + Git Bash

All `ai` commands run in Git Bash (ships with [Git for Windows](https://gitforwindows.org)). PowerShell and cmd.exe are used internally by the script but you never type in them.

Confirm:

```bash
bash --version   # should print "GNU bash, version ..."
```

### 1.2 Claude CLI

Install via npm (requires Node.js ≥ 18):

```bash
npm install -g @anthropic-ai/claude-code
```

Log in:

```bash
claude login
```

Confirm:

```bash
claude --version
```

The script expects `claude.cmd` at `C:\Users\<you>\AppData\Roaming\npm\claude.cmd`. If your npm global prefix is different, update the `CLAUDE_CMD` variable at the top of `~/ai-dev-flow/ai`.

### 1.3 AutoHotkey

AutoHotkey v1 is used to paste prompts into the Claude window automatically.

Download from [autohotkey.com](https://www.autohotkey.com) and install. Confirm `AutoHotkey.exe` is on your PATH or that `.ahk` files open with it by default.

The script (`claude_paste.ahk`) waits for a window titled **"Claude Code"**, pastes from the clipboard, confirms the paste-confirmation modal, and submits. If you rename or move Claude, the AHK script will hang — see [Troubleshooting](#7-troubleshooting).

### 1.4 Repo location

Clone ai-dev-flow to your home directory:

```bash
git clone <repo-url> ~/ai-dev-flow
```

The `SKILL_DIR` variable in the `ai` script is hardcoded to `$HOME/ai-dev-flow/skills`. If you clone elsewhere, update the top of `ai`.

### 1.5 PATH setup (recommended)

Make `ai` callable from anywhere:

```bash
# Add to ~/.bashrc or ~/.bash_profile
export PATH="$HOME/ai-dev-flow:$PATH"
```

Reload:

```bash
source ~/.bashrc
```

Confirm:

```bash
which ai   # should print /c/Users/<you>/ai-dev-flow/ai
```

---

## 2. Verify your environment

Run the smoke test from the ai-dev-flow root before touching a real repo. It copies `sandbox/sample-app/` to `/tmp/devflow-smoke` and prints the exact commands to validate each workflow.

```bash
cd ~/ai-dev-flow
bash scripts/devflow-smoke.sh
```

Expected output: a clean workspace setup message followed by the instruction block. No errors.

Then follow the printed steps from `/tmp/devflow-smoke` to confirm:

- `ai feature "sample sync"` — Claude chat opens and pastes the prompt automatically.
- `ai tdd "sample-sync"` — a new Claude Code window opens after the feature phase produces `sample-sync/plan.md`.
- `ai new-project "Sample AI app"` — Claude chat opens with the new-project skill.

If any step hangs or errors, resolve it before running against a real repo (see [Troubleshooting](#7-troubleshooting)).

---

## 3. Feature workflow: GRILL, PRD, PLAN

### 3.1 Navigate to your repo

```bash
cd /path/to/your-project
```

All artifact files (`PRD.md`, `plan.md`) will be written relative to this directory. Claude Code writes them here — not inside `~/ai-dev-flow`.

### 3.2 Run the feature command

```bash
ai feature "describe your feature here"
```

What happens immediately:
- The `ai` script derives a slug from your description (e.g. `"add user notifications"` → `add-user-notifications`).
- Assembles a prompt combining the grill-me, write-a-prd, and prd-to-plan skills.
- Copies the prompt to your clipboard.
- Opens a new Claude window via `Start-Process`.
- After ~6 seconds, AutoHotkey pastes the prompt and submits it.

You should see Claude's first grill question within a few seconds of the window opening.

At the end of the terminal output you'll see:

```
When PLAN phase is confirmed, run:
  ai tdd "add-user-notifications"
```

Keep this visible — you'll need the exact slug for the next step.

### 3.3 Phase 1 — GRILL

Claude asks one question at a time to clarify scope. For each question:

- Answer as specifically as you can.
- If a question can be resolved by pointing Claude at existing code, paste the file path or a snippet.
- When Claude has enough context, it prints: **GRILL COMPLETE**

Typical questions include edge cases, error states, affected components, and success criteria. Budget 5–15 minutes depending on feature complexity.

### 3.4 Phase 2 — PRD

Claude produces a structured PRD covering problem statement, solution, user stories, implementation decisions, testing decisions, and out-of-scope items.

Review it carefully. Ask Claude to revise any section before approving. When you're satisfied, confirm (type "yes", "looks good", or similar).

Claude then writes:

```
your-project/add-user-notifications/PRD.md
```

You'll see a confirmation message with the exact path.

### 3.5 Phase 3 — PLAN

Claude breaks the PRD into phased vertical slices, each with a title, user stories covered, what to build, and acceptance criteria checklists.

Check:
- Are the phases thin enough to be demoable individually?
- Does each acceptance criterion map to a concrete test?
- Are there any missing edge cases from the GRILL?

Request changes freely — the plan drives TDD, so getting it right here saves time later. When satisfied, confirm.

Claude writes:

```
your-project/add-user-notifications/plan.md
```

Then prints:

```
PLAN COMPLETE. To begin TDD run: ai tdd "add-user-notifications"
```

The chat session is complete. Move to your terminal.

---

## 4. TDD handoff

### 4.1 Run the TDD command

From the same repo directory (where `add-user-notifications/plan.md` exists):

```bash
ai tdd "add-user-notifications"
```

What happens:
- The script reads `add-user-notifications/plan.md`.
- Assembles a prompt: git guardrails + TDD skill + full plan content.
- Writes the prompt to `/tmp/devflow-tdd-add-user-notifications.md`.
- Copies `@/tmp/devflow-tdd-add-user-notifications.md` to the clipboard.
- Opens a **new** Claude Code window via `Start-Process`.
- After ~6 seconds, AutoHotkey pastes the `@file` reference and submits.

Your terminal prints:

```
📝 Prompt: /tmp/devflow-tdd-add-user-notifications.md
🚀 Opening Claude Code...
⌨️ Sending prompt...
✅ Done. Claude Code should now be loading the TDD context.

   Fallback: if AHK missed, paste manually in Claude Code:
   @/tmp/devflow-tdd-add-user-notifications.md
```

### 4.2 What Claude Code does

When the `@file` message is received, Claude Code loads the full context and begins the TDD workflow:

1. **Planning** — confirms which behaviors to test and the public interface shape.
2. **Tracer bullet** — writes one failing test, then minimal code to pass it.
3. **Incremental loop** — repeats for each acceptance criterion in your plan.
4. **Refactor** — extracts duplication, deepens modules, runs tests after each change.

Console output during TDD is intentionally quiet: one `RED`/`GREEN` status line per test cycle.

### 4.3 Git guardrails

The TDD prompt includes hard rules: Claude must state the exact git command and wait for you to type "yes" before running `git commit`, `git push`, `git reset --hard`, `git clean`, `git checkout --`, or `git branch -D`. If you see Claude about to commit without asking, type "stop" immediately.

### 4.4 Completion and `tdd-summary.md`

When all plan phases are complete, Claude prints:

```
TDD COMPLETE — summary saved to ./add-user-notifications/tdd-summary.md (tests: 7 GREEN)
```

Then writes `add-user-notifications/tdd-summary.md` with:

| Section | Contents |
|---------|----------|
| Timestamp | ISO 8601 run time |
| Phases completed | Each plan phase and its GREEN/RED status |
| Test results | Per-test name and status |
| Files touched | Relative paths, created or modified |
| Commands run | Exact test-runner invocations |
| Design notes | Decisions and tradeoffs made during implementation |

### 4.5 Troubleshooting TDD-specific issues

**"No plan found" error:**

```
❌ No plan found at ./add-user-notifications/plan.md
```

You're either in the wrong directory or the feature phase didn't complete. Confirm you're in the repo root where the feature folder was created, and that `plan.md` exists:

```bash
ls add-user-notifications/
# should show: PRD.md  plan.md
```

**AHK missed the paste:**

The terminal prints the fallback path. In the Claude Code window, type it manually:

```
@/tmp/devflow-tdd-add-user-notifications.md
```

**Claude Code window never opened:**

Check that `CLAUDE_CMD` in `~/ai-dev-flow/ai` points to your actual `claude.cmd`. Find it with:

```bash
where claude    # in cmd.exe, or:
which claude    # in Git Bash
```

---

## 5. Project workflow: decompose a new idea

Use `ai new-project` when you're starting from a blank canvas and need to break a broad idea into features before writing any code.

### 5.1 Navigate to your project root (or a new directory)

```bash
mkdir ~/my-new-project && cd ~/my-new-project
```

### 5.2 Run the command

```bash
ai new-project "describe your project idea"
```

Claude opens in chat mode and runs a five-phase workflow:

| Phase | What happens |
|-------|--------------|
| Scoping interview | One question at a time: users, success criteria, constraints, non-goals |
| Feature decomposition | Proposes 3–8 features with slugs, summaries, and rationale |
| Confirmation gate | Lists the full feature set and asks for your approval — **no files written yet** |
| Stub writes | Creates `features/<feature-slug>.md` for each approved feature |
| Handoff | Prints suggested `ai feature` commands in dependency order |

### 5.3 Review and edit stubs

Each stub at `features/<slug>.md` contains:
- **Summary** — one sentence description
- **Why** — rationale relative to the project goal
- **Open questions** — placeholder, to be resolved during the grill phase

Edit the stubs if anything was mis-described during the session. The slugs are used as-is when you run `ai feature "<slug>"`.

### 5.4 Kick off features

Work through them in the suggested order (foundational first):

```bash
ai feature "knowledge-schema"
ai feature "ingestion-pipeline"
# etc.
```

Each produces its own `<slug>/PRD.md` and `<slug>/plan.md` in your project root.

---

## 6. Artifact map

All artifacts are written relative to the directory where you run `ai`. Nothing is written inside `~/ai-dev-flow`.

| Artifact | Path | Written by | When |
|----------|------|------------|------|
| PRD | `./<slug>/PRD.md` | `ai feature` | After PRD phase confirmed |
| Implementation plan | `./<slug>/plan.md` | `ai feature` | After PLAN phase confirmed |
| TDD summary | `./<slug>/tdd-summary.md` | `ai tdd` | On TDD completion |
| Feature stub | `./features/<slug>.md` | `ai new-project` | After feature list confirmed |
| TDD prompt cache | `/tmp/devflow-tdd-<slug>.md` | `ai tdd` | At invocation (temp, rewritten each run) |

### Recommended commit strategy

Commit `PRD.md` and `plan.md` alongside your feature branch before starting TDD. Commit `tdd-summary.md` when the feature is done. This makes the decision trail traceable in git history.

```bash
git add add-user-notifications/PRD.md add-user-notifications/plan.md
git commit -m "docs: add PRD and plan for user notifications"

# ... after TDD ...

git add add-user-notifications/tdd-summary.md
git commit -m "docs: TDD summary for user notifications (7 GREEN)"
```

---

## 7. Troubleshooting

### Claude window doesn't open

- Confirm `CLAUDE_CMD` at the top of `~/ai-dev-flow/ai` points to a real file: `ls "$CLAUDE_CMD"` (in bash, use forward slashes or quote the path).
- Run `where claude` in a cmd.exe window to find the correct path.

### AutoHotkey hangs (nothing gets pasted)

AHK waits for a window titled **"Claude Code"**. If the window title is different (e.g., the GUI was renamed in an update), AHK will wait indefinitely.

To unblock: kill the AHK process in Task Manager, then paste manually from the clipboard (Ctrl+V in the Claude window and press Enter).

To fix permanently: update `WinWait, Claude Code` in `claude_paste.ahk` to match the actual window title. Use the AHK Window Spy tool (`AutoHotkey\WindowSpy.ahk`) to find the exact title.

### Paste confirmation modal appears but AHK misses the Enter

The script sends `{Enter}` after a 2500 ms sleep to dismiss the "Paste anyway?" modal. On slow machines this can be too fast. Increase the sleep value in `claude_paste.ahk`:

```ahk
Sleep, 2500   ; ← try 4000 or 5000 if the modal is being missed
Send {Enter}
```

### GRILL phase finishes too quickly (feels like Claude is skipping questions)

This usually means the feature description was very specific. That's fine — Claude may need fewer questions. If you feel important scope is missing, push back explicitly: "You haven't asked about error handling — grill me on that before we proceed."

### `ai feature` writes artifacts to the wrong directory

The artifacts go into whatever directory you `cd`'d into before running `ai feature`. Confirm with:

```bash
pwd   # should be your repo root, not ~/ai-dev-flow
```

If you accidentally wrote to the wrong place, move the files and re-run from the correct directory. The command is safe to re-run — PRD.md and plan.md are overwritten each time.

### `tdd-summary.md` is missing after TDD completes

Claude Code writes the file using its file-write tools. If the session ended abruptly (e.g., network drop, manual close), the file may not have been written. The TDD prompt instructs Claude to write the file **before** printing the completion line. If you see the completion line but no file, check whether the write was blocked by a permissions issue:

```bash
ls -la add-user-notifications/
```

If the directory is read-only, fix permissions and ask Claude to re-run the final summary step: "Please write tdd-summary.md now."

### Smoke test fails

Re-run with verbose output to isolate the step:

```bash
bash -x scripts/devflow-smoke.sh 2>&1 | head -50
```

Common causes: `SKILL_DIR` path wrong (repo not at `~/ai-dev-flow`), `claude.cmd` not found, AutoHotkey not installed.

---

## 8. Next steps after a run

### Review artifacts before merging

Open `<slug>/tdd-summary.md` and check:
- All plan phases show ✅ GREEN.
- No tests are RED or skipped.
- Design notes capture any scope changes (if scope changed, consider updating `plan.md` to match).

### Commit everything

See the [recommended commit strategy](#recommended-commit-strategy) in the artifact map section.

### Update your tickets / issue tracker

Copy the "Files touched" section from `tdd-summary.md` into your PR description. Copy acceptance criteria check-marks from `plan.md` to close related issues.

### Re-run TDD if the plan changes

If requirements shift after TDD has started, update `<slug>/plan.md` directly, then re-run:

```bash
ai tdd "add-user-notifications"
```

The TDD prompt is rebuilt from the current `plan.md` each time. The previous `tdd-summary.md` is overwritten.

### Kick off the next feature

Return to your project root and pick the next feature from `features/`:

```bash
cat features/ingestion-pipeline.md   # review the stub
ai feature "ingestion-pipeline"
```

---

*For the full architecture and workflow diagrams, see [`docs/system.md`](system.md). For the quick-reference command list, see the root [`README.md`](../README.md).*
