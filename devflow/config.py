"""
Config — replaces hardcoded C:\\Users\\PaulRussell\\... paths in the bash ai script.
All settings are overridable via environment variables so every engineer can use
the same codebase without editing source files.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # Anthropic API
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("DEVFLOW_MODEL", "claude-sonnet-4-6"))

    # File system roots
    notes_root: Path = field(
        default_factory=lambda: Path(
            os.environ.get("DEVFLOW_NOTES_ROOT", Path.home() / "Documents" / "ai-dev-flow")
        )
    )
    skill_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("DEVFLOW_SKILL_DIR", Path.home() / "ai-dev-flow" / "skills")
        )
    )
    lib_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("DEVFLOW_LIB_DIR", Path.home() / "ai-dev-flow" / "lib")
        )
    )

    # Paperclip orchestration (all optional — absent = degraded/local-only mode)
    paperclip_url: str = field(
        default_factory=lambda: os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")
    )
    paperclip_key: str = field(
        default_factory=lambda: os.environ.get("PAPERCLIP_API_KEY", "")
    )
    paperclip_run_id: str = field(
        default_factory=lambda: os.environ.get("PAPERCLIP_RUN_ID", "")
    )
    paperclip_company_id: str = field(
        default_factory=lambda: os.environ.get("PAPERCLIP_COMPANY_ID", "")
    )
    paperclip_agent_id: str = field(
        default_factory=lambda: os.environ.get("PAPERCLIP_AGENT_ID", "")
    )

    @property
    def paperclip_enabled(self) -> bool:
        """
        True when Paperclip integration is configured.
        In local_trusted mode Paperclip injects PAPERCLIP_COMPANY_ID but no
        API key — treat that as enabled too.
        """
        return bool(self.paperclip_key or self.paperclip_company_id)

    def validate(self) -> list[str]:
        """Return a list of error strings. Empty = config is valid."""
        errors = []
        if not self.api_key:
            errors.append(
                "ANTHROPIC_API_KEY is not set — export ANTHROPIC_API_KEY=sk-ant-..."
            )
        if not self.skill_dir.exists():
            errors.append(f"Skill directory not found: {self.skill_dir}")
        return errors

    def feature_notes_dir(self, repo_name: str, branch: str, slug: str) -> Path:
        """Return the notes directory for a specific feature."""
        return self.notes_root / repo_name / branch / "features" / slug
