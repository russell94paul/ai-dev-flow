# Backlog

Items deferred from v1. Revisit once the core workflows are stable.

---

## `ai tdd` — Seamless Claude Code Launch

**Current workaround (v1):** `ai tdd` writes the prompt to `/tmp/devflow-tdd-<slug>.md`, copies `@<file>` to the clipboard, opens Claude Code, and the user pastes as their first message.

**Root cause:** Claude Code uses Ink, which requires stdin to be an interactive TTY. Piping (`echo "$prompt" | claude`) destroys raw mode and crashes with `ERR_TTY_INIT_FAILED`.

**Ideal end state:** A single command that opens Claude Code with the TDD context pre-loaded and no manual paste step. Options to explore:
- `claude --message "$(cat $file)"` if a `--message` flag is ever added
- A `CLAUDE_INITIAL_MESSAGE` env var or similar mechanism
- A Claude Code API/SDK approach that starts a session programmatically

---

## Centralized Artifact Storage

Currently, `ai feature` writes `PRD.md` and `plan.md` into the caller's repo under a feature-slug folder. This works for single-project use but doesn't scale.

Open questions:

- Should feature artifacts sync to a shared Obsidian vault or a separate git repo?
- How should multiple projects using the same ai-dev-flow install be namespaced (e.g. `~/ai-notes/<project>/<feature>/`)?
- Should `ai` accept an explicit `--output-dir` flag to override the caller-cwd default?
- How should `ai new-project` stubs relate to the per-feature artifacts written by `ai feature`? (Currently they live in separate places: `features/<slug>.md` vs `<slug>/PRD.md`.)

---

## State Tracking / Resume

Currently relies on conversation history. If a session is interrupted mid-GRILL, the user must restart.

Possible approach:

- Write `<feature-slug>/state.json` after each phase completes: `{ "phase": "plan", "completed": ["grill", "prd"] }`
- `ai feature` detects an existing state file and skips completed phases
- Requires Claude to write the state file alongside the artifact at the end of each phase

Deferred because v1 workflows are short enough that restarts are acceptable.

---

## `--output-dir` Flag

A number of workflows would benefit from an explicit output directory:

```bash
ai feature "sync engine" --output-dir ~/notes/my-project
```

Blocked on deciding the artifact storage strategy above.

---

## Windows / Cross-Platform Polish

- The AutoHotkey dependency for clipboard paste limits `ai feature` and `ai new-project` to Windows
- Consider a cross-platform fallback (e.g. `xdotool` on Linux, `osascript` on macOS)
- The `CLAUDE_CMD` path is hardcoded; consider auto-detection via `which claude` or `where claude`
