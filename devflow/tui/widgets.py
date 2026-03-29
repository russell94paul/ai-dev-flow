"""
devflow TUI widgets — mission-control dark theme.

Color palette:
  Background   #0a0e1a   dark navy
  Surface      #0d1221   card surface
  Border       #1e293b   subtle border
  Claude       #3b82f6   blue
  User         #10b981   emerald
  Cyan         #06b6d4   active / running
  Magenta      #d946ef   section headers
  Amber        #f59e0b   facts / pinned / new entries
  Text         #e2e8f0
  Dim          #475569
  Dim2         #334155
"""
from __future__ import annotations

import datetime
import re

from rich.markup import escape
from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Input, Label, Static, TextArea
from textual.containers import Vertical, VerticalScroll


# ─────────────────────────────────────────────────────────────────────────────
# Stage bar
# ─────────────────────────────────────────────────────────────────────────────

ALL_STAGES = ["prep", "feature", "tdd", "qa", "deploy"]

_PILL = {
    "pending": lambda s: f"[dim #334155]  {s}  [/]",
    "running": lambda s: f"[bold #06b6d4] ▶ {s} [/]",
    "done":    lambda s: f"[bold #10b981] ✓ {s} [/]",
    "failed":  lambda s: f"[bold #ef4444] ✗ {s} [/]",
    "skipped": lambda s: f"[dim #334155]  {s}  [/]",
}
_SEP = "[dim #1e293b] │ [/]"


class StageBar(Static):
    """Horizontal pipeline stage indicator, docked at top."""

    DEFAULT_CSS = """
    StageBar {
        height: 1;
        background: #0d1221;
        color: #e2e8f0;
        padding: 0 2;
        border-bottom: tall #06b6d4;
    }
    """

    def __init__(self, stages: list[str] | None = None, **kwargs):
        super().__init__(**kwargs)
        self._stages: list[str] = stages or ALL_STAGES
        self._status: dict[str, str] = {s: "pending" for s in self._stages}

    def set_status(self, stage: str, status: str) -> None:
        if stage in self._status:
            self._status[stage] = status
            self._refresh()

    def set_running(self, stage: str) -> None:
        self.set_status(stage, "running")

    def set_done(self, stage: str) -> None:
        self.set_status(stage, "done")

    def set_failed(self, stage: str) -> None:
        self.set_status(stage, "failed")

    def _refresh(self) -> None:
        pills = [_PILL[self._status[s]](s) for s in self._stages]
        self.update(_SEP.join(pills))

    def on_mount(self) -> None:
        self._refresh()


# ─────────────────────────────────────────────────────────────────────────────
# Message panels
# ─────────────────────────────────────────────────────────────────────────────

def _timestamp() -> str:
    return datetime.datetime.now().strftime("%H:%M")


# Lines that indicate a recommendation from Claude
_REC_PREFIXES = (
    "> *my rec",
    "> **my rec",
    "**my recommendation",
    "my recommendation:",
    "> my recommendation",
)


def _render_body(body: str) -> str:
    """
    Render Claude's response body, turning recommendation lines into
    a cyan callout block.
    """
    lines = []
    for line in body.split("\n"):
        stripped = line.strip().lower()
        if any(stripped.startswith(p) for p in _REC_PREFIXES):
            # Strip markdown asterisks and leading > for display
            clean = re.sub(r"\*+", "", line.strip()).lstrip("> ").strip()
            # Remove leading "My recommendation:" label if present
            clean = re.sub(r"^my recommendation\s*:\s*", "", clean, flags=re.IGNORECASE)
            lines.append(f"[bold #06b6d4] ▎ {escape(clean)}[/]")
        else:
            lines.append(escape(line))
    return "\n".join(lines)


