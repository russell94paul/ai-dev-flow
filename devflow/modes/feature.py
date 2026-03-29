"""
Feature mode — replaces the bash `ai feature` + AHK clipboard workflow.

Runs a multi-turn conversation with Claude via the Anthropic API directly.
The conversation follows the same GRILL → PRD → DIAGRAM → PLAN structure
as the original bash script, but entirely inside the Textual TUI.

Completion signal: when Claude prints "PLAN COMPLETE" the conversation ends
and artifacts are written to the notes vault.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from devflow.api import DevflowClient
from devflow.session import Session
from devflow.tui.widgets import ClaudeMessage, UserMessage

if TYPE_CHECKING:
    from devflow.config import Config
    from devflow.tui.app import DevflowApp

PLAN_COMPLETE_SIGNAL = "PLAN COMPLETE"


# ─────────────────────────────────────────────────────────────────────────────
# Skill loading
# ─────────────────────────────────────────────────────────────────────────────

def load_skill(skill_name: str, skill_dir: Path) -> str:
    """Read SKILL.md for the given skill, stripping YAML frontmatter."""
    path = skill_dir / skill_name / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"Skill not found: {path}")
    text = path.read_text(encoding="utf-8")
    # Strip YAML frontmatter (--- ... ---)
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL)
    return text.strip()


def build_system_prompt(skill_dir: Path, slug: str, idea: str) -> str:
    """
    Compose the system prompt from the three planning skills.
    Mirrors the bash script's feature mode prompt assembly.
    """
    skills = []
    for name in ["grill-me", "write-a-prd", "prd-to-plan"]:
        try:
            skills.append(f"## {name.upper()}\n\n{load_skill(name, skill_dir)}")
        except FileNotFoundError:
            pass  # skill optional — warn but continue

    header = f"""You are a senior product engineer running a structured feature planning session.
This is a PURE CONVERSATION — you have no tools, no file system access, and no ability to
read codebases. Do not attempt to use tools or output XML tool-use syntax. Ask questions directly.

Feature idea: {idea}
Feature slug: {slug}

Follow these phases in order: GRILL -> PRD -> DIAGRAM -> PLAN.
When all phases are complete, print exactly:
  {PLAN_COMPLETE_SIGNAL}. To begin TDD run: devflow tdd "{slug}"

