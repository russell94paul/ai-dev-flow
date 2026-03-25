# AI Dev Flow System

## Overview

ai-dev-flow is a structured AI-driven development workflow system.

It transforms software development from ad-hoc prompting into a repeatable process.

---

## Two-Phase Execution Model

ai-dev-flow splits the development lifecycle into two distinct execution surfaces:

### Phase A: Chat (GRILL / PRD / PLAN)

Runs in the Claude GUI via clipboard + AutoHotkey paste.

- **Why chat:** These phases are conversational — they require back-and-forth clarification, user confirmation between stages, and structured document output (PRD.md, plan.md). The GUI provides a natural interface for this dialogue.
- **Commands:** `ai feature "<idea>"`, `ai new-project "<idea>"`, single skill dispatch (`ai <skill-name>`)
- **Artifacts produced:** `./<feature-slug>/PRD.md`, `./<feature-slug>/plan.md`, `features/<slug>.md`

### Phase B: Claude Code CLI (TDD)

Runs in the terminal via the Claude Code CLI (`claude.cmd`), with the prompt piped directly.

- **Why CLI:** The TDD phase executes real shell commands, writes files, and runs tests. The Claude Code CLI has full tool access (Bash, file read/write, etc.) whereas the GUI does not. This is where implementation actually happens.
- **Command:** `ai tdd "<feature-slug>"`
- **Input:** reads `./<feature-slug>/plan.md` from the caller's directory
- **Git guardrails:** applied automatically — Claude must ask before any git operation
- **Artifacts produced:** `./<feature-slug>/tdd-summary.md` — written on completion with timestamp, phases, test results, files touched, commands run, and design notes. Console output is kept to a single summary line.

The handoff signal from Phase A to Phase B is the printed message:
```
PLAN COMPLETE. To begin TDD run: ai tdd "<feature-slug>"
```

---

## Core Workflows

### new-project

Breaks a project idea into structured features.

1. Scoping interview (one question at a time)
2. Feature decomposition (3–8 features with slugs and rationale)
3. Confirmation gate (no files written until user approves)
4. Writes `features/<feature-slug>.md` stubs
5. Prints suggested `ai feature` commands in dependency order

### feature

Runs GRILL → PRD → PLAN in Claude chat:

1. Grill (clarify requirements)
2. PRD generation → writes `./<slug>/PRD.md`
3. Implementation planning → writes `./<slug>/plan.md`

### tdd

Hands off to Claude Code CLI using the plan from the feature workflow:

1. Reads `./<slug>/plan.md`
2. Applies git guardrails
3. Implements feature using TDD (red → green → refactor, one vertical slice at a time)

---

## Philosophy

- Structured thinking over ad-hoc prompting
- Human-in-the-loop decision making at every phase boundary
- Persistent artifacts (PRD, plan) committed alongside code
- Iterative improvement of workflows

---

## Architecture

- CLI (`ai`) orchestrates workflows and assembles prompts
- Skills (`skills/*/SKILL.md`) define prompt modules
- Claude chat executes conversational phases
- Claude Code CLI executes implementation phases
- Artifact files store outputs in the caller's repo

---

## Future Direction

- Centralized artifact storage / Obsidian vault sync (see `docs/backlog.md`)
- State tracking and resume for interrupted workflows
- Self-improving workflows and prompt evolution
- Multi-agent collaboration