class ClaudeMessage(Static):
    """Claude's response — blue left border, dark blue panel."""

    DEFAULT_CSS = """
    ClaudeMessage {
        background: #0d1b2a;
        border-left: tall #3b82f6;
        padding: 1 2;
        margin: 1 0 0 0;
        color: #e2e8f0;
    }
    """

    def __init__(self, body: str = "", **kwargs):
        super().__init__(self._build(body), **kwargs)
        self._body = body

    def stream_update(self, body: str) -> None:
        self._body = body
        self.update(self._build(body))

    def _build(self, body: str) -> str:
        header = f"[bold #3b82f6]Claude[/]  [dim #475569]{_timestamp()}[/]"
        divider = f"[dim #1e3a5f]{'─' * 50}[/]"
        return f"{header}\n{divider}\n{_render_body(body)}"


class UserMessage(Static):
    """User's reply — emerald left border, dark green panel."""

    DEFAULT_CSS = """
    UserMessage {
        background: #0d2318;
        border-left: tall #10b981;
        padding: 1 2;
        margin: 1 0 0 0;
        color: #e2e8f0;
    }
    """

    def __init__(self, body: str = "", **kwargs):
        super().__init__(self._build(body), **kwargs)

    def _build(self, body: str) -> str:
        header = f"[bold #10b981]You[/]  [dim #475569]{_timestamp()}[/]"
        divider = f"[dim #0f3d28]{'─' * 50}[/]"
        return f"{header}\n{divider}\n{escape(body)}"


class SystemMessage(Static):
    """Status line or separator — muted styling."""

    DEFAULT_CSS = """
    SystemMessage {
        color: #475569;
        padding: 0 2;
        margin: 0;
    }
    """


# ─────────────────────────────────────────────────────────────────────────────
# Output panel (center)
# ─────────────────────────────────────────────────────────────────────────────

