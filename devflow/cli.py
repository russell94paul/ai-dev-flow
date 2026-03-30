"""
devflow CLI — Typer entry point.

Usage:
  devflow feature "add user authentication"
  devflow tdd "add-user-authentication"
  devflow skill grill-me
  devflow --version
"""
from __future__ import annotations

import json
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
# devflow deploy
# ─────────────────────────────────────────────────────────────────────────────


@app.command()
def deploy(
    issue_id: Annotated[str, typer.Argument(help="Paperclip issue UUID")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Parse deployment YAML without running Prefect"),
    ] = False,
    cwd: Annotated[
        Optional[str],
        typer.Option("--cwd", help="Working directory for prefect deploy (default: current dir)"),
    ] = None,
):
    """
    Run the Prefect deploy stage for a Paperclip issue.

    Reads the ``deployment`` document from the issue, applies it with
    ``prefect deploy``, runs a smoke test, and reports back to Paperclip.

    Requires PAPERCLIP_API_KEY (or PAPERCLIP_COMPANY_ID) and PREFECT_API_URL.
    See docs/runbook-prefect-creds.md for setup.
    """
    import asyncio
    from devflow.deploy import run_deploy
    from devflow.paperclip import client_from_env

    run_id = os.environ.get("PAPERCLIP_RUN_ID", "")
    pc = client_from_env(run_id=run_id)
    if pc is None:
        console.print(
            "[red]✗[/red] Paperclip credentials not configured. "
            "Set PAPERCLIP_API_KEY or see docs/runbook-prefect-creds.md."
        )
        raise typer.Exit(1)

    async def _run() -> None:
        async with pc:
            console.print(f"[dim]Deploy issue:[/dim] {issue_id}")
            result = await run_deploy(
                issue_id=issue_id,
                pc=pc,
                dry_run=dry_run,
                repo_cwd=cwd,
            )
            if result.success:
                console.print(f"[green]✓[/green] {result.message}")
                if not dry_run:
                    await pc.update_issue(
                        issue_id,
                        status="done",
                        comment=(
                            "## Deploy complete\n\n"
                            f"{result.message}\n\n"
                            f"- State: `{result.state}`\n"
                            f"- Run URL: {result.run_url}"
                        ),
                    )
                    console.print("[green]✓[/green] Paperclip issue marked done.")
            else:
                console.print(f"[red]✗[/red] {result.message}")
                if not dry_run:
                    stdout_block = (
                        f"\n\n### prefect deploy output\n```\n{result.deploy_stdout}\n```"
                        if result.deploy_stdout
                        else ""
                    )
                    await pc.update_issue(
                        issue_id,
                        status="blocked",
                        comment=(
                            "## Deploy blocked\n\n"
                            f"{result.message}"
                            f"{stdout_block}"
                        ),
                    )
                    console.print("[yellow]⚠[/yellow] Paperclip issue marked blocked.")
                raise typer.Exit(1)

    asyncio.run(_run())


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


