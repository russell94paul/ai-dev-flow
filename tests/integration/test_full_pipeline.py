"""
Integration tests — full gate→seal pipeline (success + failure paths).

These tests exercise devflow/gatekeeper.py and devflow/artifact_publisher.py
end-to-end against a real filesystem (tmp_path) with no Paperclip network I/O.
The PaperclipClient is injected as a mock where needed.

Coverage matrix (matches docs/aldc-integration-plan-v0.7.md §16):
  ✓ Full happy-path pipeline (gate→seal all 9 phases)
  ✓ Missing PRD artifact → plan gate blocks
  ✓ Iron Law not met → build seal fails
  ✓ Coverage below threshold → qa seal fails; waiver passes
  ✓ Security severity high → deploy gate blocks; comment waiver passes
  ✓ Review FAIL → qa gate blocks
  ✓ Artifact upload conflict (409) → publisher retries; succeeds
  ✓ Persistent upload failure → publisher posts blocking comment; result.success=False
  ✓ Waiver from agent (not human) → waiver rejected; gate remains blocked
  ✓ Waiver expired → waiver ignored; gate remains blocked
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from devflow.gatekeeper import gate_phase, seal_phase
from devflow.artifact_publisher import publish_artifacts


# ---------------------------------------------------------------------------
# Shared artifact content helpers
# ---------------------------------------------------------------------------

FUTURE = (date.today() + timedelta(days=30)).isoformat()
PAST   = (date.today() - timedelta(days=1)).isoformat()


def _write(base: Path, rel: str, content: str) -> Path:
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _prd() -> str:
    return (
        "## Goal\nShip the feature.\n\n"
        "## Background\nContext.\n\n"
        "## Scope\nIn scope: X. Out of scope: Y.\n\n"
        "## Acceptance Criteria\n1. It works.\n\n"
        "## Security Scope\nNo security review triggered.\n"
    )


def _plan() -> str:
    return (
        "## Phases\n1. Tracer bullet.\n2. Full impl.\n\n"
        "## ADRs\nN/A — no architectural decisions.\n\n"
        "## Rollback\n`git revert HEAD`\n\n"
        "## Verification Commands\n`pytest`\n\n"
        "## Diagrams — N/A\nNo diagrams required for this feature.\n"
    )


def _tdd_summary_passing() -> str:
    return "## Test Output\n```\n47 passed in 1.23s\n```\n"


def _tdd_summary_failing() -> str:
    # Deliberately no Iron Law regex match ("passed" appears but not as \d+ passed)
    return "## Test Output\n```\nERROR: all tests failed\nFAILED src/foo.py::test_bar\n```\n"


def _review_report_pass() -> str:
    return (
        "## Checklist\n| Item | Status |\n|---|---|\n| Iron Law | PASS |\n\n"
        "**Decision:** PASS\n"
    )


def _review_report_fail() -> str:
    return (
        "## Checklist\n| Item | Status |\n|---|---|\n| Iron Law | FAIL |\n\n"
        "**Decision:** FAIL\n\n"
        "## Findings\n- `src/foo.py:42` — cognitive debt\n"
    )


def _evidence(coverage_pct: float = 75.0, tier: int = 2) -> str:
    return (
        f"**Tier:** {tier}\n"
        f"**coverage_pct:** {coverage_pct}\n\n"
        "## Test Output\n```\n47 passed in 1.23s\n```\n"
    )


def _security_review(max_severity: str = "low") -> str:
    return f"**max_severity:** {max_severity}\n**sign_off:** devflow-qa-agent\n"


def _deploy_steps() -> str:
    return (
        "## Steps\n1. `helm upgrade app ./chart`\n\n"
        "## Rollback\n`helm rollback app 0`\n\n"
        "## Health Checks\n`curl -f https://app/healthz`\n"
    )


def _manifest(feature_dir: Path) -> dict:
    p = feature_dir / "ops" / "verification-manifest.json"
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# Full happy-path pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """
    Gate → Seal for every phase in order.
    Simulates the state accumulated by the CLI (prd_complete, plan_approved,
    review_passed) that would normally be set by the agent/human layer.
    """

    def test_all_phases_pass(self, tmp_path):
        d = tmp_path
        state: dict = {}

        # ── grill ──────────────────────────────────────────────────────────
        state["grill_complete"] = True
        r = seal_phase("grill", "slug", "issue-1", d, state)
        assert r.passed, r.failures

        # ── prd ────────────────────────────────────────────────────────────
        assert gate_phase("prd", d, state).passed
        _write(d, "specs/prd.md", _prd())
        r = seal_phase("prd", "slug", "issue-1", d, state)
        assert r.passed, r.failures
        state["prd_complete"] = True            # CLI sets this after PRD skill

        # ── plan ───────────────────────────────────────────────────────────
        assert gate_phase("plan", d, state).passed
        _write(d, "plans/plan.md", _plan())
        r = seal_phase("plan", "slug", "issue-1", d, state)
        assert r.passed, r.failures
        state["plan_approved"] = True           # human approval

        # ── build ──────────────────────────────────────────────────────────
        assert gate_phase("build", d, state).passed
        _write(d, "build/tdd-summary.md", _tdd_summary_passing())
        r = seal_phase("build", "slug", "issue-1", d, state)
        assert r.passed, r.failures
        state.update(r.state_updates)           # iron_law_met = True

        # ── review ─────────────────────────────────────────────────────────
        assert gate_phase("review", d, state).passed
        _write(d, "ops/review-report.md", _review_report_pass())
        r = seal_phase("review", "slug", "issue-1", d, state)
        assert r.passed, r.failures
        state["review_passed"] = True           # CLI sets after Decision=PASS

        # ── qa ─────────────────────────────────────────────────────────────
        assert gate_phase("qa", d, state).passed
        _write(d, "qa/evidence.md", _evidence())
        r = seal_phase("qa", "slug", "issue-1", d, state)
        assert r.passed, r.failures

        # ── security ───────────────────────────────────────────────────────
        _write(d, "qa/security-review.md", _security_review("low"))
        r = seal_phase("security", "slug", "issue-1", d, state)
        assert r.passed, r.failures
        state.update(r.state_updates)           # max_severity = "low"

        # ── deploy ─────────────────────────────────────────────────────────
        assert gate_phase("deploy", d, state).passed
        _write(d, "ops/deploy-steps.md", _deploy_steps())
        r = seal_phase("deploy", "slug", "issue-1", d, state)
        assert r.passed, r.failures

        # ── done ───────────────────────────────────────────────────────────
        r = seal_phase("done", "slug", "issue-1", d, state)
        assert r.passed, r.failures
        assert r.state_updates.get("artifact_contract_met") is True
        state.update(r.state_updates)

        assert gate_phase("done", d, state).passed

        # ── manifest assertions ────────────────────────────────────────────
        m = _manifest(d)
        assert m["artifact_contract_met"] is True
        assert m["schema_version"] == "v3"
        assert "build" in m["phases"]
        assert m["phases"]["build"]["thresholds"]["iron_law_met"] is True
        assert m["phases"]["security"]["thresholds"]["max_severity"] == "low"


# ---------------------------------------------------------------------------
# Gate failure paths — missing state / artifacts
# ---------------------------------------------------------------------------

class TestGateFailurePaths:

    def test_plan_gate_blocks_when_prd_missing(self, tmp_path):
        """Plan gate blocks when specs/prd.md is absent (even with prd_complete set)."""
        state = {"grill_complete": True, "prd_complete": True}
        # No prd.md written
        r = gate_phase("plan", tmp_path, state)
        assert not r.passed
        assert any("specs/prd.md" in f for f in r.failures)

    def test_plan_gate_blocks_when_prd_state_missing(self, tmp_path):
        """Plan gate blocks when prd_complete is not set."""
        _write(tmp_path, "specs/prd.md", _prd())
        r = gate_phase("plan", tmp_path, {"grill_complete": True})
        assert not r.passed
        assert any("prd_complete" in f for f in r.failures)

    def test_build_gate_blocks_when_plan_not_approved(self, tmp_path):
        _write(tmp_path, "plans/plan.md", _plan())
        r = gate_phase("build", tmp_path, {"prd_complete": True})
        assert not r.passed
        assert any("plan_approved" in f for f in r.failures)

    def test_review_gate_blocks_when_iron_law_not_met(self, tmp_path):
        _write(tmp_path, "build/tdd-summary.md", _tdd_summary_passing())
        r = gate_phase("review", tmp_path, {})
        assert not r.passed
        assert any("iron_law_met" in f for f in r.failures)

    def test_qa_gate_blocks_when_review_not_passed(self, tmp_path):
        _write(tmp_path, "ops/review-report.md", _review_report_fail())
        r = gate_phase("qa", tmp_path, {"iron_law_met": True})
        assert not r.passed
        assert any("review_passed" in f for f in r.failures)

    def test_qa_gate_blocks_when_review_report_missing(self, tmp_path):
        r = gate_phase("qa", tmp_path, {"iron_law_met": True, "review_passed": True})
        assert not r.passed
        assert any("review-report.md" in f for f in r.failures)

    def test_deploy_gate_blocks_on_high_severity_no_waiver(self, tmp_path):
        _write(tmp_path, "qa/evidence.md", _evidence())
        state = {"max_severity": "high", "review_passed": True, "iron_law_met": True}
        r = gate_phase("deploy", tmp_path, state, waivers=[])
        assert not r.passed
        assert any("max_severity" in f for f in r.failures)

    def test_deploy_gate_blocks_on_critical_even_with_state_waiver(self, tmp_path):
        """critical severity is non-waivable — state.waivers flag does not help."""
        _write(tmp_path, "qa/evidence.md", _evidence())
        state = {"max_severity": "critical", "waivers": [{"type": "security-severity"}]}
        r = gate_phase("deploy", tmp_path, state, waivers=[])
        assert not r.passed

    def test_done_gate_blocks_without_artifact_contract_met(self, tmp_path):
        manifest = {"schema_version": "v3"}
        _write(tmp_path, "ops/verification-manifest.json", json.dumps(manifest))
        r = gate_phase("done", tmp_path, {})
        assert not r.passed
        assert any("artifact_contract_met" in f for f in r.failures)

    def test_done_gate_blocks_without_manifest(self, tmp_path):
        r = gate_phase("done", tmp_path, {"artifact_contract_met": True})
        assert not r.passed
        assert any("verification-manifest" in f for f in r.failures)


# ---------------------------------------------------------------------------
# Gate recovery paths — waivers re-open blocked phases
# ---------------------------------------------------------------------------

class TestGateWaiverPaths:

    def _waiver(self, gate="security-severity", expires=None, is_agent=False, approved_by="paulrussell"):
        return {
            "gate": gate,
            "reason": "approved for test",
            "approved_by": approved_by,
            "expires": expires or FUTURE,
            "is_agent": is_agent,
            "comment_id": "c1",
            "posted_by": approved_by,
        }

    def test_deploy_gate_passes_with_valid_comment_waiver(self, tmp_path):
        _write(tmp_path, "qa/evidence.md", _evidence())
        state = {"max_severity": "high"}
        r = gate_phase("deploy", tmp_path, state, waivers=[self._waiver()])
        sev_failures = [f for f in r.failures if "max_severity" in f]
        assert sev_failures == []

    def test_deploy_gate_passes_with_state_waiver_flag(self, tmp_path):
        _write(tmp_path, "qa/evidence.md", _evidence())
        state = {"max_severity": "high", "waivers": [{"type": "security-severity"}]}
        r = gate_phase("deploy", tmp_path, state, waivers=[])
        sev_failures = [f for f in r.failures if "max_severity" in f]
        assert sev_failures == []

    def test_waiver_rejected_when_posted_by_agent(self, tmp_path):
        """Agent-posted GATE-WAIVER must be ignored; gate remains blocked."""
        _write(tmp_path, "qa/evidence.md", _evidence())
        state = {"max_severity": "high"}
        agent_waiver = self._waiver(is_agent=True)
        r = gate_phase("deploy", tmp_path, state, waivers=[agent_waiver])
        sev_failures = [f for f in r.failures if "max_severity" in f]
        assert sev_failures, "gate should still be blocked — agent waivers are invalid"

    def test_waiver_rejected_when_expired(self, tmp_path):
        """Expired GATE-WAIVER must be ignored; gate remains blocked."""
        _write(tmp_path, "qa/evidence.md", _evidence())
        state = {"max_severity": "high"}
        expired_waiver = self._waiver(expires=PAST)
        r = gate_phase("deploy", tmp_path, state, waivers=[expired_waiver])
        sev_failures = [f for f in r.failures if "max_severity" in f]
        assert sev_failures, "gate should still be blocked — expired waivers are invalid"

    def test_waiver_rejected_for_non_waivable_gate(self, tmp_path):
        """Waiver for iron-law gate must not bypass iron-law in the waiver system."""
        from devflow.waivers import validate_waiver
        w = self._waiver(gate="iron-law")
        ok, msg = validate_waiver(w, [])
        assert not ok
        assert "not waivable" in msg


# ---------------------------------------------------------------------------
# Seal failure paths
# ---------------------------------------------------------------------------

class TestSealFailurePaths:

    def test_build_seal_fails_on_iron_law_violation(self, tmp_path):
        """Build seal rejects tdd-summary with no Iron Law regex match."""
        _write(tmp_path, "build/tdd-summary.md", _tdd_summary_failing())
        r = seal_phase("build", "slug", "i1", tmp_path, {})
        assert not r.passed
        assert any("Iron Law" in f for f in r.failures)
        assert r.state_updates.get("iron_law_met") is not True

    def test_build_seal_fails_when_test_output_section_missing(self, tmp_path):
        _write(tmp_path, "build/tdd-summary.md", "No test output here.\n")
        r = seal_phase("build", "slug", "i1", tmp_path, {})
        assert not r.passed
        assert any("Test Output" in f for f in r.failures)

    def test_build_seal_passes_on_iron_law_match(self, tmp_path):
        _write(tmp_path, "build/tdd-summary.md", _tdd_summary_passing())
        r = seal_phase("build", "slug", "i1", tmp_path, {})
        assert r.passed
        assert r.state_updates.get("iron_law_met") is True

    def test_qa_seal_fails_below_coverage_threshold(self, tmp_path):
        """QA seal blocks when coverage_pct < 70% for new_feature."""
        _write(tmp_path, "qa/evidence.md", _evidence(coverage_pct=40.0))
        r = seal_phase("qa", "slug", "i1", tmp_path, {"feature_type": "new_feature"})
        assert not r.passed
        assert any("coverage_pct" in f and "40" in f for f in r.failures)

    def test_qa_seal_passes_with_coverage_waiver(self, tmp_path):
        """QA seal passes when coverage is low but --waive-coverage is set; records waiver."""
        _write(tmp_path, "qa/evidence.md", _evidence(coverage_pct=40.0))
        r = seal_phase(
            "qa", "slug", "i1", tmp_path,
            {"feature_type": "new_feature"},
            waive_coverage=True,
        )
        assert r.passed
        assert any("waived" in w for w in r.waivers)
        assert any("waived" in w for w in r.warnings)

    def test_qa_seal_waiver_recorded_in_manifest(self, tmp_path):
        """Waiver from --waive-coverage must appear in verification-manifest.json."""
        _write(tmp_path, "qa/evidence.md", _evidence(coverage_pct=40.0))
        seal_phase(
            "qa", "slug", "i1", tmp_path,
            {"feature_type": "new_feature"},
            waive_coverage=True,
        )
        m = _manifest(tmp_path)
        assert any("waived" in w for w in m["phases"]["qa"]["waivers"])

    def test_review_seal_fails_when_decision_missing(self, tmp_path):
        _write(tmp_path, "ops/review-report.md", "## Checklist\n| Item | Status |\n|---|---|\n")
        r = seal_phase("review", "slug", "i1", tmp_path, {})
        assert not r.passed
        assert any("Decision" in f for f in r.failures)

    def test_security_seal_fails_on_invalid_severity(self, tmp_path):
        _write(tmp_path, "qa/security-review.md", "**max_severity:** ultra-critical\n**sign_off:** agent\n")
        r = seal_phase("security", "slug", "i1", tmp_path, {})
        assert not r.passed
        assert any("max_severity" in f for f in r.failures)

    def test_security_seal_writes_max_severity_to_state(self, tmp_path):
        _write(tmp_path, "qa/security-review.md", _security_review("medium"))
        r = seal_phase("security", "slug", "i1", tmp_path, {})
        assert r.passed
        assert r.state_updates["max_severity"] == "medium"

    def test_deploy_seal_fails_when_rollback_section_empty(self, tmp_path):
        content = "## Steps\n1. deploy\n\n## Rollback\n\n## Health Checks\n`curl app/healthz`\n"
        _write(tmp_path, "ops/deploy-steps.md", content)
        r = seal_phase("deploy", "slug", "i1", tmp_path, {})
        assert not r.passed
        assert any("Rollback" in f for f in r.failures)

    def test_prd_seal_fails_when_section_missing(self, tmp_path):
        content = "## Goal\nShip.\n\n## Background\nContext.\n\n## Scope\nIn.\n"
        _write(tmp_path, "specs/prd.md", content)
        r = seal_phase("prd", "slug", "i1", tmp_path, {})
        assert not r.passed
        missing = [f for f in r.failures if "missing sections" in f]
        assert missing
        assert "## Acceptance Criteria" in missing[0]

    def test_plan_seal_fails_when_section_missing(self, tmp_path):
        content = "## Phases\n1. Tracer.\n\n## ADRs\nNone.\n"
        _write(tmp_path, "plans/plan.md", content)
        r = seal_phase("plan", "slug", "i1", tmp_path, {})
        assert not r.passed
        assert any("## Rollback" in f for f in r.failures)


# ---------------------------------------------------------------------------
# Seal manifest — written on pass, NOT on failure
# ---------------------------------------------------------------------------

class TestSealManifestBehaviour:

    def test_manifest_not_written_on_seal_failure(self, tmp_path):
        """If seal fails the manifest must NOT be updated."""
        _write(tmp_path, "build/tdd-summary.md", _tdd_summary_failing())
        r = seal_phase("build", "slug", "i1", tmp_path, {})
        assert not r.passed
        assert not (tmp_path / "ops" / "verification-manifest.json").exists()

    def test_manifest_written_on_seal_pass(self, tmp_path):
        _write(tmp_path, "build/tdd-summary.md", _tdd_summary_passing())
        r = seal_phase("build", "slug", "i1", tmp_path, {})
        assert r.passed
        m = _manifest(tmp_path)
        assert "build" in m["phases"]
        assert m["phases"]["build"]["thresholds"]["iron_law_met"] is True

    def test_manifest_accumulates_across_phases(self, tmp_path):
        """Each passing seal appends to the manifest without overwriting prior phases."""
        _write(tmp_path, "build/tdd-summary.md", _tdd_summary_passing())
        seal_phase("build", "slug", "i1", tmp_path, {})

        _write(tmp_path, "qa/evidence.md", _evidence())
        seal_phase("qa", "slug", "i1", tmp_path, {})

        m = _manifest(tmp_path)
        assert "build" in m["phases"]
        assert "qa" in m["phases"]


# ---------------------------------------------------------------------------
# Publisher — conflict retry and persistent failure
# ---------------------------------------------------------------------------

class TestPublisherRetryBehaviour:
    """
    Tests for artifact_publisher._upload_with_retry via publish_artifacts.
    The PaperclipClient is injected as a mock — no network I/O.
    """

    def _make_pc(self) -> MagicMock:
        pc = MagicMock()
        pc.get_document = AsyncMock(return_value={"revisionId": "rev-1"})
        pc.post_comment = AsyncMock(return_value=None)
        return pc

    def test_upload_succeeds_on_first_attempt(self, tmp_path):
        pc = self._make_pc()
        pc.put_document = AsyncMock(return_value={"revisionId": "rev-2"})

        _write(tmp_path, "specs/prd.md", _prd())
        result = asyncio.run(
            publish_artifacts("issue-1", "slug", "prd", tmp_path, pc)
        )
        assert result.success
        assert len(result.critical_failures) == 0
        assert result.uploads[0].status == "ok"
        assert pc.put_document.call_count == 1

    def test_upload_retries_on_409_conflict(self, tmp_path):
        """Publisher re-fetches revisionId and retries once on a 409 conflict."""
        pc = self._make_pc()
        call_count = 0

        async def put_with_conflict(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("409 conflict — revision mismatch")
            return {"revisionId": "rev-3"}

        pc.put_document = put_with_conflict

        _write(tmp_path, "specs/prd.md", _prd())
        result = asyncio.run(
            publish_artifacts("issue-1", "slug", "prd", tmp_path, pc)
        )
        assert result.success
        assert result.uploads[0].status == "ok"
        assert call_count == 2  # initial attempt + 1 retry

    def test_persistent_failure_on_critical_artifact_posts_blocking_comment(self, tmp_path):
        """
        When a critical artifact upload always fails, publisher posts a blocking
        comment and result.success is False.
        """
        pc = self._make_pc()
        pc.put_document = AsyncMock(side_effect=Exception("500 server error"))

        # verification-manifest is the critical (blocking_upload=True) artifact
        _write(tmp_path, "ops/verification-manifest.json", json.dumps({"schema_version": "v3"}))
        result = asyncio.run(
            publish_artifacts("issue-1", "slug", "done", tmp_path, pc)
        )
        assert not result.success
        assert len(result.critical_failures) == 1
        assert pc.post_comment.called

    def test_missing_non_critical_artifact_is_warning_not_failure(self, tmp_path):
        """A missing non-critical artifact (e.g. prd) produces a warning, not a critical failure."""
        pc = self._make_pc()
        pc.put_document = AsyncMock(return_value={"revisionId": "rev-1"})

        # Don't write specs/prd.md — it is non-critical (blocking_upload=False)
        result = asyncio.run(
            publish_artifacts("issue-1", "slug", "prd", tmp_path, pc)
        )
        assert result.success          # non-critical miss doesn't fail
        assert len(result.warnings) > 0
        assert any("specs/prd.md" in w for w in result.warnings)
