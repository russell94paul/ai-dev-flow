"""
devflow CLI — Typer entry point.

Usage:
  devflow feature "add user authentication"
  devflow tdd "add-user-authentication"
  devflow skill grill-me
  devflow --version
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Annotated, Optional

import typer
from rich.console import Console

from devflow import __version__
from devflow.config import Config

app = typer.Typer(
    name="devflow",
    help="AI-assisted developer workflow. Cross-platform, no AHK required.",
    add_completion=False,
)
console = Console()


def _in_vscode() -> bool:
    """Return True when running inside VS Code's integrated terminal."""
    if os.environ.get("DEVFLOW_NO_RELAUNCH"):
        return False  # already relaunched — don't loop
    return (
        os.environ.get("TERM_PROGRAM") == "vscode"
        or "VSCODE_INJECTION" in os.environ
        or "VSCODE_PID" in os.environ
    )


_WT_EXE = r"C:\Users\PaulRussell\AppData\Local\Microsoft\WindowsApps\wt.exe"
_GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"


def _to_bash_path(win_path: str) -> str:
    """Convert a Windows path to Git Bash Unix-style path. C:\\foo\\bar → /c/foo/bar"""
    p = win_path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        p = "/" + p[0].lower() + p[2:]
    return p


def _relaunch_in_wt() -> None:
    """
    Re-launch the current devflow command in Windows Terminal using Git Bash.
    Called automatically when a TUI command is run inside VS Code.
    """
    if not os.path.exists(_WT_EXE) or not os.path.exists(_GIT_BASH):
        return  # fall through and run in VS Code terminal

    # Use full path to devflow.exe so WT doesn't need devflow in its PATH
    devflow_exe = os.path.join(os.path.dirname(sys.executable), "Scripts", "devflow.exe")
    if not os.path.exists(devflow_exe):
        devflow_exe = sys.argv[0]

    bash_devflow = _to_bash_path(devflow_exe)

    # Single-quote each argument for bash (handles spaces, avoids Windows double-quote mangling)
    def _bq(s: str) -> str:
        return "'" + s.replace("'", "'\\''") + "'"

    bash_args = " ".join(_bq(a) for a in sys.argv[1:])

    # Write a temp script — avoids all -c quoting issues entirely.
    # Forward key env vars so the WT window has the same context as VS Code.
    import tempfile
    env_lines = ["export PYTHONUTF8=1", "export DEVFLOW_NO_RELAUNCH=1"]
    for var in ("ANTHROPIC_API_KEY", "DEVFLOW_NOTES_ROOT", "DEVFLOW_SKILL_DIR", "DEVFLOW_MODEL"):
        val = os.environ.get(var)
        if val:
            env_lines.append(f"export {var}={_bq(val)}")

    script = "\n".join([
        "#!/bin/bash",
        *env_lines,
        f"{_bq(bash_devflow)} {bash_args}",
        "echo",
        "read -p 'Press Enter to close...'",
    ]) + "\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, newline="\n"
    ) as f:
        f.write(script)
        script_path = _to_bash_path(f.name)

    try:
        subprocess.Popen([_WT_EXE, _GIT_BASH, script_path])
        console.print(f"[cyan]Opened in Windows Terminal[/cyan]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[yellow]Could not open Windows Terminal ({e}) — running here instead[/yellow]")


def _load_config() -> Config:
    config = Config()
    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]✗[/red] {err}")
        raise typer.Exit(1)
    return config


