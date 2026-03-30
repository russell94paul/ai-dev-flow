"""
Tests verifying contract.py is the single source of truth for artifact paths
and that gatekeeper + artifact_publisher stay consistent with it.
"""
import json
import tempfile
from pathlib import Path

import pytest

from devflow import contract
from devflow.gatekeeper import (
    PRD_REQUIRED_SECTIONS,
    PLAN_REQUIRED_SECTIONS,
    gate_phase,
    seal_phase,
)


# ---------------------------------------------------------------------------
# contract.py structural tests
# ---------------------------------------------------------------------------

def test_all_phase_artifact_keys_exist():
    """Every key in PHASE_ARTIFACT_KEYS must resolve to a known ARTIFACTS entry."""
    for phase, keys in contract.PHASE_ARTIFACT_KEYS.items():
        for key in keys:
            assert key in contract.ARTIFACTS, (
                f"PHASE_ARTIFACT_KEYS[{phase!r}] references unknown key {key!r}"
            )


def test_artifact_paths_are_unique():
    """No two ARTIFACTS entries should share a path (would indicate a copy-paste error)."""
    paths = [a["path"] for a in contract.ARTIFACTS.values()]
    assert len(paths) == len(set(paths)), "Duplicate artifact paths found in ARTIFACTS"


def test_accessor_artifact_path():
    assert contract.artifact_path("prd") == "specs/prd.md"
    assert contract.artifact_path("tdd-summary") == "build/tdd-summary.md"
    assert contract.artifact_path("security-review") == "qa/security-review.md"
    assert contract.artifact_path("verification-manifest") == "ops/verification-manifest.json"


def test_accessor_required_sections():
    prd_secs = contract.required_sections("prd")
    assert "## Goal" in prd_secs
    assert "## Acceptance Criteria" in prd_secs

    plan_secs = contract.required_sections("plan")
    assert "## Phases" in plan_secs
    assert "## Rollback" in plan_secs


def test_artifacts_for_phase_connector_filter():
    non_connector = contract.artifacts_for_phase("deploy", "new_feature")
    keys = [a["key"] for a in non_connector]
    assert "connector-checklist" not in keys

    connector = contract.artifacts_for_phase("deploy", "connector")
    # connector-checklist is not in deploy phase, but verify filter doesn't break
    assert all(isinstance(a, dict) for a in connector)


def test_connector_only_excluded_by_default():
    """connector-checklist must only appear when feature_type == 'connector'."""
    for phase in contract.PHASES:
        result = contract.artifacts_for_phase(phase, "new_feature")
        for a in result:
            assert not a.get("connector_only"), (
                f"connector_only artifact {a['key']!r} leaked into phase {phase!r} for new_feature"
            )


# ---------------------------------------------------------------------------
# gatekeeper uses contract constants
# ---------------------------------------------------------------------------

def test_gatekeeper_prd_sections_match_contract():
    assert PRD_REQUIRED_SECTIONS == contract.required_sections("prd")


def test_gatekeeper_plan_sections_match_contract():
    assert PLAN_REQUIRED_SECTIONS == contract.required_sections("plan")


# ---------------------------------------------------------------------------
# artifact_publisher uses contract
# ---------------------------------------------------------------------------

def test_publisher_imports_from_contract():
    """artifact_publisher.publish_artifacts must use artifacts_for_phase, not a local dict."""
    import devflow.artifact_publisher as ap
    import inspect
    src = inspect.getsource(ap)
    assert "from devflow.contract import artifacts_for_phase" in src
    # The old hardcoded dict must not be present (stale comment references are OK)
    assert "PHASE_ARTIFACTS: dict" not in src
    assert "PHASE_ARTIFACTS.get(" not in src


def test_publisher_blocking_upload_field():
    """_is_critical must read blocking_upload, not the old critical field."""
    import devflow.artifact_publisher as ap
    import inspect
    src = inspect.getsource(ap._is_critical)
    assert "blocking_upload" in src
    assert '"critical"' not in src


# ---------------------------------------------------------------------------
# done seal writes artifact_contract_met
# ---------------------------------------------------------------------------

def _write_artifact(feature_dir: Path, rel_path: str, content: str) -> None:
    p = feature_dir / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_done_seal_sets_artifact_contract_met():
    """seal_phase('done') must write artifact_contract_met=true to the manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        feature_dir = Path(tmpdir)
        # Pre-populate a minimal verification-manifest so the artifact exists
        manifest = {
            "schema_version": "v3",
            "feature_slug": "test-slug",
            "issue_id": "test-issue",
            "phases": {"deploy": {"sealed_at": "2026-01-01T00:00:00+00:00"}},
        }
        _write_artifact(
            feature_dir,
            contract.artifact_path("verification-manifest"),
            json.dumps(manifest),
        )

        result = seal_phase(
            phase="done",
            slug="test-slug",
            issue_id="test-issue",
            feature_dir=feature_dir,
            state={},
        )

        assert result.passed, f"done seal unexpectedly failed: {result.failures}"
        assert result.state_updates.get("artifact_contract_met") is True

        # Manifest on disk must also have the flag
        manifest_path = feature_dir / contract.artifact_path("verification-manifest")
        written = json.loads(manifest_path.read_text())
        assert written.get("artifact_contract_met") is True


def test_done_seal_fails_when_manifest_missing():
    """done seal must fail if verification-manifest.json is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = seal_phase(
            phase="done",
            slug="test-slug",
            issue_id="test-issue",
            feature_dir=Path(tmpdir),
            state={},
        )
        assert not result.passed
        assert any("verification-manifest" in f for f in result.failures)


def test_done_gate_requires_artifact_contract_met():
    """gate_phase('done') must fail when state.artifact_contract_met is absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        feature_dir = Path(tmpdir)
        # Provide manifest so only the state flag is missing
        manifest = {"schema_version": "v3"}
        _write_artifact(
            feature_dir,
            contract.artifact_path("verification-manifest"),
            json.dumps(manifest),
        )

        result = gate_phase("done", feature_dir, state={})
        assert not result.passed
        assert any("artifact_contract_met" in f for f in result.failures)
