"""
Unit tests for lib/devflow.py.

Run from ~/ai-dev-flow:
    pytest tests/test_devflow.py -v
"""
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from devflow import check_evidence, generate_evidence, stage_done, validate_manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_manifest(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f)


def write_state(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


VALID_MANIFEST = {
    "env": {"venv": ".venv"},
    "qa": {"suites": [{"name": "Unit", "command": "pytest tests/"}]},
}


# ---------------------------------------------------------------------------
# validate_manifest
# ---------------------------------------------------------------------------

class TestValidateManifest:
    def test_valid_manifest(self, tmp_path):
        venv = tmp_path / ".venv"
        venv.mkdir()
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, VALID_MANIFEST)
        assert validate_manifest(manifest_path, tmp_path) == []

    def test_missing_venv_key(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, {"env": {}, "qa": {"suites": [{"name": "Unit", "command": "pytest"}]}})
        errors = validate_manifest(manifest_path, tmp_path)
        assert any("env.venv" in e for e in errors)

    def test_venv_dir_not_on_disk(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, VALID_MANIFEST)
        # .venv dir not created
        errors = validate_manifest(manifest_path, tmp_path)
        assert any("not found" in e for e in errors)

    def test_empty_suites(self, tmp_path):
        (tmp_path / ".venv").mkdir()
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, {"env": {"venv": ".venv"}, "qa": {"suites": []}})
        errors = validate_manifest(manifest_path, tmp_path)
        assert any("suites is empty" in e for e in errors)

    def test_suite_missing_command(self, tmp_path):
        (tmp_path / ".venv").mkdir()
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, {"env": {"venv": ".venv"}, "qa": {"suites": [{"name": "Unit", "command": ""}]}})
        errors = validate_manifest(manifest_path, tmp_path)
        assert any("no command" in e for e in errors)

    def test_invalid_yaml(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        manifest_path.write_text(": invalid: [yaml")
        errors = validate_manifest(manifest_path, tmp_path)
        assert any("not valid YAML" in e for e in errors)

    def test_non_mapping_yaml(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        manifest_path.write_text("- item1\n- item2\n")
        errors = validate_manifest(manifest_path, tmp_path)
        assert any("mapping" in e for e in errors)


# ---------------------------------------------------------------------------
# check_evidence
# ---------------------------------------------------------------------------

class TestCheckEvidence:
    def test_all_passing(self, tmp_path):
        (tmp_path / "qa").mkdir()
        (tmp_path / "qa" / "evidence.md").write_text("# Evidence")
        write_state(tmp_path / "state.json", {"qa": {"unit": "pass", "prefect-run": "pass"}})
        assert check_evidence(tmp_path, "my-feature") == []

    def test_missing_evidence_file(self, tmp_path):
        write_state(tmp_path / "state.json", {"qa": {"unit": "pass", "prefect-run": "pass"}})
        errors = check_evidence(tmp_path, "my-feature")
        assert any("evidence.md" in e for e in errors)

    def test_missing_state_file(self, tmp_path):
        (tmp_path / "qa").mkdir()
        (tmp_path / "qa" / "evidence.md").write_text("# Evidence")
        errors = check_evidence(tmp_path, "my-feature")
        assert any("state.json" in e for e in errors)

    def test_unit_not_passed(self, tmp_path):
        (tmp_path / "qa").mkdir()
        (tmp_path / "qa" / "evidence.md").write_text("# Evidence")
        write_state(tmp_path / "state.json", {"qa": {"unit": "fail", "prefect-run": "pass"}})
        errors = check_evidence(tmp_path, "my-feature")
        assert any("qa.unit" in e for e in errors)

    def test_prefect_run_pending(self, tmp_path):
        (tmp_path / "qa").mkdir()
        (tmp_path / "qa" / "evidence.md").write_text("# Evidence")
        write_state(tmp_path / "state.json", {"qa": {"unit": "pass"}})
        errors = check_evidence(tmp_path, "my-feature")
        assert any("prefect-run" in e for e in errors)

    def test_multiple_errors_reported(self, tmp_path):
        write_state(tmp_path / "state.json", {"qa": {}})
        errors = check_evidence(tmp_path, "my-feature")
        assert len(errors) >= 2


# ---------------------------------------------------------------------------
# stage_done
# ---------------------------------------------------------------------------

class TestStageDone:
    def test_prep_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"completed": ["prep"]})
        assert stage_done(tmp_path, "prep") is True

    def test_prep_not_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"completed": []})
        assert stage_done(tmp_path, "prep") is False

    def test_prep_no_state_file(self, tmp_path):
        assert stage_done(tmp_path, "prep") is False

    def test_feature_done(self, tmp_path):
        plan = tmp_path / "plans" / "plan.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("# Plan")
        assert stage_done(tmp_path, "feature") is True

    def test_feature_not_done(self, tmp_path):
        assert stage_done(tmp_path, "feature") is False

    def test_tdd_done_with_green(self, tmp_path):
        summary = tmp_path / "build" / "tdd-summary.md"
        summary.parent.mkdir(parents=True)
        summary.write_text("**Total: 5 GREEN, 0 RED**\n✅ GREEN", encoding="utf-8")
        assert stage_done(tmp_path, "tdd") is True

    def test_tdd_not_done_without_green(self, tmp_path):
        summary = tmp_path / "build" / "tdd-summary.md"
        summary.parent.mkdir(parents=True)
        summary.write_text("**Total: 0 GREEN, 3 RED**")
        assert stage_done(tmp_path, "tdd") is False

    def test_tdd_not_done_missing_file(self, tmp_path):
        assert stage_done(tmp_path, "tdd") is False

    def test_qa_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"qa": {"unit": "pass"}})
        assert stage_done(tmp_path, "qa") is True

    def test_qa_not_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"qa": {"unit": "fail"}})
        assert stage_done(tmp_path, "qa") is False

    def test_prefect_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"qa": {"prefect-run": "pass"}})
        assert stage_done(tmp_path, "prefect") is True

    def test_prefect_not_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"qa": {}})
        assert stage_done(tmp_path, "prefect") is False

    def test_deploy_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"deploy": {"status": "success"}})
        assert stage_done(tmp_path, "deploy") is True

    def test_deploy_not_done(self, tmp_path):
        write_state(tmp_path / "state.json", {"deploy": {"status": "fail"}})
        assert stage_done(tmp_path, "deploy") is False

    def test_unknown_stage(self, tmp_path):
        assert stage_done(tmp_path, "nonexistent") is False


