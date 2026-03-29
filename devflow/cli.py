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

# Ensure UTF-8 output on Windows regardless of console code page.
# Must be done before Rich/Typer import so the console is configured correctly.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

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
    for var in (
        "ANTHROPIC_API_KEY", "DEVFLOW_NOTES_ROOT", "DEVFLOW_SKILL_DIR", "DEVFLOW_MODEL",
        "PAPERCLIP_API_URL", "PAPERCLIP_API_KEY", "PAPERCLIP_AGENT_ID", "PAPERCLIP_COMPANY_ID",
    ):
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
# devflow heartbeat
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def heartbeat(
    once: Annotated[
        bool,
        typer.Option("--once", help="Process one task then exit (default)"),
    ] = True,
):
    """
    Process the Paperclip task inbox: fetch the next assigned issue,
    check it out, and mark it done.

    Fallback for when a triggered Paperclip heartbeat fails to fire.
    Requires PAPERCLIP_API_KEY to be set.
    """
    import asyncio

    async def _run() -> None:
        from devflow.paperclip import client_from_env, PaperclipCheckoutConflict, PaperclipError

        config = Config()
        if not config.paperclip_enabled:
            console.print("[red]✗[/red] PAPERCLIP_API_KEY is not set.")
            raise typer.Exit(1)

        pc = client_from_env()
        async with pc:
            # Health check
            if not await pc.check_health():
                console.print(
                    f"[red]✗[/red] Paperclip server unreachable at [cyan]{config.paperclip_url}[/cyan]\n"
                    "Start it with: [dim]npx paperclipai run[/dim]"
                )
                raise typer.Exit(1)

            # Confirm identity
            try:
                agent = await pc.get_agent()
            except Exception as exc:
                console.print(f"[red]✗[/red] Could not authenticate with Paperclip: {exc}")
                raise typer.Exit(1)

            console.print(f"[dim]Agent:[/dim] {agent.name} ({agent.id})")

            company_id = config.paperclip_company_id or agent.company_id
            if not company_id:
                console.print("[red]✗[/red] No company ID. Set PAPERCLIP_COMPANY_ID or run devflow setup-paperclip.")
                raise typer.Exit(1)

            # Prefer PAPERCLIP_TASK_ID injected by Paperclip on triggered heartbeats.
            # Fall back to inbox fetch for manual / test runs.
            injected_task_id = os.environ.get("PAPERCLIP_TASK_ID", "")
            if injected_task_id:
                console.print(f"[dim]Task ID from Paperclip:[/dim] {injected_task_id}")
                try:
                    task = await pc.get_issue(injected_task_id)
                except Exception as exc:
                    console.print(f"[red]✗[/red] Could not fetch task {injected_task_id}: {exc}")
                    raise typer.Exit(1)
            else:
                issues = await pc.list_issues(company_id, status="todo,unstarted,in_progress")
                if not issues:
                    console.print("[dim]No tasks in inbox.[/dim]")
                    return
                task = issues[0]

            console.print(
                f"[cyan]Task:[/cyan] {task.identifier} — {task.title} "
                f"[dim]({task.status})[/dim]"
            )

            # Skip checkout if already in_progress (e.g. retried run)
            if task.status == "in_progress":
                console.print("[dim]Task already in_progress — skipping checkout.[/dim]")
            else:
                try:
                    task = await pc.checkout_issue(task.id)
                    console.print(f"[green]✓[/green] Checked out {task.identifier}")
                except PaperclipCheckoutConflict:
                    console.print(f"[yellow]⚠[/yellow] {task.identifier} already checked out by another agent.")
                    return
                except Exception as exc:
                    # 400 can mean issue state won't allow checkout — log and continue
                    console.print(f"[yellow]⚠[/yellow] Checkout returned error ({exc}). Continuing without checkout.")

            # Post acknowledgement comment
            await pc.update_issue(
                task.id,
                status="in_progress",
                comment="devflow heartbeat: task received. Run `devflow feature` to begin.",
            )
            console.print(f"[green]✓[/green] {task.identifier} marked in_progress")
            console.print(
                f"\n[dim]To work on this feature run:[/dim]\n"
                f"  [cyan]devflow feature \"{task.title}\"[/cyan]"
            )

    import asyncio
    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# devflow setup-paperclip
# ─────────────────────────────────────────────────────────────────────────────

