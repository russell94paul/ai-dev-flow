"""
DevflowApp — mission-control TUI, three-pane layout.

  ┌─ prep │ ▶ feature │ ○ tdd │ ○ qa │ ○ deploy ──────────────────────────────┐
  ├── MISSION ──────────┬───── conversation ──────────┬─── WORKING MEMORY ──────┤
  │ repo  connector     │                             │  ANSWERS                │
  │ br    feature/..    │  ╔ Claude ════════════════╗ │  1. Q1 FastAPI / Python │
  │ feat  add-user..    │  ║ What kind of app?      ║ │  2. Q2 email + password │
  │                     │  ╚════════════════════════╝ │                         │
  │ PHASES              │                             │  FACTS                  │
  │ ✓ grill  done       │  ╔ You ═══════════════════╗ │  stack  fastapi         │
  │ ▶ prd    in progres │  ║ FastAPI / Python / SQL  ║ │  auth   email           │
  │ ○ plan   awaiting   │  ╚════════════════════════╝ │                         │
  │                     │                             │  TIMELINE               │
  │ QUICK REPLY         │   Claude is thinking · · ·  │  14:32 Session started  │
  │ Alt+1 ‣ Accept rec  ├─────────────────────────────┴─────────────────────────┤
  │ Alt+2 ‣ Skip this   │  Q3  │  Focus OFF  │  Shift+Enter  multiline          │
  │ Alt+3 ‣ Elaborate   ├───────────────────────────────────────────────────────┤
  └─────────────────────┴─ ⎇ branch │ model │ Ctrl+K │ Ctrl+F focus │ Ctrl+Q ──┘

Focus mode (Ctrl+F): hides both side rails for full-width reading.
Alt+1–5: keyboard shortcuts to pre-fill macro quick replies.
Shift+Enter: open multiline draft modal (TextArea).
Ctrl+K: command palette — snapshot, copy summary, toggle focus, jump phase.
Click WM answer entry to copy text back into composer.
"""
from __future__ import annotations

import asyncio
import datetime
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal

from devflow.tui.widgets import (
    ComposerStatus,
    ContextPanel,
    InputField,
    MacroPill,
    MultilineDraft,
    OutputPanel,
    StageBar,
    StatusBar,
    ThinkingIndicator,
    UserSubmitted,
    WMEntry,
    WorkingMemoryPanel,
)

# ─────────────────────────────────────────────────────────────────────────────
# Command palette
# ─────────────────────────────────────────────────────────────────────────────

_COMMANDS = [
    ("Toggle focus mode",    "toggle-focus",   "Ctrl+F  Hide side rails, full-width center"),
    ("Snapshot session",     "snapshot",       "Export answers + timeline to build/snapshot.md"),
    ("Copy summary",         "copy-summary",   "Print session summary to output panel"),
    ("Toggle log panel",     "toggle-log",     "Show/hide right working-memory rail"),
    ("Toggle context panel", "toggle-ctx",     "Show/hide left phase-tracker rail"),
    ("Reset session hint",   "reset-hint",     "Show the --reset command"),
]


class DevflowCommands(Provider):
    """Commands exposed via Ctrl+K palette."""

    async def search(self, query: str) -> Hits:
        app: DevflowApp = self.app  # type: ignore
        q = query.lower()
        for label, action, help_text in _COMMANDS:
            if not q or q in label.lower():
                yield Hit(
                    score=1.0,
                    match_display=label,
                    command=lambda a=action: app._run_command(a),
                    help=help_text,
                )


# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

