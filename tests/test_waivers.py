"""
Tests for devflow/waivers.py — GATE-WAIVER parse + validate.
"""
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from devflow.waivers import (
    WAIVABLE_GATES,
    NON_WAIVABLE_GATES,
    find_active_waiver,
    load_authority_list,
    parse_gate_waivers,
    validate_waiver,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FUTURE = (date.today() + timedelta(days=30)).isoformat()
PAST   = (date.today() - timedelta(days=1)).isoformat()
TODAY  = date.today()


def _comment(body: str, agent_id: str = "", author_id: str = "paulrussell") -> dict:
    return {"id": "c1", "body": body, "agentId": agent_id or None, "authorId": author_id}


def _waiver_body(gate="security-severity", approved_by="paulrussell", expires=None, reason="test reason") -> str:
    return (
        f"GATE-WAIVER\n"
        f"gate: {gate}\n"
        f"reason: {reason}\n"
        f"approved-by: {approved_by}\n"
        f"expires: {expires or FUTURE}"
    )


# ---------------------------------------------------------------------------
# parse_gate_waivers
# ---------------------------------------------------------------------------

class TestParseGateWaivers:
    def test_parses_valid_block(self):
        comments = [_comment(_waiver_body())]
        result = parse_gate_waivers(comments)
        assert len(result) == 1
        assert result[0]["gate"] == "security-severity"
        assert result[0]["approved_by"] == "paulrussell"
        assert result[0]["expires"] == FUTURE
        assert result[0]["reason"] == "test reason"
        assert result[0]["is_agent"] is False
        assert result[0]["posted_by"] == "paulrussell"

    def test_skips_comment_without_gate_waiver_keyword(self):
        comments = [_comment("This is a normal comment")]
        assert parse_gate_waivers(comments) == []

    def test_skips_block_missing_required_fields(self):
        # Missing approved-by
        body = "GATE-WAIVER\ngate: security-severity\nexpires: " + FUTURE
        assert parse_gate_waivers([_comment(body)]) == []

    def test_skips_block_missing_expires(self):
        body = "GATE-WAIVER\ngate: security-severity\napproved-by: paulrussell"
        assert parse_gate_waivers([_comment(body)]) == []

    def test_marks_agent_posted_comment(self):
        comments = [_comment(_waiver_body(), agent_id="agent-123")]
        result = parse_gate_waivers(comments)
        assert result[0]["is_agent"] is True

    def test_parses_multiple_waivers(self):
        comments = [
            _comment(_waiver_body("security-severity")),
            _comment(_waiver_body("coverage-threshold")),
        ]
        result = parse_gate_waivers(comments)
        assert len(result) == 2
        assert {r["gate"] for r in result} == {"security-severity", "coverage-threshold"}

    def test_ignores_comment_with_no_gate_waiver(self):
        comments = [
            _comment("No waiver here"),
            _comment(_waiver_body()),
        ]
        assert len(parse_gate_waivers(comments)) == 1

    def test_case_insensitive_fields(self):
        body = (
            "GATE-WAIVER\n"
            "Gate: security-severity\n"
            "Approved-By: paulrussell\n"
            f"Expires: {FUTURE}\n"
            "Reason: test\n"
        )
        result = parse_gate_waivers([_comment(body)])
        assert len(result) == 1
        assert result[0]["gate"] == "security-severity"


# ---------------------------------------------------------------------------
# validate_waiver
# ---------------------------------------------------------------------------

class TestValidateWaiver:
    def _base(self, **overrides) -> dict:
        base = {
            "gate": "security-severity",
            "reason": "test",
            "approved_by": "paulrussell",
            "expires": FUTURE,
            "is_agent": False,
            "comment_id": "c1",
            "posted_by": "paulrussell",
        }
        base.update(overrides)
        return base

    def test_valid_waiver_with_authority_list(self):
        ok, msg = validate_waiver(self._base(), ["paulrussell"])
        assert ok is True
        assert msg == "valid"

    def test_valid_waiver_permissive_empty_authority(self):
        ok, _ = validate_waiver(self._base(), [])
        assert ok is True

    def test_rejects_non_waivable_gate(self):
        ok, msg = validate_waiver(self._base(gate="iron-law"), [])
        assert ok is False
        assert "not waivable" in msg

    def test_rejects_agent_posted_waiver(self):
        ok, msg = validate_waiver(self._base(is_agent=True), [])
        assert ok is False
        assert "agent" in msg

    def test_rejects_unauthorised_approver(self):
        ok, msg = validate_waiver(self._base(approved_by="unknown"), ["paulrussell"])
        assert ok is False
        assert "not in the waiver_authority list" in msg

    def test_rejects_expired_waiver(self):
        ok, msg = validate_waiver(self._base(expires=PAST), [])
        assert ok is False
        assert "expired" in msg

    def test_rejects_invalid_date_format(self):
        ok, msg = validate_waiver(self._base(expires="not-a-date"), [])
        assert ok is False
        assert "valid YYYY-MM-DD" in msg

    def test_accepts_waiver_expiring_today(self):
        ok, _ = validate_waiver(self._base(expires=TODAY.isoformat()), [], now=TODAY)
        # expires < now → rejected; expires == now → accepted (not strictly less)
        assert ok is True

    def test_rejects_waiver_expired_yesterday(self):
        yesterday = (TODAY - timedelta(days=1)).isoformat()
        ok, _ = validate_waiver(self._base(expires=yesterday), [], now=TODAY)
        assert ok is False

    def test_all_waivable_gates_accepted(self):
        for gate in WAIVABLE_GATES:
            ok, _ = validate_waiver(self._base(gate=gate), [])
            assert ok is True, f"Expected {gate} to be waivable"

    def test_non_waivable_gates_rejected(self):
        for gate in NON_WAIVABLE_GATES:
            ok, _ = validate_waiver(self._base(gate=gate), [])
            assert ok is False, f"Expected {gate} to be non-waivable"


# ---------------------------------------------------------------------------
# find_active_waiver
# ---------------------------------------------------------------------------

class TestFindActiveWaiver:
    def _w(self, gate="security-severity", approved_by="paulrussell", expires=None, is_agent=False):
        return {
            "gate": gate,
            "reason": "test",
            "approved_by": approved_by,
            "expires": expires or FUTURE,
            "is_agent": is_agent,
            "comment_id": "c1",
            "posted_by": approved_by,
        }

    def test_finds_matching_valid_waiver(self):
        waivers = [self._w()]
        result = find_active_waiver(waivers, "security-severity", [])
        assert result is not None
        assert result["gate"] == "security-severity"

    def test_returns_none_when_no_waivers(self):
        assert find_active_waiver([], "security-severity", []) is None

    def test_returns_none_when_gate_does_not_match(self):
        waivers = [self._w(gate="coverage-threshold")]
        assert find_active_waiver(waivers, "security-severity", []) is None

    def test_returns_none_when_waiver_invalid(self):
        waivers = [self._w(expires=PAST)]  # expired
        assert find_active_waiver(waivers, "security-severity", []) is None

    def test_returns_first_valid_when_multiple(self):
        waivers = [
            self._w(expires=PAST),                # expired — skip
            self._w(approved_by="alice"),          # valid
        ]
        result = find_active_waiver(waivers, "security-severity", [])
        assert result["approved_by"] == "alice"

    def test_authority_filter_applied(self):
        waivers = [self._w(approved_by="unauthorised")]
        assert find_active_waiver(waivers, "security-severity", ["paulrussell"]) is None


# ---------------------------------------------------------------------------
# load_authority_list
# ---------------------------------------------------------------------------

class TestLoadAuthorityList:
    def test_returns_empty_when_no_file(self):
        assert load_authority_list(None) == []
        assert load_authority_list(Path("/nonexistent/devflow.yaml")) == []

    def test_returns_empty_when_governance_absent(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("project:\n  name: test\n")
            path = Path(f.name)
        try:
            assert load_authority_list(path) == []
        finally:
            path.unlink(missing_ok=True)

    def test_reads_authority_list(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write("governance:\n  waiver_authority:\n    - paulrussell\n    - teamlead\n")
            path = Path(f.name)
        try:
            result = load_authority_list(path)
            assert result == ["paulrussell", "teamlead"]
        finally:
            path.unlink(missing_ok=True)

    def test_returns_empty_on_invalid_yaml(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            f.write(": invalid: yaml: {{{\n")
            path = Path(f.name)
        try:
            assert load_authority_list(path) == []
        finally:
            path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Integration: deploy gate uses comment waivers
# ---------------------------------------------------------------------------

class TestDeployGateWithWaivers:
    """Verify gate_phase('deploy') respects comment-based waivers."""

    def test_deploy_gate_passes_with_comment_waiver(self, tmp_path):
        from devflow.gatekeeper import gate_phase

        # Create qa/evidence.md so the artifact check doesn't also fail
        (tmp_path / "qa").mkdir()
        (tmp_path / "qa" / "evidence.md").write_text("## Test Output\n")

        state = {"max_severity": "high"}
        waivers = [{
            "gate": "security-severity",
            "reason": "approved",
            "approved_by": "paulrussell",
            "expires": FUTURE,
            "is_agent": False,
            "comment_id": "c1",
            "posted_by": "paulrussell",
        }]

        result = gate_phase("deploy", tmp_path, state, waivers=waivers)
        # Should pass severity check (waiver present)
        sev_failures = [f for f in result.failures if "max_severity" in f]
        assert sev_failures == []

    def test_deploy_gate_blocks_without_waiver(self, tmp_path):
        from devflow.gatekeeper import gate_phase

        (tmp_path / "qa").mkdir()
        (tmp_path / "qa" / "evidence.md").write_text("## Test Output\n")

        state = {"max_severity": "high"}
        result = gate_phase("deploy", tmp_path, state, waivers=[])
        sev_failures = [f for f in result.failures if "max_severity" in f]
        assert sev_failures  # should be blocked