@app.command(name="setup-paperclip")
def setup_paperclip(
    api_url: Annotated[
        str,
        typer.Option("--url", help="Paperclip server URL"),
    ] = "http://localhost:3100",
):
    """
    Interactive wizard to connect devflow to a local Paperclip server.

    Creates (or links) a Company, Project, and devflow-feature agent,
    then writes the IDs into devflow.yaml.
    """
    import asyncio

    async def _run() -> None:
        import yaml
        from devflow.paperclip import PaperclipClient

        console.rule("[bold #d946ef]Paperclip Setup[/]")
        console.print(
            f"\nThis wizard connects devflow to Paperclip at [cyan]{api_url}[/cyan].\n"
            "You'll need the Paperclip board open in your browser to create entities.\n"
        )

        # Step 1 — health check
        console.print("[bold]Step 1/5[/bold] — Checking Paperclip server...")
        dummy_client = PaperclipClient(api_url=api_url, api_key="health-check")
        async with dummy_client:
            reachable = await dummy_client.check_health()

        if not reachable:
            console.print(
                f"[red]✗[/red] Cannot reach Paperclip at [cyan]{api_url}[/cyan]\n\n"
                "Start the server first:\n"
                "  [dim]npx paperclipai run[/dim]\n"
                "  — or —\n"
                "  [dim]cd ~/paperclip && pnpm dev[/dim]"
            )
            raise typer.Exit(1)
        console.print(f"[green]✓[/green] Server is up at {api_url}\n")

        # Step 2 — API key
        console.print(
            "[bold]Step 2/5[/bold] — Agent API key\n"
            f"Open [cyan]{api_url}[/cyan] in your browser, create an agent named\n"
            "[bold]devflow-feature[/bold] with adapter type [bold]Process[/bold] and\n"
            "heartbeat command: [dim]devflow heartbeat --once[/dim]\n"
            "Copy the API key shown once after creation.\n"
        )
        api_key = typer.prompt("Paste the API key for devflow-feature")
        if not api_key.strip():
            console.print("[red]✗[/red] API key cannot be empty.")
            raise typer.Exit(1)

        # Step 3 — verify key / get agent ID
        console.print("\n[bold]Step 3/5[/bold] — Verifying API key...")
        async with PaperclipClient(api_url=api_url, api_key=api_key) as pc:
            try:
                agent = await pc.get_agent()
            except Exception as exc:
                console.print(f"[red]✗[/red] API key invalid or agent not found: {exc}")
                raise typer.Exit(1)

        console.print(f"[green]✓[/green] Authenticated as [bold]{agent.name}[/bold] ({agent.id})\n")

        # Step 4 — company & project IDs
        console.print(
            "[bold]Step 4/5[/bold] — Company & Project IDs\n"
            "In the Paperclip board, locate (or create) your Company and\n"
            "the Project for this git repo. Copy their IDs from the URL or settings.\n"
        )
        company_id = typer.prompt("Company ID", default=agent.company_id or "")
        project_id = typer.prompt("Project ID (for this repo)")

        if not company_id or not project_id:
            console.print("[red]✗[/red] Both Company ID and Project ID are required.")
            raise typer.Exit(1)

        # Step 5 — write devflow.yaml
        console.print("\n[bold]Step 5/5[/bold] — Writing devflow.yaml...")

        yaml_path = _find_devflow_yaml()
        if yaml_path is None:
            yaml_path = _cwd() / "devflow.yaml"
            console.print(f"[dim]Creating new {yaml_path}[/dim]")

        existing: dict = {}
        if yaml_path.exists():
            try:
                existing = yaml.safe_load(yaml_path.read_text()) or {}
            except Exception:
                existing = {}

        existing.setdefault("paperclip", {})
        existing["paperclip"]["api_url"] = api_url
        existing["paperclip"]["company_id"] = company_id
        existing["paperclip"]["project_id"] = project_id
        existing["paperclip"]["agent_id"] = agent.id

        with open(yaml_path, "w") as f:
            yaml.dump(existing, f, default_flow_style=False, sort_keys=False)

        console.print(f"[green]✓[/green] Written to {yaml_path}")

        # Summary
        console.rule()
        console.print("\n[bold green]Setup complete.[/bold green]\n")
        console.print(
            "Add these to your [dim].env[/dim] or shell profile:\n\n"
            f"  [cyan]export PAPERCLIP_API_KEY={api_key}[/cyan]\n"
            f"  [cyan]export PAPERCLIP_COMPANY_ID={company_id}[/cyan]\n"
            f"  [cyan]export PAPERCLIP_AGENT_ID={agent.id}[/cyan]\n\n"
            "Then run: [bold]devflow feature \"<your idea>\"[/bold]"
        )

    import asyncio
    asyncio.run(_run())


def _find_devflow_yaml() -> "Optional[Path]":
    """Walk up from cwd to find devflow.yaml."""
    from pathlib import Path
    p = Path.cwd()
    for _ in range(5):
        candidate = p / "devflow.yaml"
        if candidate.exists():
            return candidate
        if p.parent == p:
            break
        p = p.parent
    return None


def _cwd() -> "Path":
    from pathlib import Path
    return Path.cwd()


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