class DevflowApp(App):
    """Root devflow Textual application — mission-control three-pane layout."""

    TITLE = "devflow"

    COMMANDS = App.COMMANDS | {DevflowCommands}

    CSS = """
    Screen {
        background: #0a0e1a;
        layout: vertical;
    }
    #stage-bar       { dock: top; }
    #main-area       { height: 1fr; layout: horizontal; }
    #thinking        { dock: bottom; height: 1; }
    #composer-status { dock: bottom; height: 1; }
    #input-field     { dock: bottom; }
    #status-bar      { dock: bottom; }
    """

    BINDINGS = [
        ("ctrl+q",     "quit",             "Quit"),
        ("ctrl+k",     "command_palette",  "Commands"),
        ("ctrl+f",     "toggle_focus",     "Focus mode"),
        ("shift+enter","open_draft",       "Multiline draft"),
        ("alt+1",      "macro('0')",       "Quick reply 1"),
        ("alt+2",      "macro('1')",       "Quick reply 2"),
        ("alt+3",      "macro('2')",       "Quick reply 3"),
        ("alt+4",      "macro('3')",       "Quick reply 4"),
        ("alt+5",      "macro('4')",       "Quick reply 5"),
    ]

    # ── Macro text in same order as MacroPill widgets in ContextPanel ──────── #
    _MACROS = [
        "yes, looks good — proceed",
        "let's skip this for now",
        "can you elaborate on that?",
        "yes",
        "for context: ",
    ]

    def __init__(self, slug: str, stages: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.slug = slug
        self._stages = stages
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._mode_fn: Optional[Callable] = None
        self._mode_args: tuple = ()
        self._mode_kwargs: dict = {}
        self._focus_mode = False
        self._notes_dir: Optional[Path] = None  # set by mode for snapshot
        self._last_macro_idx: Optional[int] = None

    # ── Layout ────────────────────────────────────────────────────────────── #

    def compose(self) -> ComposeResult:
        yield StageBar(stages=self._stages, id="stage-bar")
        with Horizontal(id="main-area"):
            yield ContextPanel(id="context-panel")
            yield OutputPanel(id="output")
            yield WorkingMemoryPanel(id="working-memory")
        yield ThinkingIndicator(id="thinking")
        yield ComposerStatus(id="composer-status")
        yield InputField(id="input-field")
        yield StatusBar(id="status-bar")

    # ── Accessors ─────────────────────────────────────────────────────────── #

    @property
    def stage_bar(self) -> StageBar:
        return self.query_one("#stage-bar", StageBar)

    @property
    def output(self) -> OutputPanel:
        return self.query_one("#output", OutputPanel)

    @property
    def thinking(self) -> ThinkingIndicator:
        return self.query_one("#thinking", ThinkingIndicator)

    @property
    def input_field(self) -> InputField:
        return self.query_one("#input-field", InputField)

    @property
    def context_panel(self) -> ContextPanel:
        return self.query_one("#context-panel", ContextPanel)

    @property
    def working_memory(self) -> WorkingMemoryPanel:
        return self.query_one("#working-memory", WorkingMemoryPanel)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one("#status-bar", StatusBar)

    @property
    def composer_status(self) -> ComposerStatus:
        return self.query_one("#composer-status", ComposerStatus)

    # ── Helpers ───────────────────────────────────────────────────────────── #

    def emit(self, text: str) -> None:
        """Add a timestamped entry to the working memory timeline."""
        self.working_memory.add_timeline(text)

    def update_context(self, repo: str, branch: str, slug: str) -> None:
        self.context_panel.update_context(repo, branch, slug)
        self.status_bar.set_branch(branch)

    # ── Input ─────────────────────────────────────────────────────────────── #

    def on_user_submitted(self, event: UserSubmitted) -> None:
        self._input_queue.put_nowait(event.text)

    def on_macro_pill_selected(self, event: MacroPill.Selected) -> None:
        if self.input_field.display:
            self.input_field.set_value(event.text)
        else:
            self._input_queue.put_nowait(event.text)

    def on_wm_entry_copy_requested(self, event: WMEntry.CopyRequested) -> None:
        """Copy a WM answer back into the composer input field."""
        if self.input_field.display:
            self.input_field.set_value(event.text)

    async def wait_for_input(self) -> str:
        self.input_field.show()
        text = await self._input_queue.get()
        self.input_field.hide()
        return text

    # ── Mode runner ───────────────────────────────────────────────────────── #

    def run_mode(self, coro_fn: Callable[..., Coroutine[Any, Any, None]], *args, **kwargs) -> None:
        self._mode_fn = coro_fn
        self._mode_args = args
        self._mode_kwargs = kwargs

    def on_mount(self) -> None:
        self.sub_title = self.slug
        if self._mode_fn is not None:
            self.run_worker(self._launch_mode(), exclusive=True)

    async def _launch_mode(self) -> None:
        try:
            await self._mode_fn(self, *self._mode_args, **self._mode_kwargs)
        except Exception as exc:
            self.output.write_line(f"[bold #ef4444]Error:[/] {exc}")

    # ── Actions ───────────────────────────────────────────────────────────── #

    def action_toggle_focus(self) -> None:
        """Ctrl+F — hide/show side rails for distraction-free reading."""
        self._focus_mode = not self._focus_mode
        self.context_panel.display = not self._focus_mode
        self.working_memory.display = not self._focus_mode
        self.status_bar.set_focus_mode(self._focus_mode)
        self.composer_status.set_focus_mode(self._focus_mode)

    def action_macro(self, index: str) -> None:
        """Alt+1-5 — pre-fill a quick-reply macro into the input field."""
        idx = int(index)
        if idx < len(self._MACROS) and self.input_field.display:
            self.input_field.set_value(self._MACROS[idx])
            # Glow the last-used pill
            if self._last_macro_idx is not None:
                try:
                    prev = self.query_one(f"#macro-{self._last_macro_idx}", MacroPill)
                    prev.remove_class("last-used")
                except Exception:
                    pass
            try:
                pill = self.query_one(f"#macro-{idx}", MacroPill)
                pill.add_class("last-used")
                self._last_macro_idx = idx
            except Exception:
                pass

    def action_open_draft(self) -> None:
        """Shift+Enter — open multiline draft modal."""
        if not self.input_field.display:
            return

        def _on_draft(text: str | None) -> None:
            if text:
                self.input_field.set_value(text)

        self.push_screen(MultilineDraft(), _on_draft)

    # ── Command palette actions ────────────────────────────────────────────── #

    def _run_command(self, action: str) -> None:
        if action == "toggle-focus":
            self.action_toggle_focus()
        elif action == "toggle-log":
            wm = self.working_memory
            wm.display = not wm.display
        elif action == "toggle-ctx":
            ctx = self.context_panel
            ctx.display = not ctx.display
        elif action == "snapshot":
            self._snapshot()
        elif action == "copy-summary":
            self._print_summary()
        elif action == "reset-hint":
            self.output.write_line(
                f"[dim #475569]Reset: [/][bold #06b6d4]devflow feature --reset \"{self.slug}\"[/]"
            )

    def _snapshot(self) -> None:
        """Export working memory (answers + facts + timeline) to a markdown file."""
        if self._notes_dir is None:
            self.notify("No active session — snapshot skipped.", severity="warning")
            return

        build_dir = self._notes_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = build_dir / f"snapshot-{ts}.md"

        wm = self.working_memory
        lines = [f"# devflow snapshot — {self.slug}", f"\n_exported {ts}_\n"]

        # Answers
        if wm._answer_count > 0:
            lines.append("\n## Answers\n")
            scroll = wm.query_one("#wm-scroll")
            for w in scroll.query(WMEntry):
                lines.append(f"- {w._full_text}")

        # Facts
        if wm._facts:
            lines.append("\n## Facts\n")
            for k, v in wm._facts.items():
                lines.append(f"- **{k}**: {v}")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        self.notify(f"Snapshot saved → {out_path.name}", severity="information")

    def _print_summary(self) -> None:
        wm = self.working_memory
        lines = [f"[bold #d946ef]Session summary[/] — [dim]{self.slug}[/]"]
        if wm._facts:
            facts_str = "  ".join(f"[bold #f59e0b]{k}[/]=[#475569]{v}[/]" for k, v in wm._facts.items())
            lines.append(f"Facts: {facts_str}")
        lines.append(f"Answers: [#06b6d4]{wm._answer_count}[/]  Phases: see left rail")
        for line in lines:
            self.output.write_line(line)
        self.notify("Summary printed to output.", severity="information")