# ─────────────────────────────────────────────────────────────────────────────
# devflow orient
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def orient(
    issue_id: Annotated[str, typer.Argument(help="Paperclip issue UUID")],
    agent: Annotated[
        Optional[str],
        typer.Option("--agent", help="Agent name (e.g. devflow-builder)"),
    ] = None,
):
    """
    Session context health check — run at the start of every heartbeat.

    Checks proxy signals for stale context, long sessions, fix-break-fix
    loops, unread comments, and model tier. Validates required tools exist.

    Exit codes:
      0  OK — proceed
      1  Hard block — issue cancelled, reassigned, or missing required tools
      2  Warning — stale session, model tier, or unread comments (logged, proceeds)

    Requires PAPERCLIP_API_KEY.
    """
    import asyncio
    from devflow.orient import run_orient

    async def _run() -> int:
        from devflow.paperclip import client_from_env

        config = Config()
        if not config.paperclip_enabled:
            console.print("[red]✗[/red] PAPERCLIP_API_KEY is not set.")
            return 1

        pc = client_from_env()
        async with pc:
            if not await pc.check_health():
                console.print(
                    f"[red]✗[/red] Paperclip unreachable at [cyan]{config.paperclip_url}[/cyan]"
                )
                return 1

            result = await run_orient(
                pc=pc,
                issue_id=issue_id,
                agent_name=agent or "",
            )

        if result.blocked:
            console.print(f"[red]✗ HARD BLOCK[/red]  {result.hard_block_reason}")
            if result.warnings:
                for w in result.warnings:
                    console.print(f"  [yellow]⚠[/yellow] {w}")
            return 1

        if result.warnings:
            for w in result.warnings:
                console.print(f"[yellow]⚠[/yellow] {w}")

        missing_optional = [t for t, ok in result.tool_check.items() if not ok]
        if missing_optional:
            console.print(f"[dim]Optional tools not found: {', '.join(missing_optional)}[/dim]")

        if result.exit_code == 0:
            console.print(f"[green]✓[/green] orient OK — {issue_id}")

        return result.exit_code

    code = asyncio.run(_run())
    raise typer.Exit(code)


# ─────────────────────────────────────────────────────────────────────────────
# devflow export-artifacts
# ─────────────────────────────────────────────────────────────────────────────

@app.command(name="export-artifacts")
def export_artifacts(
    all_open: Annotated[
        bool,
        typer.Option("--all-open", help="Export documents for all open issues"),
    ] = False,
    output: Annotated[
        str,
        typer.Option("--output", "-o", help="Output directory (default: ./archive/pre-v3)"),
    ] = "./archive/pre-v3",
):
    """
    Download all Paperclip documents for open issues to a local archive.

    Creates <output>/<issue-id>/<doc-key>.md for each document found.
    Run this before devflow ceo-init --apply to preserve pre-v3 artifacts.
    Requires PAPERCLIP_API_KEY and PAPERCLIP_COMPANY_ID.
    """
    import asyncio
    import json
    from pathlib import Path

    async def _run() -> None:
        from devflow.paperclip import client_from_env

        config = Config()
        if not config.paperclip_enabled:
            console.print("[red]✗[/red] PAPERCLIP_API_KEY is not set.")
            raise typer.Exit(1)

        company_id = config.paperclip_company_id
        if not company_id:
            console.print("[red]✗[/red] PAPERCLIP_COMPANY_ID is not set.")
            raise typer.Exit(1)

        if not all_open:
            console.print(
                "[yellow]⚠[/yellow] No scope specified. Use [bold]--all-open[/bold] to export all open issues."
            )
            raise typer.Exit(1)

        pc = client_from_env()
        async with pc:
            if not await pc.check_health():
                console.print(
                    f"[red]✗[/red] Paperclip unreachable at [cyan]{config.paperclip_url}[/cyan]"
                )
                raise typer.Exit(1)

            issues = await pc.list_issues(
                company_id,
                status="todo,unstarted,in_progress,in_review,blocked",
                limit=200,
            )
            if not issues:
                console.print("[dim]No open issues found.[/dim]")
                return

            out_root = Path(output)
            out_root.mkdir(parents=True, exist_ok=True)
            console.print(
                f"[cyan]Exporting[/cyan] {len(issues)} open issue(s) → [dim]{out_root}[/dim]"
            )

            total_docs = 0
            for issue in issues:
                issue_dir = out_root / issue.id
                issue_dir.mkdir(parents=True, exist_ok=True)

                # Write issue metadata
                meta = {
                    "id": issue.id,
                    "identifier": issue.identifier,
                    "title": issue.title,
                    "status": issue.status,
                    "assignee_id": issue.assignee_id,
                    "project_id": issue.project_id,
                }
                (issue_dir / "_issue.json").write_text(
                    json.dumps(meta, indent=2), encoding="utf-8"
                )

                docs = await pc.list_documents(issue.id)
                for doc in docs:
                    key = doc.get("key") or doc.get("id") or "unknown"
                    body = doc.get("body", "")
                    fmt = doc.get("format", "markdown")
                    ext = "json" if fmt == "json" else "md"
                    (issue_dir / f"{key}.{ext}").write_text(body or "", encoding="utf-8")
                    total_docs += 1

                label = f"[green]{issue.identifier}[/green]" if docs else f"[dim]{issue.identifier}[/dim]"
                console.print(f"  {label} — {len(docs)} doc(s)")

            console.print(
                f"\n[green]✓[/green] Exported {total_docs} document(s) from {len(issues)} issue(s) to [dim]{out_root}[/dim]"
            )

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# devflow ceo-init
# ─────────────────────────────────────────────────────────────────────────────