# ─────────────────────────────────────────────────────────────────────────────
# devflow feature
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def feature(
    idea: Annotated[str, typer.Argument(help="One-line description of the feature")],
    slug: Annotated[
        Optional[str],
        typer.Option("--slug", "-s", help="Override auto-generated slug"),
    ] = None,
    reset: Annotated[
        bool,
        typer.Option("--reset", help="Discard existing session and start fresh"),
    ] = False,
):
    """
    Run the GRILL → PRD → PLAN conversation for a new feature.
    Replaces: ai feature "<idea>"  +  AutoHotKey clipboard paste.
    """
    if _in_vscode():
        _relaunch_in_wt()

    from devflow.modes.feature import run_feature
    from devflow.tui.app import DevflowApp

    config = _load_config()
    feature_slug = slug or _make_slug(idea)

    if reset:
        from devflow.session import Session
        from devflow.modes.feature import _detect_repo_name, _detect_branch
        notes_dir = config.feature_notes_dir(_detect_repo_name(), _detect_branch(), feature_slug)
        Session(slug=feature_slug, notes_dir=notes_dir).reset()
        console.print(f"[yellow]Session reset for[/yellow] {feature_slug}")

    tui = DevflowApp(slug=feature_slug, stages=["prep", "feature", "tdd", "qa", "deploy"])
    tui.run_mode(run_feature, slug=feature_slug, idea=idea, config=config)
    tui.run()


# ─────────────────────────────────────────────────────────────────────────────
# devflow tdd  (Phase 3 — placeholder until implemented)
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def tdd(
    slug: Annotated[str, typer.Argument(help="Feature slug to implement")],
):
    """
    Run TDD implementation via claude -p headless, streaming output to TUI.
    Replaces: ai tdd "<slug>"  +  AutoHotKey clipboard paste.
    """
    console.print(
        f"[yellow]devflow tdd[/yellow] — Phase 3 (coming soon)\n"
        f"Until then: [dim]ai tdd \"{slug}\"[/dim]"
    )
    raise typer.Exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# devflow skill
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def skill(
    name: Annotated[str, typer.Argument(help="Skill name (e.g. grill-me, write-a-prd)")],
    context: Annotated[
        Optional[str],
        typer.Argument(help="Optional context to pass to the skill"),
    ] = None,
):
    """
    Run a single skill as a one-shot conversation in the TUI.
    Replaces: ai <skill-name>  +  AutoHotKey clipboard paste.
    """
    from devflow.modes.feature import load_skill, DevflowClient
    from devflow.tui.app import DevflowApp
    from devflow.session import Session
    import asyncio

    config = _load_config()

    try:
        skill_text = load_skill(name, config.skill_dir)
    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] {e}")
        raise typer.Exit(1)

    async def run_skill(app: DevflowApp) -> None:
        from devflow.tui.widgets import ClaudeMessage
        client = DevflowClient(config)
        messages = [{"role": "user", "content": context or "Begin."}]
        app.output.write_line(f"[bold #06b6d4]devflow skill[/]  [dim #475569]{name}[/]")
        msg = ClaudeMessage("")
        await app.output.mount_message(msg)
        app.thinking.show()
        accumulated: list[str] = []
        async for token in client.stream(messages, system=skill_text):
            accumulated.append(token)
            msg.stream_update("".join(accumulated))
            app.output.scroll_end()
        app.thinking.hide()
        msg.stream_update("".join(accumulated))
        app.input_field.hide()
        app.exit()

    tui = DevflowApp(slug=name, stages=[])
    tui.run_mode(run_skill)
    tui.run()


# ─────────────────────────────────────────────────────────────────────────────
# devflow run  (Phase 4 — placeholder)
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def run(
    slug: Annotated[str, typer.Argument(help="Feature slug to run through the pipeline")],
):
    """
    Run the full pipeline: prep → feature → tdd → qa → deploy.
    Replaces: ai run "<slug>"
    """
    console.print(
        f"[yellow]devflow run[/yellow] — Phase 4 (coming soon)\n"
        f"Until then: [dim]ai run \"{slug}\"[/dim]"
    )
    raise typer.Exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# devflow --version
# ─────────────────────────────────────────────────────────────────────────────

def _version_callback(value: bool) -> None:
    if value:
        console.print(f"devflow {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
):
    """devflow — AI-assisted developer workflow CLI."""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_slug(text: str) -> str:
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]