class OutputPanel(Widget):
    """Scrollable conversation output — center pane."""

    DEFAULT_CSS = """
    OutputPanel {
        background: #0a0e1a;
        width: 1fr;
        height: 1fr;
    }
    OutputPanel VerticalScroll {
        background: #0a0e1a;
        border: none;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield VerticalScroll()

    @property
    def _scroll(self) -> VerticalScroll:
        return self.query_one(VerticalScroll)

    async def mount_message(self, widget: Widget) -> None:
        await self._scroll.mount(widget)
        self._scroll.scroll_end(animate=False)

    def scroll_end(self) -> None:
        self._scroll.scroll_end(animate=False)

    def write_line(self, text: str) -> None:
        self._scroll.mount(SystemMessage(text))
        self._scroll.scroll_end(animate=False)

    def write_separator(self) -> None:
        self._scroll.mount(SystemMessage(f"[dim #1e293b]{'─' * 60}[/]"))
        self._scroll.scroll_end(animate=False)


# ─────────────────────────────────────────────────────────────────────────────
# Left rail — Phase tracker + context
# ─────────────────────────────────────────────────────────────────────────────

_PHASE_LABEL = {
    "pending":  lambda p: f"[dim #334155]○ {p:<8}[/] [dim #1e293b]awaiting[/]",
    "running":  lambda p: f"[bold #06b6d4]▶ {p:<8}[/] [#06b6d4]in progress[/]",
    "done":     lambda p: f"[bold #10b981]✓ {p:<8}[/] [dim #10b981]done[/]",
}


class MacroPill(Static, can_focus=True):
    """Compact quick-reply button with a visible keyboard shortcut hint."""

    DEFAULT_CSS = """
    MacroPill {
        height: 1;
        padding: 0 1;
        margin: 0 0 1 0;
        background: #111827;
        color: #475569;
    }
    MacroPill:hover {
        background: #0c3a4a;
        color: #e2e8f0;
    }
    MacroPill:focus {
        background: #0c3a4a;
        color: #06b6d4;
    }
    MacroPill.last-used {
        background: #0c2a3a;
        color: #06b6d4;
    }
    """

    class Selected(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, label: str, text: str, shortcut: str = "", **kwargs):
        hint = f"[dim #1e293b]{shortcut}[/] " if shortcut else ""
        super().__init__(f"{hint}[dim #334155]‣[/] {label}", **kwargs)
        self._text = text

    def on_click(self) -> None:
        self.post_message(self.Selected(self._text))

    def on_key(self, event) -> None:
        if event.key == "enter":
            self.post_message(self.Selected(self._text))
            event.stop()


class ContextPanel(Widget):
    """Left rail: phase tracker with states + mission metadata."""

    DEFAULT_CSS = """
    ContextPanel {
        width: 24;
        background: #0d1221;
        border-right: tall #1e293b;
        padding: 1 1;
        layout: vertical;
        overflow-y: auto;
        height: 1fr;
    }
    ContextPanel .rail-hdr {
        color: #d946ef;
        text-style: bold;
        height: 1;
        margin: 1 0 0 0;
    }
    ContextPanel .ctx-row {
        color: #475569;
        height: 1;
        overflow: hidden;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("MISSION", classes="rail-hdr")
        yield Static("", id="ctx-repo",   classes="ctx-row")
        yield Static("", id="ctx-branch", classes="ctx-row")
        yield Static("", id="ctx-slug",   classes="ctx-row")
        yield Static("PHASES", classes="rail-hdr")
        yield Static(_PHASE_LABEL["pending"]("grill"), id="phase-grill", classes="ctx-row")
        yield Static(_PHASE_LABEL["pending"]("prd"),   id="phase-prd",   classes="ctx-row")
        yield Static(_PHASE_LABEL["pending"]("plan"),  id="phase-plan",  classes="ctx-row")
        yield Static("QUICK REPLY", classes="rail-hdr")
        yield MacroPill("Accept rec",  "yes, looks good — proceed",  shortcut="Alt+1", id="macro-0")
        yield MacroPill("Skip this",   "let's skip this for now",    shortcut="Alt+2", id="macro-1")
        yield MacroPill("Elaborate",   "can you elaborate on that?", shortcut="Alt+3", id="macro-2")
        yield MacroPill("Looks good",  "yes",                        shortcut="Alt+4", id="macro-3")
        yield MacroPill("Add context", "for context: ",              shortcut="Alt+5", id="macro-4")

    def update_context(self, repo: str, branch: str, slug: str) -> None:
        # Labels are 4 chars + 1 space = 5 chars, leaving 15 for the value
        # within the 21-char usable width (24 - right border - 2 padding).
        # Using [:15] rather than [:16] to avoid wrap-at-limit edge cases.
        self.query_one("#ctx-repo").update(
            f"[dim #334155]repo [/][#475569]{escape(repo[:15])}[/]"
        )
        self.query_one("#ctx-branch").update(
            f"[dim #334155]br   [/][#475569]{escape(branch[:15])}[/]"
        )
        self.query_one("#ctx-slug").update(
            f"[dim #334155]feat [/][#475569]{escape(slug[:15])}[/]"
        )

    def set_phase(self, phase: str, status: str) -> None:
        label_fn = _PHASE_LABEL.get(status, _PHASE_LABEL["pending"])
        self.query_one(f"#phase-{phase}").update(label_fn(phase))


# ─────────────────────────────────────────────────────────────────────────────
# Right rail — Working Memory
# ─────────────────────────────────────────────────────────────────────────────

class WMEntry(Static, can_focus=True):
    """
    A single answer entry in the Working Memory panel.

    - Full text (no truncation)
    - Amber highlight for ~3s after creation, then dims to normal
    - Click or Enter to copy text back to the composer
    - Optional Q-tag (Q1, Q2, …) prefix
    """

    class CopyRequested(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    DEFAULT_CSS = """
    WMEntry {
        padding: 0 0;
    }
    WMEntry:hover {
        background: #0c3a4a;
    }
    WMEntry:focus {
        background: #0c2a3a;
    }
    """

    def __init__(self, idx: int, text: str, q_tag: str = "", **kwargs):
        self._idx = idx
        self._full_text = text
        self._q_tag = q_tag
        self._is_new = True
        super().__init__(self._markup(new=True), **kwargs)

    def _markup(self, new: bool) -> str:
        text_color = "#f59e0b" if new else "#e2e8f0"
        tag_color  = "#f59e0b" if new else "#06b6d4"
        tag_part   = f" [dim {tag_color}]{self._q_tag}[/]" if self._q_tag else ""
        return (
            f"[dim #334155]{self._idx:>2}.[/]{tag_part} "
            f"[{text_color}]{escape(self._full_text)}[/]"
        )

    def on_mount(self) -> None:
        self.set_timer(3.0, self._dim)

    def _dim(self) -> None:
        self._is_new = False
        self.update(self._markup(new=False))

    def on_click(self) -> None:
        self.post_message(self.CopyRequested(self._full_text))

    def on_key(self, event) -> None:
        if event.key == "enter":
            self.post_message(self.CopyRequested(self._full_text))
            event.stop()


class WorkingMemoryPanel(Widget):
    """
    Right rail: numbered user answers, extracted facts, phase timeline.

    Sections:
      ANSWERS   — each user reply, numbered, in submission order
      FACTS     — key/value pairs extracted from answers (stack, auth, etc.)
      TIMELINE  — timestamped phase transitions
    """

    DEFAULT_CSS = """
    WorkingMemoryPanel {
        width: 28;
        background: #0d1221;
        border-left: tall #1e293b;
        layout: vertical;
        height: 1fr;
    }
    WorkingMemoryPanel #wm-title {
        height: 1;
        color: #d946ef;
        text-style: bold;
        padding: 0 1;
        background: #0d1221;
        border-bottom: tall #1e293b;
    }
    WorkingMemoryPanel VerticalScroll {
        background: #0d1221;
        border: none;
        padding: 0 1;
    }
    WorkingMemoryPanel .wm-section {
        color: #334155;
        text-style: bold;
        height: 1;
        padding: 0 0;
        margin: 1 0 0 0;
    }
    WorkingMemoryPanel .wm-fact {
        color: #f59e0b;
        padding: 0 0;
        height: 1;
    }
    WorkingMemoryPanel .wm-event {
        color: #475569;
        padding: 0 0;
        height: 1;
    }
    """

    # Simple heuristics for extracting labelled facts from user answers
    _FACT_PATTERNS: list[tuple[str, list[str]]] = [
        ("stack",    ["python", "fastapi", "django", "flask", "node", "express",
                      "rails", "spring", "go", "rust", "react", "vue", "next"]),
        ("db",       ["postgres", "postgresql", "sqlite", "mysql", "mongo",
                      "dynamodb", "redis", "snowflake"]),
        ("auth",     ["jwt", "oauth", "session", "magic link", "passwordless",
                      "api key", "email", "password"]),
        ("infra",    ["docker", "kubernetes", "k8s", "aws", "gcp", "azure",
                      "heroku", "vercel", "prefect"]),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._answer_count = 0
        self._facts: dict[str, str] = {}
        self._pinned: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static("WORKING MEMORY", id="wm-title")
        yield VerticalScroll(id="wm-scroll")

    # ── Public API ────────────────────────────────────────────────────────── #

    def add_answer(self, text: str, q_tag: str = "") -> None:
        """Record a user answer (full text, no truncation) and extract facts."""
        self._answer_count += 1
        idx = self._answer_count
        scroll = self.query_one("#wm-scroll", VerticalScroll)

        # Section header on first answer
        if idx == 1:
            scroll.mount(Static("ANSWERS", classes="wm-section"))

        scroll.mount(WMEntry(idx=idx, text=text, q_tag=q_tag))

        # Extract and surface facts
        self._extract_facts(text, scroll)
        scroll.scroll_end(animate=False)

    def add_timeline(self, event: str) -> None:
        """Add a timestamped phase transition to the timeline."""
        ts = datetime.datetime.now().strftime("%H:%M")
        scroll = self.query_one("#wm-scroll", VerticalScroll)

        # Lazy section header
        if not hasattr(self, "_timeline_started"):
            scroll.mount(Static("TIMELINE", classes="wm-section"))
            self._timeline_started = True

        scroll.mount(
            Static(
                f"[dim #334155]{ts}[/] [#475569]{escape(event)}[/]",
                classes="wm-event",
            )
        )
        scroll.scroll_end(animate=False)

    # ── Internal ──────────────────────────────────────────────────────────── #

    def _extract_facts(self, text: str, scroll: VerticalScroll) -> None:
        lower = text.lower()
        for fact_key, keywords in self._FACT_PATTERNS:
            if fact_key in self._facts:
                continue  # already captured
            matched = next((kw for kw in keywords if kw in lower), None)
            if matched:
                self._facts[fact_key] = matched

                # Lazy FACTS header
                if len(self._facts) == 1:
                    scroll.mount(Static("FACTS", classes="wm-section"))

                scroll.mount(
                    Static(
                        f"[dim #334155]{fact_key:<6}[/] [bold #f59e0b]{matched}[/]",
                        classes="wm-fact",
                    )
                )


# ─────────────────────────────────────────────────────────────────────────────
# Thinking indicator (animated, docked bottom)
# ─────────────────────────────────────────────────────────────────────────────

_THINK_FRAMES = [
    "[#06b6d4] ·  ·  · [/]",
    "[#06b6d4]  · ·   [/]",
    "[#06b6d4]   · ·  [/]",
    "[#06b6d4]  · · · [/]",
    "[#3b82f6] Claude is thinking[/][#06b6d4] ·  [/]",
    "[#3b82f6] Claude is thinking[/][#06b6d4] ·· [/]",
    "[#3b82f6] Claude is thinking[/][#06b6d4] ···[/]",
    "[#3b82f6] Claude is thinking[/][#06b6d4] ·· [/]",
]


class ThinkingIndicator(Static):
    """Animated indicator shown while Claude is generating."""

    DEFAULT_CSS = """
    ThinkingIndicator {
        height: 1;
        background: #0a0e1a;
        padding: 0 2;
        color: #06b6d4;
        display: none;
    }
    """

    _frame: reactive[int] = reactive(0)
    _timer = None

    def watch__frame(self, frame: int) -> None:
        self.update(_THINK_FRAMES[frame % len(_THINK_FRAMES)])

    def show(self) -> None:
        self.display = True
        self._timer = self.set_interval(0.2, self._tick)

    def hide(self) -> None:
        self.display = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _tick(self) -> None:
        self._frame = (self._frame + 1) % len(_THINK_FRAMES)


# ─────────────────────────────────────────────────────────────────────────────
# Composer status strip (above input field)
# ─────────────────────────────────────────────────────────────────────────────

class ComposerStatus(Static):
    """
    Thin strip above the input field showing current question number,
    focus mode, and keyboard hints.
    """

    DEFAULT_CSS = """
    ComposerStatus {
        height: 1;
        background: #0a0e1a;
        color: #334155;
        padding: 0 2;
        border-top: tall #1e293b;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._question = 0
        self._focus_mode = False

    def set_question(self, n: int) -> None:
        self._question = n
        self._refresh()

    def set_focus_mode(self, active: bool) -> None:
        self._focus_mode = active
        self._refresh()

    def _refresh(self) -> None:
        parts = []
        if self._question > 0:
            parts.append(f"[bold #06b6d4]Q{self._question}[/]")
        focus_label = (
            "[bold #d946ef]FOCUS ON[/]" if self._focus_mode
            else "[dim #334155]Focus OFF[/]"
        )
        parts.append(focus_label)
        parts.append("[dim #334155]Shift+Enter  multiline[/]")
        sep = "  [dim #1e293b]│[/]  "
        self.update("  " + sep.join(parts))

    def on_mount(self) -> None:
        self._refresh()


# ─────────────────────────────────────────────────────────────────────────────
# Input field
# ─────────────────────────────────────────────────────────────────────────────

class UserSubmitted(Message):
    """Posted when the user submits a reply."""
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class InputField(Widget):
    """Single-line input with a cyan `>` prompt prefix."""

    DEFAULT_CSS = """
    InputField {
        height: 3;
        layout: horizontal;
        border-top: tall #06b6d4;
        background: #0a0e1a;
        padding: 0 0;
    }
    InputField #prompt-label {
        width: 4;
        height: 3;
        content-align: center middle;
        color: #06b6d4;
        background: #0a0e1a;
        padding: 0 0 0 1;
    }
    InputField Input {
        width: 1fr;
        background: #0a0e1a;
        color: #e2e8f0;
        border: none;
    }
    InputField Input:focus {
        border: none;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("[bold #06b6d4]>[/]", id="prompt-label")
        yield Input(placeholder="Reply to Claude…")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            event.input.clear()
            self.post_message(UserSubmitted(text))

    def set_value(self, text: str) -> None:
        """Pre-fill without submitting (macros, keyboard shortcuts)."""
        inp = self.query_one(Input)
        inp.value = text
        inp.focus()
        inp.cursor_position = len(text)

    def show(self) -> None:
        self.display = True
        self.query_one(Input).focus()

    def hide(self) -> None:
        self.display = False


# ─────────────────────────────────────────────────────────────────────────────
# Multiline draft modal
# ─────────────────────────────────────────────────────────────────────────────

class MultilineDraft(ModalScreen):
    """
    Full-screen modal for composing multi-line messages.
    Ctrl+Enter submits, Escape cancels.
    Result is the text string (or None if cancelled).
    """

    BINDINGS = [
        ("ctrl+enter", "submit",  "Send"),
        ("escape",     "cancel",  "Cancel"),
    ]

    DEFAULT_CSS = """
    MultilineDraft {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }
    MultilineDraft #draft-panel {
        width: 70%;
        height: 55%;
        background: #0d1221;
        border: tall #06b6d4;
        padding: 1 2;
    }
    MultilineDraft #draft-title {
        height: 1;
        color: #06b6d4;
        text-style: bold;
        margin: 0 0 1 0;
    }
    MultilineDraft TextArea {
        height: 1fr;
        background: #0a0e1a;
        color: #e2e8f0;
        border: tall #1e293b;
    }
    MultilineDraft #draft-hint {
        height: 1;
        color: #334155;
        margin: 1 0 0 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="draft-panel"):
            yield Static(
                "[bold #06b6d4]Compose[/]  "
                "[dim #334155]Ctrl+Enter  send  │  Escape  cancel[/]",
                id="draft-title",
            )
            yield TextArea(id="draft-area")
            yield Static(
                "[dim #334155]Tip: paste multi-line content freely, then Ctrl+Enter to send.[/]",
                id="draft-hint",
            )

    def on_mount(self) -> None:
        self.query_one(TextArea).focus()

    def action_submit(self) -> None:
        text = self.query_one(TextArea).text.strip()
        if text:
            self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────────────────────────────────────────
# Status bar (bottom)
# ─────────────────────────────────────────────────────────────────────────────

class StatusBar(Static):
    """Bottom bar: git branch, model name, mode indicator, keyboard hints."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        background: #0d1221;
        color: #334155;
        padding: 0 2;
        border-top: tall #1e293b;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._branch = ""
        self._model = ""
        self._focus_mode = False

    def set_branch(self, branch: str) -> None:
        self._branch = branch
        self._refresh()

    def set_model(self, model: str) -> None:
        self._model = model
        self._refresh()

    def set_focus_mode(self, active: bool) -> None:
        self._focus_mode = active
        self._refresh()

    def _refresh(self) -> None:
        parts = []
        if self._branch:
            parts.append(f"[#06b6d4]⎇ {self._branch}[/]")
        if self._model:
            parts.append(f"[dim #475569]{self._model}[/]")
        if self._focus_mode:
            parts.append("[bold #d946ef]FOCUS[/]")
        parts.append("[dim #334155]Ctrl+K[/] [dim #475569]commands[/]")
        parts.append("[dim #334155]Ctrl+F[/] [dim #475569]focus[/]")
        parts.append("[dim #334155]Ctrl+Q[/] [dim #475569]quit[/]")
        sep = "  [dim #1e293b]│[/]  "
        self.update("  " + sep.join(parts))

    def on_mount(self) -> None:
        self._refresh()