"""
    return header + "\n\n---\n\n".join(skills)


# ─────────────────────────────────────────────────────────────────────────────
# Artifact writing
# ─────────────────────────────────────────────────────────────────────────────

def _extract_section(text: str, keyword: str) -> str:
    """
    Extract content under a heading that starts with `keyword`.
    Handles titles like '# Plan: User Auth' and '## Implementation Plan'.
    """
    kw = re.escape(keyword)
    # Match heading + everything until the next same-or-higher heading or end of string
    pattern = r"(#{1,3} " + kw + r"[^\n]*\n.*?)(?=\n#{1,3} |\Z)"
    m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def write_artifacts(session: Session, notes_dir: Path, slug: str) -> None:
    """
    Write conversation artifacts to the notes vault:
      build/conversation.md  — full chat transcript (user + assistant)
      specs/prd.md           — PRD section extracted from assistant messages
      plans/plan.md          — implementation plan extracted from assistant messages
    """
    # ── Full conversation transcript ──────────────────────────────────────── #
    turns = []
    for m in session.messages:
        label = "You" if m["role"] == "user" else "Claude"
        turns.append(f"## {label}\n\n{m['content'].strip()}")
    transcript = "\n\n---\n\n".join(turns)

    # ── All assistant text joined (source for section extraction) ─────────── #
    assistant_text = "\n\n".join(
        m["content"] for m in session.messages
        if m["role"] == "assistant" and isinstance(m["content"], str)
    )
    # Strip the PLAN COMPLETE signal line from the extracted text
    assistant_text = re.sub(r"\n*PLAN COMPLETE[^\n]*", "", assistant_text)

    build_dir = notes_dir / "build"
    specs_dir = notes_dir / "specs"
    plans_dir = notes_dir / "plans"
    build_dir.mkdir(parents=True, exist_ok=True)
    specs_dir.mkdir(parents=True, exist_ok=True)
    plans_dir.mkdir(parents=True, exist_ok=True)

    # Full transcript
    (build_dir / "conversation.md").write_text(transcript, encoding="utf-8")

    # PRD — prefer extracted section, fall back to full assistant text
    prd_content = (
        _extract_section(assistant_text, "PRD")
        or _extract_section(assistant_text, "Product Requirements")
        or assistant_text
    )
    (specs_dir / "prd.md").write_text(prd_content, encoding="utf-8")

    # Plan — try several heading variants Claude might use
    plan_content = (
        _extract_section(assistant_text, "Plan")
        or _extract_section(assistant_text, "Implementation Plan")
        or _extract_section(assistant_text, "Development Plan")
        or _extract_section(assistant_text, "Technical Plan")
    )
    if plan_content:
        (plans_dir / "plan.md").write_text(plan_content, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main mode coroutine
# ─────────────────────────────────────────────────────────────────────────────

def _detect_phase_transition(text: str) -> str | None:
    """Detect when Claude transitions between GRILL → PRD → PLAN phases."""
    t = text.lower()
    if "# prd" in text or "moving to prd" in t or "moving to the prd" in t or "let me move to the prd" in t:
        return "prd_start"
    if "# plan" in text or "moving to the plan" in t or "writing the plan" in t or "writing a plan" in t:
        return "plan_start"
    return None


async def run_feature(app: "DevflowApp", slug: str, idea: str, config: "Config") -> None:
    """
    Multi-turn feature planning session.
    Runs inside the Textual event loop via app.run_mode().
    """
    repo_name = _detect_repo_name()
    branch = _detect_branch()

    notes_dir = config.feature_notes_dir(
        repo_name=repo_name,
        branch=branch,
        slug=slug,
    )

    # Populate context panel, status bar, and snapshot path
    app.update_context(repo_name, branch, slug)
    app.status_bar.set_model(config.model)
    app._notes_dir = notes_dir

    session = Session.load_or_create(slug, notes_dir)
    client = DevflowClient(config)
    system_prompt = build_system_prompt(config.skill_dir, slug, idea)
    turn = 0  # counts Claude responses (= question number)

    # ── Already complete — restore finished state ─────────────────────────── #
    if session.complete:
        app.stage_bar.set_done("feature")
        app.context_panel.set_phase("grill", "done")
        app.context_panel.set_phase("prd", "done")
        app.context_panel.set_phase("plan", "done")
        app.output.write_line(
            f"[bold #06b6d4]devflow feature[/]  [dim #475569]{slug}[/]"
        )
        app.output.write_line(
            f"[bold #10b981]Plan already complete[/]  "
            f"[dim #475569]artifacts → {notes_dir}[/]"
        )
        app.output.write_line(
            f'[dim #475569]Run with[/]  [bold #06b6d4]--reset[/]  [dim #475569]to start over.[/]'
        )
        app.emit("Session already complete")
        app.input_field.hide()
        return

    app.stage_bar.set_running("feature")
    app.context_panel.set_phase("grill", "running")
    app.output.write_line(
        f"[bold #06b6d4]devflow feature[/]  [dim #475569]{slug}[/]"
    )
    app.emit(f"Session started: {slug}")

    # Seed first user message if this is a fresh session
    if not session.messages:
        session.add_user(f"I want to build: {idea}")

    while not session.complete:
        # ── Stream Claude's response into a live message widget ────────── #
        msg = ClaudeMessage("")
        await app.output.mount_message(msg)
        app.thinking.show()

        accumulated: list[str] = []
        async for token in client.stream(session.messages, system=system_prompt):
            accumulated.append(token)
            msg.stream_update("".join(accumulated))
            app.output.scroll_end()

        app.thinking.hide()
        full_response = "".join(accumulated)
        msg.stream_update(full_response)
        session.add_assistant(full_response)
        session.save()

        # ── Update composer status with current question number ────────── #
        turn += 1
        app.composer_status.set_question(turn)

        # ── Detect phase transitions ──────────────────────────────────── #
        transition = _detect_phase_transition(full_response)
        if transition == "prd_start":
            app.context_panel.set_phase("grill", "done")
            app.context_panel.set_phase("prd", "running")
            app.emit("GRILL complete → PRD")
        elif transition == "plan_start":
            app.context_panel.set_phase("prd", "done")
            app.context_panel.set_phase("plan", "running")
            app.emit("PRD complete → Plan")

        # ── Check for completion ──────────────────────────────────────── #
        if PLAN_COMPLETE_SIGNAL in full_response:
            write_artifacts(session, notes_dir, slug)
            session.complete = True
            session.save()
            app.stage_bar.set_done("feature")
            app.context_panel.set_phase("grill", "done")
            app.context_panel.set_phase("prd", "done")
            app.context_panel.set_phase("plan", "done")
            app.emit("Plan complete — artifacts written")
            app.output.write_line(
                f"[bold #10b981]Plan complete[/]  "
                f"[dim #475569]artifacts → {notes_dir}[/]"
            )
            app.output.write_line(
                f'[dim #475569]Next:[/]  [bold #06b6d4]devflow tdd "{slug}"[/]'
            )
            app.output.write_line(
                f"[dim #475569]Press Ctrl+Q to close.[/]"
            )
            app.input_field.hide()
            return

        # ── Wait for user reply ───────────────────────────────────────── #
        user_text = await app.wait_for_input()
        await app.output.mount_message(UserMessage(user_text))
        app.working_memory.add_answer(user_text, q_tag=f"Q{turn}")
        session.add_user(user_text)
        session.save()


# ─────────────────────────────────────────────────────────────────────────────
# Git helpers
# ─────────────────────────────────────────────────────────────────────────────

def _detect_repo_name() -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        return Path(result.stdout.strip()).name
    except Exception:
        return "unknown-repo"


def _detect_branch() -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() or "main"
    except Exception:
        return "main"
