"""
devflow.py — pure Python utilities for ai-dev-flow.

These functions contain the logic previously embedded in bash heredocs.
They have no dependency on environment variables or subprocess calls,
making them straightforward to unit test.
"""
import hashlib
import json
import yaml
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def validate_manifest(manifest_path: Path, repo_root: Path) -> list[str]:
    """
    Validate a devflow.yaml manifest.

    Returns a list of error strings. An empty list means the manifest is valid.
    """
    errors = []

    try:
        with open(manifest_path, "r") as f:
            manifest = yaml.safe_load(f)
    except yaml.YAMLError as e:
        return [f"devflow.yaml is not valid YAML: {e}"]

    if not isinstance(manifest, dict):
        return ["devflow.yaml must be a YAML mapping"]

    venv = manifest.get("env", {}).get("venv", "")
    if not venv:
        errors.append("env.venv is missing")
    elif not (repo_root / venv).exists():
        errors.append(f"venv directory not found: {venv} (run bootstrap first)")

    suites = manifest.get("qa", {}).get("suites", [])
    if not suites:
        errors.append("qa.suites is empty — add at least one test suite")
    else:
        for suite in suites:
            if not suite.get("command", "").strip():
                errors.append(
                    f"qa suite {suite.get('name', '(unnamed)')!r} has no command"
                )

    return errors


# ---------------------------------------------------------------------------
# Evidence checking
# ---------------------------------------------------------------------------

def check_evidence(feature_notes_dir: Path, feature_slug: str) -> list[str]:
    """
    Check that all required QA gates have passed before deploying.

    Returns a list of error strings. An empty list means the check passed.
    """
    errors = []

    evidence_path = feature_notes_dir / "qa" / "evidence.md"
    if not evidence_path.exists():
        errors.append("evidence.md not found — run ai prefect-run first")

    state_path = feature_notes_dir / "state.json"
    if not state_path.exists():
        errors.append("state.json not found — no stages have been run yet")
        return errors

    with open(state_path) as f:
        state = json.load(f)

    qa = state.get("qa", {})

    unit = qa.get("unit")
    if unit != "pass":
        errors.append(f"qa.unit is '{unit or 'pending'}' — run ai qa first")

    prefect_run = qa.get("prefect-run")
    if prefect_run != "pass":
        errors.append(
            f"qa.prefect-run is '{prefect_run or 'pending'}' — run ai prefect-run first"
        )

    return errors


# ---------------------------------------------------------------------------
# Evidence generation
# ---------------------------------------------------------------------------

def generate_evidence(
    manifest_path: Path, feature_notes_dir: Path, feature_slug: str
) -> Path:
    """
    Write qa/evidence.md summarising all QA artifacts and state.

    Returns the path to the written evidence file.
    """
    with open(manifest_path, "r") as f:
        manifest = yaml.safe_load(f)

    state = {}
    state_path = feature_notes_dir / "state.json"
    if state_path.exists():
        with open(state_path) as f:
            state = json.load(f)

    with open(manifest_path, "rb") as f:
        manifest_sha = hashlib.sha256(f.read()).hexdigest()

    prd_path = feature_notes_dir / "specs" / "prd.md"
    plan_path = feature_notes_dir / "plans" / "plan.md"
    diagram_path = feature_notes_dir / "specs" / "diagram.md"

    lines = [
        f"# Evidence: {feature_slug}",
        f"",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}Z",
        f"**Manifest SHA256:** `{manifest_sha}`",
        f"",
        f"## Artifacts",
        f"",
        f"| Artifact | Path | Exists |",
        f"|----------|------|--------|",
        f'| PRD | {prd_path} | {"yes" if prd_path.exists() else "no"} |',
        f'| Plan | {plan_path} | {"yes" if plan_path.exists() else "no"} |',
        f'| Diagram | {diagram_path} | {"yes" if diagram_path.exists() else "no"} |',
        f"",
        f"## QA Suites",
        f"",
        f"| Suite | Status | Artifact |",
        f"|-------|--------|----------|",
    ]

    qa_suites = manifest.get("qa", {}).get("suites", [])
    qa_state = state.get("qa", {})
    for suite in qa_suites:
        name = suite.get("name", "")
        artifact_tmpl = suite.get("artifact", "")
        artifact = artifact_tmpl.replace("%slug%", feature_slug)
        slug_key = name.lower().replace(" ", "-")
        status = qa_state.get(slug_key, "pending")
        lines.append(f"| {name} | {status} | {artifact} |")

    lines += [
        f"",
        f"## Prefect Run",
        f"",
        f'**Status:** {state.get("qa", {}).get("prefect-run", "pending")}',
        f"",
        f"## Deploy",
        f"",
        f'**Status:** {state.get("deploy", {}).get("status", "pending")}',
    ]

    evidence_path = feature_notes_dir / "qa" / "evidence.md"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("\n".join(lines) + "\n")
    return evidence_path


# ---------------------------------------------------------------------------
# Stage completion checks
# ---------------------------------------------------------------------------

def stage_done(feature_notes_dir: Path, stage: str) -> bool:
    """
    Return True if the given stage has been completed for this feature.
    """
    state_path = feature_notes_dir / "state.json"

    def load_state() -> dict:
        if not state_path.exists():
            return {}
        with open(state_path) as f:
            return json.load(f)

    if stage == "prep":
        state = load_state()
        return "prep" in state.get("completed", [])

    if stage == "feature":
        return (feature_notes_dir / "plans" / "plan.md").exists()

    if stage == "tdd":
        summary = feature_notes_dir / "build" / "tdd-summary.md"
        if not summary.exists():
            return False
        return "✅ GREEN" in summary.read_text(encoding="utf-8")

    if stage == "qa":
        state = load_state()
        return state.get("qa", {}).get("unit") == "pass"

    if stage == "prefect":
        state = load_state()
        return state.get("qa", {}).get("prefect-run") == "pass"

    if stage == "deploy":
        state = load_state()
        return state.get("deploy", {}).get("status") == "success"

    return False
