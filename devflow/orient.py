"""
devflow orient — session context health check.

Runs proxy-signal checks before each heartbeat to detect stale context,
long sessions, fix-break-fix loops, and model tier issues.

The 40% context-utilisation threshold from ALDC guidelines is advisory only
(not measurable from outside the model). These proxy signals are the
enforceable equivalent.

Exit codes
----------
0  OK — proceed
1  Hard block — cancellation or critical state conflict
2  Warning — stale session, model tier, unread comments — proceed with logged warnings
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from devflow.config import Config
    from devflow.paperclip import PaperclipClient


# ---------------------------------------------------------------------------
# Thresholds (can be overridden via devflow.yaml governance.ceo_thresholds)
# ---------------------------------------------------------------------------

STALE_SESSION_MINUTES = int(os.environ.get("DEVFLOW_ORIENT_STALE_MINUTES", "30"))
MAX_HEARTBEATS_PER_PHASE = int(os.environ.get("DEVFLOW_ORIENT_MAX_HEARTBEATS", "10"))
MAX_SEAL_FAILURES = int(os.environ.get("DEVFLOW_ORIENT_MAX_SEAL_FAILURES", "3"))

# Required tools and which check they belong to
_REQUIRED_TOOLS = ["git", "python"]
_OPTIONAL_TOOLS = ["pytest", "coverage", "mmdc", "nyc"]


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class OrientResult:
    exit_code: int                      # 0=OK, 1=hard block, 2=warning
    hard_block_reason: str = ""         # set when exit_code == 1
    warnings: list[str] = field(default_factory=list)
    tool_check: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def blocked(self) -> bool:
        return self.exit_code == 1


# ---------------------------------------------------------------------------
# Core orient logic
# ---------------------------------------------------------------------------

async def run_orient(
    pc: "PaperclipClient",
    issue_id: str,
    agent_name: str,
) -> OrientResult:
    """
    Run all orient proxy-signal checks for the given issue and agent.
    Returns an OrientResult with exit_code + warnings.
    """
    warnings: list[str] = []

    # ── 1. Fetch issue ────────────────────────────────────────────────────────
    try:
        issue = await pc.get_issue(issue_id)
    except Exception as exc:
        return OrientResult(
            exit_code=1,
            hard_block_reason=f"Could not fetch issue {issue_id}: {exc}",
        )

    # ── 2. Fetch state document ───────────────────────────────────────────────
    state = await pc.load_state(issue_id)

    # ── 3. Cancellation / reassignment check (hard block) ────────────────────
    if issue.status in ("cancelled", "completed", "done"):
        return OrientResult(
            exit_code=1,
            hard_block_reason=(
                f"Issue {issue.identifier} is {issue.status}. "
                "This agent should not be working on a closed issue."
            ),
        )

    agent_id = await _resolve_agent_id(pc, agent_name)
    if agent_id and issue.assignee_id and issue.assignee_id != agent_id:
        return OrientResult(
            exit_code=1,
            hard_block_reason=(
                f"Issue {issue.identifier} is assigned to a different agent "
                f"({issue.assignee_id}). Hard block — do not proceed."
            ),
        )

    # ── 4. Session age check ──────────────────────────────────────────────────
    last_heartbeat_start = state.get("last_heartbeat_start")
    current_phase = state.get("phase", "")
    if last_heartbeat_start and current_phase:
        try:
            last_dt = datetime.fromisoformat(last_heartbeat_start)
            now = datetime.now(timezone.utc)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            gap_minutes = (now - last_dt).total_seconds() / 60
            if gap_minutes > STALE_SESSION_MINUTES:
                warnings.append(
                    f"Context may be stale — last heartbeat was {gap_minutes:.0f} min ago "
                    f"(threshold: {STALE_SESSION_MINUTES} min). "
                    "Read the state document before continuing."
                )
        except (ValueError, TypeError):
            pass

    # ── 5. Heartbeat count check ──────────────────────────────────────────────
    heartbeat_count = state.get("heartbeat_count", 0)
    if isinstance(heartbeat_count, int) and heartbeat_count > MAX_HEARTBEATS_PER_PHASE:
        warnings.append(
            f"Long session detected — {heartbeat_count} heartbeats in current phase "
            f"(threshold: {MAX_HEARTBEATS_PER_PHASE}). "
            "Consider summarising progress and starting a fresh context."
        )

    # ── 6. Fix-break-fix (seal failure count) check ───────────────────────────
    seal_failures = state.get("seal_failures", 0)
    if isinstance(seal_failures, int) and seal_failures > MAX_SEAL_FAILURES:
        warnings.append(
            f"Fix-break-fix pattern detected — {seal_failures} seal failures in current phase "
            f"(threshold: {MAX_SEAL_FAILURES}). "
            "Strongly recommend starting a fresh context. CEO will be notified."
        )

    # ── 7. Unread comments check ──────────────────────────────────────────────
    last_read_id = state.get("last_read_comment_id")
    try:
        comments = await pc.list_comments(issue_id)
        if comments:
            if last_read_id is None:
                unread = len(comments)
            else:
                ids = [c.get("id") for c in comments]
                try:
                    idx = ids.index(last_read_id)
                    unread = len(comments) - idx - 1
                except ValueError:
                    unread = len(comments)
            if unread > 0:
                warnings.append(
                    f"{unread} unread comment(s) on {issue.identifier}. "
                    "Read comments before proceeding — they may contain updated requirements or escalations."
                )
    except Exception:
        pass

    # ── 8. Model tier check ───────────────────────────────────────────────────
    model_tier = state.get("model_tier", "")
    model_tier_justification = state.get("model_tier_justification", "")
    if model_tier.lower() == "opus" and not model_tier_justification:
        warnings.append(
            "Opus model tier declared without justification. "
            "Add model_tier_justification to the state document before proceeding. "
            "See docs/artifact-contract.md §WS14."
        )

    # ── 9. Tool availability check (run once per orient, non-blocking for optional) ──
    tool_check = _check_tools()
    missing_required = [t for t, ok in tool_check.items() if not ok and t in _REQUIRED_TOOLS]
    missing_optional = [t for t, ok in tool_check.items() if not ok and t in _OPTIONAL_TOOLS]

    if missing_required:
        return OrientResult(
            exit_code=1,
            hard_block_reason=(
                f"Required tools missing: {', '.join(missing_required)}. "
                "Install them before proceeding."
            ),
            warnings=warnings,
            tool_check=tool_check,
        )

    if missing_optional:
        warnings.append(
            f"Optional tools not found: {', '.join(missing_optional)}. "
            "Seal will skip those validations with a warning."
        )

    exit_code = 2 if warnings else 0
    return OrientResult(
        exit_code=exit_code,
        warnings=warnings,
        tool_check=tool_check,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_agent_id(pc: "PaperclipClient", agent_name: str) -> Optional[str]:
    """
    Return the agent ID for the given name, or None if it cannot be resolved.
    Used to verify the current agent is still the assignee.
    """
    try:
        agent = await pc.get_agent()
        return agent.id
    except Exception:
        return None


def _check_tools() -> dict[str, bool]:
    """Return a dict of tool_name → available (bool)."""
    import shutil
    result: dict[str, bool] = {}
    for tool in _REQUIRED_TOOLS + _OPTIONAL_TOOLS:
        result[tool] = shutil.which(tool) is not None
    return result