# ---------------------------------------------------------------------------
# generate_evidence
# ---------------------------------------------------------------------------

class TestGenerateEvidence:
    def test_writes_evidence_file(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, VALID_MANIFEST)
        result = generate_evidence(manifest_path, tmp_path, "my-feature")
        assert result.exists()
        content = result.read_text()
        assert "my-feature" in content
        assert "Manifest SHA256" in content

    def test_reflects_qa_state(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, VALID_MANIFEST)
        write_state(tmp_path / "state.json", {"qa": {"unit": "pass", "prefect-run": "pass"}})
        result = generate_evidence(manifest_path, tmp_path, "my-feature")
        content = result.read_text()
        assert "pass" in content

    def test_pending_when_no_state(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, VALID_MANIFEST)
        result = generate_evidence(manifest_path, tmp_path, "my-feature")
        content = result.read_text()
        assert "pending" in content

    def test_artifact_exists_flags(self, tmp_path):
        manifest_path = tmp_path / "devflow.yaml"
        write_manifest(manifest_path, VALID_MANIFEST)
        plan = tmp_path / "plans" / "plan.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("# Plan")
        result = generate_evidence(manifest_path, tmp_path, "my-feature")
        content = result.read_text()
        assert "| Plan |" in content
        assert "yes" in content