# Legacy agent names to retire in the v3 rollout.
_LEGACY_AGENT_NAMES = {"devflow-connector-builder", "devflow-prefect-qa"}

# V3 agents to register/verify exist.
_V3_AGENT_NAMES = {"devflow-builder", "devflow-reviewer", "devflow-qa", "devflow-feature", "devflow-sre"}


def _classify_issue(status: str, has_state_doc: bool) -> str:
    """
    Classify an open issue for the v3 rollout.

    Returns:
      'ignore'  — already done/cancelled; no action needed
      'archive' — close with retirement note
      'migrate' — keep; run devflow sync <id> --migrate-v3 --apply
    """
    if status in ("completed", "done", "cancelled"):
        return "ignore"
    if status == "blocked":
        return "archive"
    if status in ("in_progress", "in_review"):
        return "migrate" if has_state_doc else "archive"
    # unstarted / todo / unknown
    return "archive"


@app.command(name="ceo-init")
def ceo_init(
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Audit state and preview changes (no writes)"),
    ] = False,
    apply: Annotated[
        bool,
        typer.Option("--apply", help="Execute the v3 rollout changes"),
    ] = False,
    archive_all: Annotated[
        bool,
        typer.Option(
            "--archive-all",
            help="Archive ALL open issues (including those with artifacts). "
                 "Use when you do not want to carry any pre-v3 issues forward.",
        ),
    ] = False,
):
    """
    One-time v3 rollout command.

    --dry-run      Audit open issues (migrate/archive/ignore), list legacy
                   agents, and preview what --apply would do. Makes no changes.

    --apply        Post retirement notices on legacy-agent issues, cancel open
                   issues, and post a pinned board announcement.

    --archive-all  Used with --apply. Archives ALL open issues, including those
                   with existing artifacts (normally classified as 'migrate').
                   Use this when you are starting v3 clean with no carry-overs.

    Run export-artifacts first to preserve pre-v3 documents.
    Requires PAPERCLIP_API_KEY and PAPERCLIP_COMPANY_ID.
    """
    import asyncio
    from datetime import date

    if not dry_run and not apply:
        console.print(
            "[yellow]⚠[/yellow] Specify [bold]--dry-run[/bold] to audit or [bold]--apply[/bold] to execute."
        )
        raise typer.Exit(1)

    if dry_run and apply:
        console.print("[red]✗[/red] --dry-run and --apply are mutually exclusive.")
        raise typer.Exit(1)

    async def _run() -> None:
        from devflow.paperclip import client_from_env

        config = Config()
        if not config.paperclip_enabled:
            console.print("[red]✗[/red] PAPERCLIP_API_KEY is not set.")
            raise typer.Exit(1)

        company_id = config.paperclip_company_id
        if not company_id:
            console.print("[red]✗[/red] PAPERCLIP_COMPANY_ID is not set.")
            raise typer.Exit(1)

        pc = client_from_env()
        async with pc:
            if not await pc.check_health():
                console.print(
                    f"[red]✗[/red] Paperclip unreachable at [cyan]{config.paperclip_url}[/cyan]"
                )
                raise typer.Exit(1)

            console.rule("[bold #d946ef]devflow ceo-init[/] — v3 rollout audit")

            # ── 1. Fetch open issues ──────────────────────────────────────────
            issues = await pc.list_issues(
                company_id,
                status="todo,unstarted,in_progress,in_review,blocked",
                limit=200,
            )
            console.print(f"\n[bold]Issues[/bold] — {len(issues)} open\n")

            classify_results: dict[str, list] = {"migrate": [], "archive": [], "ignore": []}
            for issue in issues:
                state_doc = await pc.load_state(issue.id)
                has_state = bool(state_doc)
                label = _classify_issue(issue.status, has_state)
                classify_results[label].append(issue)

                colour = {"migrate": "green", "archive": "yellow", "ignore": "dim"}.get(label, "white")
                console.print(
                    f"  [{colour}]{label:8}[/{colour}]  {issue.identifier}  [dim]{issue.status}[/dim]  {issue.title[:60]}"
                )

            migrate_count = len(classify_results["migrate"])
            archive_count = len(classify_results["archive"])
            console.print(
                f"\n  → {migrate_count} to migrate, {archive_count} to archive, "
                f"{len(classify_results['ignore'])} to ignore\n"
            )

            # ── 2. Fetch agent roster ─────────────────────────────────────────
            console.print("[bold]Agent roster[/bold]")
            try:
                all_agents = await pc.list_agents(company_id)
            except Exception as exc:
                console.print(f"  [yellow]⚠[/yellow] Could not fetch agent roster: {exc}")
                all_agents = []

            agent_names = {a.get("name", "") for a in all_agents}
            legacy_found = [a for a in all_agents if a.get("name", "") in _LEGACY_AGENT_NAMES]
            missing_v3 = _V3_AGENT_NAMES - agent_names

            for agent in all_agents:
                name = agent.get("name", agent.get("id", "?"))
                tag = " [red][LEGACY — to retire][/red]" if name in _LEGACY_AGENT_NAMES else ""
                console.print(f"  {name}{tag}")

            if missing_v3:
                console.print(f"\n  [yellow]Missing v3 agents:[/yellow] {', '.join(sorted(missing_v3))}")

            # ── 3. Preview / execute ──────────────────────────────────────────
            console.print()
            if dry_run:
                console.rule("[dim]dry-run — no changes made[/dim]")
                console.print("\nTo proceed:\n")
                console.print(
                    "  1. Export pre-v3 artifacts first:\n"
                    "     [cyan]devflow export-artifacts --all-open --output ./archive/pre-v3[/cyan]\n"
                )
                if migrate_count and not archive_all:
                    console.print(
                        f"  2. {migrate_count} issue(s) have existing artifacts (classified [green]migrate[/green]).\n"
                        "     To archive them all and start v3 clean (recommended):\n"
                        "     [cyan]devflow ceo-init --apply --archive-all[/cyan]\n\n"
                        "     To carry them forward into v3 instead (requires WS8):\n"
                        "     [cyan]devflow sync <issue-id> --migrate-v3 --apply[/cyan]  then\n"
                        "     [cyan]devflow ceo-init --apply[/cyan]\n"
                    )
                else:
                    console.print(f"  2. When ready: [cyan]devflow ceo-init --apply[/cyan]")
                return

            # ── apply mode ────────────────────────────────────────────────────
            if archive_all and classify_results["migrate"]:
                classify_results["archive"].extend(classify_results["migrate"])
                classify_results["migrate"] = []
                console.print(
                    f"[dim]--archive-all: {len(classify_results['archive'])} issue(s) will be archived "
                    f"(including those with existing artifacts)[/dim]\n"
                )

            console.rule("[bold green]Applying v3 rollout[/bold green]")

            rollout_date = date.today().isoformat()
            retirement_note = (
                "## v3 pipeline rollout\n\n"
                f"This issue was assigned to a legacy agent (`{', '.join(_LEGACY_AGENT_NAMES)}`). "
                "These agents are retired as of the v3 rollout. "
                "Reassigned to devflow-feature (v3 orchestrator).\n\n"
                f"Rollout date: {rollout_date}"
            )

            # Post retirement notices on issues held by legacy agents
            retired = 0
            for issue in issues:
                if issue.assignee_id:
                    # Check if the assignee is a legacy agent
                    assigned_agent = next(
                        (a for a in all_agents if a.get("id") == issue.assignee_id), None
                    )
                    if assigned_agent and assigned_agent.get("name", "") in _LEGACY_AGENT_NAMES:
                        await pc.post_comment(issue.id, retirement_note)
                        console.print(
                            f"  [yellow]retired[/yellow]  {issue.identifier} — posted retirement notice"
                        )
                        retired += 1

            if retired == 0:
                console.print("  [dim]No issues assigned to legacy agents — nothing to reassign.[/dim]")

            # Archive issues classified as 'archive'
            archived = 0
            for issue in classify_results["archive"]:
                archive_comment = (
                    "## v3 rollout — archived\n\n"
                    "This issue had no in-progress artifacts and is archived as part of the v3 pipeline rollout. "
                    "If still relevant, create a fresh issue using the v3 issue template.\n\n"
                    f"Archived: {rollout_date}"
                )
                await pc.update_issue(issue.id, status="cancelled", comment=archive_comment)
                console.print(f"  [dim]archived[/dim]   {issue.identifier} — cancelled + comment posted")
                archived += 1

            # Post migration reminders on migrate issues
            for issue in classify_results["migrate"]:
                await pc.post_comment(
                    issue.id,
                    f"## v3 rollout — migration needed\n\n"
                    f"This issue has existing artifacts and is marked for v3 migration.\n\n"
                    f"Run: `devflow sync {issue.id} --migrate-v3 --apply`\n\n"
                    f"Rollout date: {rollout_date}",
                )
                console.print(f"  [green]migrate[/green]    {issue.identifier} — migration reminder posted")

            # Post board announcement
            announcement = (
                f"## v3 pipeline active\n\n"
                f"The ai-dev-flow v3 pipeline is now active as of **{rollout_date}**.\n\n"
                f"**Changes:**\n"
                f"- Legacy agents retired: {', '.join(sorted(_LEGACY_AGENT_NAMES))}\n"
                f"- V3 agents active: devflow-feature (orchestrator), devflow-builder, "
                f"devflow-reviewer, devflow-qa, devflow-sre, devflow-ceo\n"
                f"- {archived} pre-v3 issues archived\n"
                f"- {migrate_count} issues flagged for migration\n\n"
                f"See `docs/aldc-integration-plan-v0.6.md` for the full v3 plan."
            )
            # Post to the first open issue as a board-level notice (Paperclip
            # does not expose a board-level comment endpoint in v1 API).
            if issues:
                await pc.post_comment(issues[0].id, announcement)
                console.print(
                    f"\n  [green]✓[/green] Pinned announcement posted to {issues[0].identifier}"
                )
            else:
                console.print("\n  [dim]No open issues — announcement skipped.[/dim]")

            console.rule()
            console.print(
                f"\n[bold green]ceo-init complete.[/bold green]  "
                f"{archived} archived · {migrate_count} flagged for migration · "
                f"{retired} retirement notices posted\n"
            )

    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# devflow gate
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def gate(
    entering: Annotated[str, typer.Option("--entering", help="Phase to enter (grill/prd/plan/build/review/qa/security/deploy/done)")],
    slug: Annotated[str, typer.Option("--slug", help="Feature slug")],
    issue_id: Annotated[
        Optional[str],
        typer.Option("--issue-id", help="Paperclip issue UUID (optional; used to load state)"),
    ] = None,
    dir: Annotated[
        Optional[str],
        typer.Option("--dir", help="Feature directory (default: ./features/<slug>)"),
    ] = None,
    feature_type: Annotated[
        Optional[str],
        typer.Option("--feature-type", help="Override state.feature_type (new_feature/bugfix/refactor/connector)"),
    ] = None,
):
    """
    Read-only precondition check before entering a phase.

    Exit 0 = all checks pass (proceed).
    Exit 1 = one or more checks failed (blocked).

    State is loaded from Paperclip if PAPERCLIP_API_KEY is set and --issue-id
    is provided; otherwise falls back to a local state file.
    """
    import asyncio
    from pathlib import Path
    from devflow.gatekeeper import gate_phase

    feature_dir = Path(dir) if dir else Path.cwd() / "features" / slug

    # Load state — try Paperclip first, fall back to local
    state: dict = {}
    if issue_id:
        config = Config()
        if config.paperclip_enabled:
            from devflow.paperclip import client_from_env

            async def _fetch_state() -> dict:
                pc = client_from_env()
                if pc is None:
                    return {}
                async with pc:
                    return await pc.load_state(issue_id)

            try:
                state = asyncio.run(_fetch_state())
            except Exception:
                pass

    # Fall back to local state file if Paperclip gave nothing
    if not state:
        local_state_path = feature_dir / "ops" / "state.json"
        if local_state_path.exists():
            try:
                state = json.loads(local_state_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    result = gate_phase(
        phase=entering,
        feature_dir=feature_dir,
        state=state,
        feature_type=feature_type,
    )

    if result.passed:
        console.print(f"[green]✓[/green] gate --entering {entering}  PASS")
        raise typer.Exit(0)

    console.print(f"[red]✗[/red] gate --entering {entering}  BLOCKED\n")
    for failure, recovery in zip(result.failures, result.recoveries):
        console.print(f"  [red]FAIL[/red]  {failure}")
        console.print(f"  [dim]→[/dim]     {recovery}\n")
    raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# devflow seal
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def seal(
    completing: Annotated[str, typer.Option("--completing", help="Phase that just completed (grill/prd/plan/build/review/qa/security/deploy)")],
    slug: Annotated[str, typer.Option("--slug", help="Feature slug")],
    issue_id: Annotated[
        Optional[str],
        typer.Option("--issue-id", help="Paperclip issue UUID (optional; used to load/save state)"),
    ] = None,
    dir: Annotated[
        Optional[str],
        typer.Option("--dir", help="Feature directory (default: ./features/<slug>)"),
    ] = None,
    waive_coverage: Annotated[
        bool,
        typer.Option("--waive-coverage", help="Waive coverage threshold failure (records waiver in manifest)"),
    ] = False,
    waive_diagrams: Annotated[
        bool,
        typer.Option("--waive-diagrams", help="Waive Mermaid diagram check failure (records waiver in manifest)"),
    ] = False,
):
    """
    Validate artifacts for a completing phase and write ops/verification-manifest.json.

    Exit 0 = all checks pass (manifest written).
    Exit 1 = one or more checks failed (manifest NOT written).

    State is loaded from Paperclip if PAPERCLIP_API_KEY is set and --issue-id
    is provided; any state_updates returned by seal are saved back to Paperclip.
    """
    import asyncio
    import json as _json
    from pathlib import Path
    from devflow.gatekeeper import seal_phase

    feature_dir = Path(dir) if dir else Path.cwd() / "features" / slug

    # Load state
    state: dict = {}
    if issue_id:
        config = Config()
        if config.paperclip_enabled:
            from devflow.paperclip import client_from_env

            async def _fetch_state() -> dict:
                pc = client_from_env()
                if pc is None:
                    return {}
                async with pc:
                    return await pc.load_state(issue_id)

            try:
                state = asyncio.run(_fetch_state())
            except Exception:
                pass

    if not state:
        local_state_path = feature_dir / "ops" / "state.json"
        if local_state_path.exists():
            try:
                state = _json.loads(local_state_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    result = seal_phase(
        phase=completing,
        slug=slug,
        issue_id=issue_id or "",
        feature_dir=feature_dir,
        state=state,
        waive_coverage=waive_coverage,
        waive_diagrams=waive_diagrams,
    )

    # Print warnings regardless of pass/fail
    for w in result.warnings:
        console.print(f"  [yellow]⚠[/yellow]  {w}")

    if result.passed:
        console.print(f"[green]✓[/green] seal --completing {completing}  PASS")
        if result.artifacts:
            console.print(f"  [dim]artifacts:[/dim] {', '.join(result.artifacts)}")
        if result.waivers:
            for waiver in result.waivers:
                console.print(f"  [yellow]waiver:[/yellow] {waiver}")

        # Save state updates back to Paperclip or local state file
        if result.state_updates:
            updated_state = {**state, **result.state_updates}
            saved_to_paperclip = False
            if issue_id:
                _config = Config()
                if _config.paperclip_enabled:
                    from devflow.paperclip import client_from_env

                    async def _save_state() -> None:
                        pc = client_from_env()
                        if pc is None:
                            return
                        async with pc:
                            await pc.save_state(issue_id, updated_state)

                    try:
                        asyncio.run(_save_state())
                        saved_to_paperclip = True
                        console.print(f"  [dim]state updates saved to Paperclip:[/dim] {list(result.state_updates.keys())}")
                    except Exception as exc:
                        console.print(f"  [yellow]⚠[/yellow] Could not save state to Paperclip: {exc}")

            if not saved_to_paperclip:
                # Write to local state file
                local_state_path = feature_dir / "ops" / "state.json"
                local_state_path.parent.mkdir(parents=True, exist_ok=True)
                local_state_path.write_text(
                    _json.dumps(updated_state, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                console.print(f"  [dim]state updates written to {local_state_path}:[/dim] {list(result.state_updates.keys())}")

        raise typer.Exit(0)

    console.print(f"[red]✗[/red] seal --completing {completing}  FAIL\n")
    for failure, recovery in zip(result.failures, result.recoveries):
        console.print(f"  [red]FAIL[/red]  {failure}")
        console.print(f"  [dim]→[/dim]     {recovery}\n")
    raise typer.Exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# devflow publish-artifacts
# ─────────────────────────────────────────────────────────────────────────────

@app.command(name="publish-artifacts")
def publish_artifacts(
    issue_id: Annotated[str, typer.Option("--issue-id", help="Paperclip issue UUID")],
    slug: Annotated[str, typer.Option("--slug", help="Feature slug")],
    phase: Annotated[str, typer.Option("--phase", help="Pipeline phase (prd/plan/build/review/qa/security/deploy/done)")],
    dir: Annotated[
        Optional[str],
        typer.Option("--dir", help="Feature directory (default: ./features/<slug>)"),
    ] = None,
):
    """
    Upload phase artifacts to Paperclip and record results in
    ops/verification-manifest.json.

    For each artifact defined for the phase in the artifact contract, checks
    that the local file exists, uploads it via PUT /api/issues/{id}/documents/{key},
    and records the revision ID in the manifest.

    Exit 0 = all critical artifacts uploaded successfully.
    Exit 1 = one or more critical artifacts failed to upload.

    Requires PAPERCLIP_API_KEY.
    """
    import asyncio
    from pathlib import Path
    from devflow.artifact_publisher import publish_artifacts as _publish, PHASE_ARTIFACTS

    feature_dir = Path(dir) if dir else Path.cwd() / "features" / slug

    valid_phases = list(PHASE_ARTIFACTS.keys())
    if phase not in valid_phases:
        console.print(
            f"[red]✗[/red] Unknown phase [bold]{phase}[/bold]. "
            f"Valid phases: {', '.join(valid_phases)}"
        )
        raise typer.Exit(1)

    config = Config()
    if not config.paperclip_enabled:
        console.print(
            "[red]✗[/red] Paperclip credentials not configured. "
            "Set PAPERCLIP_API_KEY or see docs/runbook-prefect-creds.md."
        )
        raise typer.Exit(1)

    from devflow.paperclip import client_from_env

    run_id = os.environ.get("PAPERCLIP_RUN_ID", "")
    pc = client_from_env(run_id=run_id)
    if pc is None:
        console.print("[red]✗[/red] Could not build Paperclip client from environment.")
        raise typer.Exit(1)

    async def _run() -> int:
        async with pc:
            console.print(
                f"[dim]publish-artifacts:[/dim] issue={issue_id}  slug={slug}  "
                f"phase={phase}  dir={feature_dir}"
            )
            result = await _publish(
                issue_id=issue_id,
                slug=slug,
                phase=phase,
                feature_dir=feature_dir,
                pc=pc,
            )

        if not result.uploads and not result.critical_failures:
            console.print(f"[dim]No artifacts defined for phase {phase}.[/dim]")
            return 0

        for upload in result.uploads:
            if upload.status == "ok":
                console.print(
                    f"  [green]✓[/green]  {upload.key}  "
                    f"[dim]{upload.path}  rev={upload.revision_id}[/dim]"
                )
            elif upload.status == "missing":
                console.print(f"  [yellow]⚠[/yellow]  {upload.key}  [dim]{upload.path}[/dim]  — missing")
            else:
                console.print(
                    f"  [red]✗[/red]  {upload.key}  [dim]{upload.path}[/dim]  "
                    f"— {upload.error}"
                )

        for w in result.warnings:
            console.print(f"  [yellow]⚠[/yellow]  {w}")

        if result.critical_failures:
            console.print(f"\n[red]✗[/red] publish-artifacts BLOCKED — critical artifact(s) failed:")
            for cf in result.critical_failures:
                console.print(f"  [red]FAIL[/red]  {cf}")
            return 1

        ok_count = sum(1 for u in result.uploads if u.status == "ok")
        console.print(f"\n[green]✓[/green] publish-artifacts OK — {ok_count} artifact(s) uploaded")
        return 0

    exit_code = asyncio.run(_run())
    raise typer.Exit(exit_code)


# ─────────────────────────────────────────────────────────────────────────────
# devflow metrics
# ─────────────────────────────────────────────────────────────────────────────

@app.command()
def metrics(
    slug: Annotated[
        Optional[str],
        typer.Option("--slug", help="Feature slug for per-feature report"),
    ] = None,
    summary: Annotated[
        bool,
        typer.Option("--summary", help="Print summary across all features"),
    ] = False,
    output: Annotated[
        Optional[str],
        typer.Option("--output", help="Write markdown report to this file (requires --summary)"),
    ] = None,
    dir: Annotated[
        Optional[str],
        typer.Option("--dir", help="Root directory to scan for features/ (default: CWD)"),
    ] = None,
):
    """
    Report metrics from verification-manifest.json files.

    Per-feature:   devflow metrics --slug <slug>
    Summary:       devflow metrics --summary
    Markdown file: devflow metrics --summary --output metrics-report.md
    """
    from pathlib import Path as _Path
    from devflow.metrics import (
        report_slug,
        print_slug_report,
        compute_summary,
        print_summary_report,
        build_markdown_report,
    )

    scan_root = _Path(dir) if dir else _Path.cwd()

    if slug and not summary:
        try:
            m = report_slug(slug, scan_root)
        except FileNotFoundError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1)
        print_slug_report(m)
        raise typer.Exit(0)

    if summary or output:
        s = compute_summary(scan_root)
        print_summary_report(s)
        if output:
            md = build_markdown_report(s)
            out_path = _Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md, encoding="utf-8")
            console.print(f"\n[green]✓[/green] Markdown report written to {out_path}")
        raise typer.Exit(0)

    # Neither --slug nor --summary provided
    console.print("[yellow]Usage:[/yellow] devflow metrics --slug <slug>  OR  devflow metrics --summary")
    raise typer.Exit(1)


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
