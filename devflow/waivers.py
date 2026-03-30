"""
devflow waivers — parse and validate GATE-WAIVER comment blocks.

Pure module: no Paperclip dependency. The CLI layer fetches raw comment
dicts and passes them here; gatekeeper receives already-validated waivers.

GATE-WAIVER comment format (must appear verbatim in a Paperclip comment):

    GATE-WAIVER
    gate: security-severity
    reason: External pentest scheduled for next sprint; findings tracked in ANA-99.
    approved-by: paulrussell
    expires: 2026-06-01

Fields:
    gate        : gate name (see WAIVABLE_GATES)
    reason      : free text — required for audit trail
    approved-by : Paperclip username of the authorising human
    expires     : YYYY-MM-DD — waivers do not auto-renew

Validation rules (all must pass):
    1. gate is in WAIVABLE_GATES
    2. comment was posted by a human (not an agent)
    3. approved-by is in devflow.yaml governance.waiver_authority
       (or authority list is empty → permissive default)
    4. expires is a valid date that has not passed
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Gate name constants
# ---------------------------------------------------------------------------

WAIVABLE_GATES = frozenset({
    "security-severity",    # deploy gate: max_severity = high
    "coverage-threshold",   # qa seal: coverage_pct below threshold
    "mermaid-diagrams",     # plan seal: diagram count / syntax failure
})

# For documentation — enforced by gatekeeper, not this module
NON_WAIVABLE_GATES = frozenset({
    "iron-law",                    # test output missing / regex not matched
    "artifact-contract",           # required artifact absent
    "reviewer-fail",               # review Decision = FAIL
    "security-severity-critical",  # max_severity = critical
})


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_gate_waivers(comments: list[dict]) -> list[dict]:
    """
    Extract GATE-WAIVER blocks from a list of Paperclip comment dicts.

    Each comment dict is expected to contain at minimum:
        body     : str         — comment text
        id       : str         — comment UUID
        agentId  : str | None  — set when posted by an agent, absent for humans
        authorId : str | None  — poster's user / agent identifier

    Returns a list of waiver dicts (not yet validated against authority or
    expiry — call validate_waiver() or find_active_waiver() for that):
        gate         : str
        reason       : str
        approved_by  : str
        expires      : str  (raw YYYY-MM-DD string from the comment)
        comment_id   : str
        posted_by    : str
        is_agent     : bool
    """
    results: list[dict] = []
    for comment in comments:
        body = comment.get("body") or ""
        if "GATE-WAIVER" not in body:
            continue
        parsed = _parse_waiver_block(body)
        if parsed is None:
            continue
        parsed["comment_id"] = comment.get("id") or ""
        parsed["posted_by"] = (
            comment.get("authorId")
            or comment.get("userId")
            or ""
        )
        parsed["is_agent"] = bool(comment.get("agentId"))
        results.append(parsed)
    return results


def _parse_waiver_block(text: str) -> Optional[dict]:
    """
    Parse a single GATE-WAIVER block from a comment body string.
    Returns None if any required field (gate, approved-by, expires) is absent.
    """
    def _field(name: str) -> Optional[str]:
        m = re.search(
            rf"^{re.escape(name)}\s*:\s*(.+)$",
            text,
            re.IGNORECASE | re.MULTILINE,
        )
        return m.group(1).strip() if m else None

    gate = _field("gate")
    approved_by = _field("approved-by")
    expires = _field("expires")

    if not gate or not approved_by or not expires:
        return None

    return {
        "gate": gate.lower(),
        "reason": _field("reason") or "",
        "approved_by": approved_by,
        "expires": expires,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_waiver(
    waiver: dict,
    authority_list: list[str],
    now: Optional[date] = None,
) -> tuple[bool, str]:
    """
    Validate a parsed waiver dict.

    Returns (valid: bool, reason: str).

    Parameters
    ----------
    waiver         : dict returned by parse_gate_waivers()
    authority_list : list of approved usernames from devflow.yaml
                     governance.waiver_authority; empty list = permissive
    now            : override today's date (for testing)
    """
    if now is None:
        now = datetime.now(timezone.utc).date()

    gate = waiver.get("gate", "")
    if gate not in WAIVABLE_GATES:
        return False, f"gate '{gate}' is not waivable (non-waivable or unknown)"

    if waiver.get("is_agent"):
        return False, "waiver was posted by an agent — only human posts are accepted"

    approved_by = waiver.get("approved_by", "")
    if authority_list and approved_by not in authority_list:
        return False, (
            f"approved-by '{approved_by}' is not in the waiver_authority list "
            f"({', '.join(authority_list)})"
        )

    expires_str = waiver.get("expires", "")
    try:
        expires_date = date.fromisoformat(expires_str)
    except (ValueError, TypeError):
        return False, f"expires '{expires_str}' is not a valid YYYY-MM-DD date"

    if expires_date < now:
        return False, f"waiver expired on {expires_str}"

    return True, "valid"


def find_active_waiver(
    waivers: list[dict],
    gate: str,
    authority_list: list[str],
    now: Optional[date] = None,
) -> Optional[dict]:
    """
    Return the first valid, non-expired waiver for ``gate``, or None.

    ``waivers`` is the raw parsed list from parse_gate_waivers().
    Validation (authority + expiry) is applied internally.
    """
    for w in waivers:
        if w.get("gate") != gate:
            continue
        ok, _ = validate_waiver(w, authority_list, now)
        if ok:
            return w
    return None


# ---------------------------------------------------------------------------
# devflow.yaml governance config reader
# ---------------------------------------------------------------------------

def load_authority_list(devflow_yaml_path: Optional[Path]) -> list[str]:
    """
    Read governance.waiver_authority from devflow.yaml.

    Returns an empty list (permissive default — any human may waive) if:
    - devflow.yaml is absent
    - governance.waiver_authority key is not present
    - yaml library is unavailable
    """
    if devflow_yaml_path is None or not devflow_yaml_path.exists():
        return []
    try:
        import yaml  # PyYAML — optional; falls back to permissive if absent
        data = yaml.safe_load(devflow_yaml_path.read_text(encoding="utf-8")) or {}
        authority = data.get("governance", {}).get("waiver_authority", [])
        if isinstance(authority, list):
            return [str(a) for a in authority]
        return []
    except Exception:
        return []
