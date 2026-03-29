"""
Session — persists multi-turn conversation history to disk.

A session lives at: <notes_dir>/session.json
It stores the Anthropic MessageParam list so a conversation can be resumed
after the TUI is closed or a network error occurs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Session:
    slug: str
    notes_dir: Path
    messages: list[dict] = field(default_factory=list)
    complete: bool = False

    # ------------------------------------------------------------------ #
    # Message helpers                                                       #
    # ------------------------------------------------------------------ #

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self.messages.append({"role": "assistant", "content": text})

    def last_assistant_text(self) -> str:
        """Return the most recent assistant message text, or ''."""
        for msg in reversed(self.messages):
            if msg["role"] == "assistant":
                content = msg["content"]
                if isinstance(content, str):
                    return content
                # Handle block format
                return "".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
        return ""

    # ------------------------------------------------------------------ #
    # Persistence                                                           #
    # ------------------------------------------------------------------ #

    @property
    def _path(self) -> Path:
        return self.notes_dir / "session.json"

    def save(self) -> None:
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "slug": self.slug,
            "complete": self.complete,
            "messages": self.messages,
        }
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, slug: str, notes_dir: Path) -> "Session":
        """Load existing session from disk."""
        path = notes_dir / "session.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            slug=data["slug"],
            notes_dir=notes_dir,
            messages=data.get("messages", []),
            complete=data.get("complete", False),
        )

    @classmethod
    def load_or_create(cls, slug: str, notes_dir: Path) -> "Session":
        """Load from disk if a session exists, otherwise start fresh."""
        if (notes_dir / "session.json").exists():
            return cls.load(slug, notes_dir)
        return cls(slug=slug, notes_dir=notes_dir)

    def reset(self) -> None:
        """Clear conversation history and completion flag."""
        self.messages = []
        self.complete = False
        if self._path.exists():
            self._path.unlink()
