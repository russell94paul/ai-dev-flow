"""
Gatekeeper — phase gate and seal logic for the v3 devflow pipeline.

Core check functions are pure (state dict + local files) — zero Paperclip
dependency. The CLI layer fetches state from Paperclip if available, then
passes it here.

Exit contract:
  gate_phase() returns GateResult  — caller exits 0 on pass, 1 on block
  seal_phase() returns SealResult  — caller exits 0 on pass, 1 on fail
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from devflow.contract import artifact_path
from devflow.contract import required_sections as _artifact_sections
from devflow.waivers import find_active_waiver


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class GateResult:
    passed: bool
    failures: list[str] = field(default_factory=list)   # human-readable failure descriptions
    recoveries: list[str] = field(default_factory=list)  # paired recovery actions


@dataclass
class SealResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    recoveries: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)   # relative paths sealed
    thresholds: dict = field(default_factory=dict)
    waivers: list[str] = field(default_factory=list)
    state_updates: dict = field(default_factory=dict)    # fields to write back to state


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

PRD_REQUIRED_SECTIONS = _artifact_sections("prd")
PLAN_REQUIRED_SECTIONS = _artifact_sections("plan")

IRON_LAW_PATTERNS = [
    re.compile(r"PASSED \d+"),
    re.compile(r"GREEN \d+"),
    re.compile(r"\d+ passed"),
]

VALID_SEVERITY_LEVELS = {"none", "low", "medium", "high", "critical"}
SEVERITY_ORDER = ["none", "low", "medium", "high", "critical"]

COVERAGE_THRESHOLDS = {
    "bugfix": 60.0,
    "new_feature": 70.0,
    "connector": 70.0,
    # refactor: non-decreasing (checked separately)
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_file(path: Path) -> Optional[str]:
    """Return file text or None if missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _has_section(text: str, section: str) -> bool:
    """Check whether a markdown section header is present (line-start match)."""
    for line in text.splitlines():
        if line.strip() == section or line.strip().startswith(section + " "):
            return True
    return False


def _missing_sections(text: str, required: list[str]) -> list[str]:
    return [s for s in required if not _has_section(text, s)]


def _extract_section_text(text: str, section: str) -> str:
    """Return the body of a markdown section (everything until the next ## heading)."""
    lines = text.splitlines()
    in_section = False
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == section or stripped.startswith(section + " "):
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## ") and stripped != section:
                break
            body.append(line)
    return "\n".join(body)


def _iron_law_matches(section_text: str) -> bool:
    """Return True if any Iron Law regex matches anywhere in the section text."""
    for pattern in IRON_LAW_PATTERNS:
        if pattern.search(section_text):
            return True
    return False


def _extract_field_value(text: str, field_name: str) -> Optional[str]:
    """
    Extract a markdown bold-field value: `**field_name:** value`.
    Returns stripped value or None if not found.
    """
    pattern = re.compile(
        r"\*\*" + re.escape(field_name) + r"\*\*\s*:?\s*(.+)",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if m:
        return m.group(1).strip()
    return None


def _severity_exceeds(severity: str, max_allowed: str) -> bool:
    """Return True when severity is strictly worse than max_allowed."""
    try:
        return SEVERITY_ORDER.index(severity) > SEVERITY_ORDER.index(max_allowed)
    except ValueError:
        return True  # unknown severity → treat as exceeded


def _mermaid_check(plan_text: str, waive_diagrams: bool) -> tuple[bool, list[str]]:
    """
    Validate Mermaid diagrams in plan text.
    Returns (passed, warnings_or_failures).
    If waive_diagrams is True, failures become warnings.
    """
    issues: list[str] = []
    # Check for ≥ 2 Mermaid diagrams or the N/A heading
    mermaid_count = plan_text.count("```mermaid")
    has_na = _has_section(plan_text, "## Diagrams")

    if mermaid_count < 2 and not has_na:
        msg = "Plan has fewer than 2 Mermaid diagrams and no '## Diagrams — N/A' section"
        if waive_diagrams:
            return True, [f"WARNING (waived): {msg}"]
        return False, [msg]

    if mermaid_count == 0:
        return True, []

    # Try mmdc validation
    try:
        result = subprocess.run(
            ["mmdc", "--version"],
            capture_output=True, timeout=5,
        )
        mmdc_available = result.returncode == 0
    except Exception:
        mmdc_available = False

    if not mmdc_available:
        return True, ["mmdc not available — Mermaid syntax not validated (install @mermaid-js/mermaid-cli to enable)"]

    # Extract and validate each diagram block
    diagram_re = re.compile(r"```mermaid\s*(.*?)```", re.DOTALL)
    for i, m in enumerate(diagram_re.finditer(plan_text)):
        diagram_src = m.group(1).strip()
        try:
            import tempfile, os
            with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False, encoding="utf-8") as f:
                f.write(diagram_src)
                tmp_path = f.name
            result = subprocess.run(
                ["mmdc", "--input", tmp_path, "--output", "/dev/null"],
                capture_output=True, timeout=15,
            )
            os.unlink(tmp_path)
            if result.returncode != 0:
                msg = f"Mermaid diagram {i + 1} syntax error: {result.stderr.decode('utf-8', errors='replace')[:200]}"
                if waive_diagrams:
                    issues.append(f"WARNING (waived): {msg}")
                else:
                    return False, [msg]
        except Exception as exc:
            issues.append(f"WARNING: Could not validate Mermaid diagram {i + 1}: {exc}")

    return True, issues


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def gate_phase(
    phase: str,
    feature_dir: Path,
    state: dict,
    feature_type: Optional[str] = None,
    waivers: Optional[list] = None,
) -> GateResult:
    """
    Read-only precondition check for entering a phase.

    Parameters
    ----------
    phase        : lowercase phase name (grill/prd/plan/build/review/qa/security/deploy/done)
    feature_dir  : absolute path to the feature root (e.g. features/<slug>/)
    state        : state dict loaded from Paperclip or local state file
    feature_type : override for state.feature_type (e.g. "connector")
    """
    phase = phase.lower()
    failures: list[str] = []
    recoveries: list[str] = []

    resolved_feature_type = feature_type or state.get("feature_type", "")

    def _fail(description: str, recovery: str) -> None:
        failures.append(description)
        recoveries.append(recovery)

    def _check_artifact(rel_path: str) -> bool:
        return (feature_dir / rel_path).exists()

    # ── per-phase checks ────────────────────────────────────────────────────

    if phase == "grill":
        pass  # always allowed

    elif phase == "prd":
        if not state.get("grill_complete"):
            _fail(
                "state.grill_complete is not set",
                "Re-run grill phase",
            )

    elif phase == "plan":
        if not state.get("prd_complete"):
            _fail(
                "state.prd_complete is not set",
                "Run: devflow skill write-a-prd",
            )
        prd_path = feature_dir / artifact_path("prd")
        if not prd_path.exists():
            _fail(
                "artifact missing: specs/prd.md",
                "Run: devflow skill write-a-prd",
            )
        else:
            text = _read_file(prd_path) or ""
            missing = _missing_sections(text, PRD_REQUIRED_SECTIONS)
            if missing:
                _fail(
                    f"specs/prd.md is missing sections: {', '.join(missing)}",
                    "Run: devflow skill write-a-prd",
                )

    elif phase == "build":
        if not state.get("plan_approved"):
            _fail(
                "state.plan_approved is not set",
                "Post review request; set issue to in_review; wait for human approval",
            )
        plan_path = feature_dir / artifact_path("plan")
        if not plan_path.exists():
            _fail(
                "artifact missing: plans/plan.md",
                "Run responsible skill to produce the artifact",
            )
        else:
            text = _read_file(plan_path) or ""
            missing = _missing_sections(text, PLAN_REQUIRED_SECTIONS)
            if missing:
                _fail(
                    f"plans/plan.md is missing sections: {', '.join(missing)}",
                    "Run responsible skill to produce the artifact",
                )
        # Connector extra check
        if resolved_feature_type == "connector":
            connectors_dir = feature_dir / "connectors"
            if not connectors_dir.is_dir():
                _fail(
                    "connector extra check: connectors/ directory does not exist under feature_dir",
                    "Run responsible skill to produce the artifact",
                )

    elif phase == "review":
        if not state.get("iron_law_met"):
            _fail(
                "state.iron_law_met is not set",
                "Run: devflow skill tdd <slug>",
            )
        if not _check_artifact(artifact_path("tdd-summary")):
            _fail(
                "artifact missing: build/tdd-summary.md",
                "Run responsible skill to produce the artifact",
            )

    elif phase == "qa":
        if not state.get("review_passed"):
            _fail(
                "state.review_passed is not set",
                "Open builder subtask with reviewer findings",
            )
        if not _check_artifact(artifact_path("review-report")):
            _fail(
                "artifact missing: ops/review-report.md",
                "Run responsible skill to produce the artifact",
            )

    elif phase == "security":
        pass  # always allowed when QA starts

    elif phase == "deploy":
        # Severity check — waivable via GATE-WAIVER comment or state.waivers
        max_sev = str(state.get("max_severity") or "none").lower()
        state_waiver = bool(state.get("waivers"))
        comment_waiver = find_active_waiver(waivers or [], "security-severity", []) is not None
        waiver_present = state_waiver or comment_waiver
        if _severity_exceeds(max_sev, "medium") and not waiver_present:
            _fail(
                f"state.max_severity is '{max_sev}' (must be none/low/medium or waiver present)",
                "Post findings; notify human; set issue to blocked",
            )
        # Required artifacts
        if not _check_artifact(artifact_path("qa-evidence")):
            _fail(
                "artifact missing: qa/evidence.md",
                "Run responsible skill to produce the artifact",
            )
        # Security review artifact (only required when security was triggered)
        if state.get("security_triggered"):
            if not _check_artifact(artifact_path("security-review")):
                _fail(
                    "artifact missing: qa/security-review.md (security_triggered=true)",
                    "Run responsible skill to produce the artifact",
                )
        # Connector extra checks
        if resolved_feature_type == "connector":
            evidence_path = feature_dir / artifact_path("qa-evidence")
            evidence_text = _read_file(evidence_path) or ""
            if not _has_section(evidence_text, "## Connector QA"):
                _fail(
                    "connector extra check: qa/evidence.md is missing '## Connector QA' section",
                    "Run responsible skill to produce the artifact",
                )
            else:
                connector_qa_text = _extract_section_text(evidence_text, "## Connector QA")
                if not re.search(r"contract test.*PASS|PASS.*contract test", connector_qa_text, re.IGNORECASE):
                    _fail(
                        "connector extra check: no 'contract test PASS' result found in '## Connector QA' section",
                        "Run responsible skill to produce the artifact",
                    )

    elif phase == "done":
        if not state.get("artifact_contract_met"):
            _fail(
                "state.artifact_contract_met is not set",
                "Run responsible skill to produce the artifact",
            )
        if not _check_artifact(artifact_path("verification-manifest")):
            _fail(
                "artifact missing: ops/verification-manifest.json",
                "Run responsible skill to produce the artifact",
            )

    else:
        _fail(
            f"Unknown phase: '{phase}'",
            "Check phase name spelling (grill/prd/plan/build/review/qa/security/deploy/done)",
        )

    return GateResult(
        passed=len(failures) == 0,
        failures=failures,
        recoveries=recoveries,
    )


# ---------------------------------------------------------------------------
# Seal
# ---------------------------------------------------------------------------

def seal_phase(
    phase: str,
    slug: str,
    issue_id: str,
    feature_dir: Path,
    state: dict,
    waive_coverage: bool = False,
    waive_diagrams: bool = False,
) -> SealResult:
    """
    Validate artifacts for a completing phase. Writes ops/verification-manifest.json on pass.

    Parameters
    ----------
    phase          : lowercase phase name
    slug           : feature slug (used in manifest)
    issue_id       : issue UUID (used in manifest; may be empty string)
    feature_dir    : absolute path to the feature root
    state          : current state dict (read-only here; state_updates returned separately)
    waive_coverage : skip coverage threshold failure (records waiver)
    waive_diagrams : skip Mermaid diagram check failure (records waiver)
    """
    phase = phase.lower()
    failures: list[str] = []
    recoveries: list[str] = []
    warnings: list[str] = []
    artifacts: list[str] = []
    thresholds: dict = {}
    waivers: list[str] = []
    state_updates: dict = {}

    def _fail(description: str, recovery: str) -> None:
        failures.append(description)
        recoveries.append(recovery)

    def _require_file(rel_path: str) -> Optional[str]:
        """Return file text if present; record failure if missing."""
        full = feature_dir / rel_path
        text = _read_file(full)
        if text is None:
            _fail(
                f"artifact missing: {rel_path}",
                "Re-run the responsible skill targeting only the missing sections",
            )
        else:
            artifacts.append(rel_path)
        return text

    # ── per-phase validation ─────────────────────────────────────────────────

    if phase == "grill":
        if not state.get("grill_complete"):
            _fail(
                "state.grill_complete is not set in state dict",
                "Re-run the responsible skill targeting only the missing sections",
            )

    elif phase == "prd":
        text = _require_file(artifact_path("prd"))
        if text is not None:
            missing = _missing_sections(text, PRD_REQUIRED_SECTIONS)
            if missing:
                _fail(
                    f"specs/prd.md missing sections: {', '.join(missing)}",
                    "Re-run the responsible skill targeting only the missing sections",
                )

    elif phase == "plan":
        text = _require_file(artifact_path("plan"))
        if text is not None:
            missing = _missing_sections(text, PLAN_REQUIRED_SECTIONS)
            if missing:
                _fail(
                    f"plans/plan.md missing sections: {', '.join(missing)}",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            # Mermaid check
            mermaid_passed, mermaid_issues = _mermaid_check(text, waive_diagrams)
            if not mermaid_passed:
                for issue in mermaid_issues:
                    _fail(
                        issue,
                        "Re-run architecture-diagrams skill; or use --waive-diagrams if not applicable",
                    )
            else:
                for w in mermaid_issues:
                    warnings.append(w)
                if waive_diagrams and any("waived" in w for w in mermaid_issues):
                    waivers.append("diagrams: waived by --waive-diagrams flag")

    elif phase == "build":
        text = _require_file(artifact_path("tdd-summary"))
        if text is not None:
            if not _has_section(text, "## Test Output"):
                _fail(
                    "build/tdd-summary.md is missing '## Test Output' section",
                    "Re-run TDD for failing tests; check ## Test Output section contains verbatim runner output",
                )
            else:
                section_text = _extract_section_text(text, "## Test Output")
                if not _iron_law_matches(section_text):
                    _fail(
                        "Iron Law check failed: '## Test Output' does not match any Iron Law regex "
                        "(expected: 'PASSED \\d+', 'GREEN \\d+', or '\\d+ passed')",
                        "Re-run TDD for failing tests; check ## Test Output section contains verbatim runner output",
                    )
                else:
                    thresholds["iron_law_met"] = True
                    state_updates["iron_law_met"] = True

    elif phase == "review":
        text = _require_file(artifact_path("review-report"))
        if text is not None:
            decision = _extract_field_value(text, "Decision")
            if decision is None:
                _fail(
                    "ops/review-report.md missing '**Decision:**' field",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            elif decision.upper() not in ("PASS", "FAIL"):
                _fail(
                    f"ops/review-report.md '**Decision:**' value '{decision}' is not PASS or FAIL",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            if not _has_section(text, "## Checklist"):
                _fail(
                    "ops/review-report.md missing '## Checklist' section",
                    "Re-run the responsible skill targeting only the missing sections",
                )

    elif phase == "qa":
        text = _require_file(artifact_path("qa-evidence"))
        if text is not None:
            tier = _extract_field_value(text, "Tier")
            if tier is None:
                _fail(
                    "qa/evidence.md missing '**Tier:**' field",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            coverage_str = _extract_field_value(text, "coverage_pct")
            if coverage_str is None:
                _fail(
                    "qa/evidence.md missing '**coverage_pct:**' field",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            else:
                try:
                    coverage_pct = float(coverage_str.rstrip("%"))
                    thresholds["coverage_pct"] = coverage_pct
                except ValueError:
                    _fail(
                        f"qa/evidence.md '**coverage_pct:**' value '{coverage_str}' is not a number",
                        "Re-run the responsible skill targeting only the missing sections",
                    )
                    coverage_pct = None

                if coverage_pct is not None:
                    feature_type = state.get("feature_type", "new_feature")
                    if feature_type == "refactor":
                        baseline = state.get("baseline_coverage_pct")
                        if baseline is not None:
                            try:
                                baseline_f = float(baseline)
                                if coverage_pct < baseline_f:
                                    msg = (
                                        f"coverage_pct {coverage_pct}% is below baseline {baseline_f}% "
                                        f"(refactor must be non-decreasing)"
                                    )
                                    if waive_coverage:
                                        waivers.append(f"coverage: waived by --waive-coverage flag ({msg})")
                                        warnings.append(f"WARNING (waived): {msg}")
                                    else:
                                        _fail(
                                            msg,
                                            "Apply --waive-coverage with justification, or re-run tests with coverage goal",
                                        )
                            except (TypeError, ValueError):
                                warnings.append("WARNING: baseline_coverage_pct in state is not numeric — skipping refactor coverage check")
                        else:
                            warnings.append("WARNING: feature_type=refactor but no baseline_coverage_pct in state — coverage check skipped")
                    else:
                        threshold = COVERAGE_THRESHOLDS.get(feature_type, 70.0)
                        thresholds["coverage_threshold"] = threshold
                        if coverage_pct < threshold:
                            msg = f"coverage_pct {coverage_pct}% is below threshold {threshold}% for feature_type '{feature_type}'"
                            if waive_coverage:
                                waivers.append(f"coverage: waived by --waive-coverage flag ({msg})")
                                warnings.append(f"WARNING (waived): {msg}")
                            else:
                                _fail(
                                    msg,
                                    "Apply --waive-coverage with justification, or re-run tests with coverage goal",
                                )

            if not _has_section(text, "## Test Output"):
                _fail(
                    "qa/evidence.md missing '## Test Output' section",
                    "Re-run the responsible skill targeting only the missing sections",
                )

    elif phase == "security":
        text = _require_file(artifact_path("security-review"))
        if text is not None:
            max_sev = _extract_field_value(text, "max_severity")
            if max_sev is None:
                _fail(
                    "qa/security-review.md missing '**max_severity:**' field",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            elif max_sev.lower() not in VALID_SEVERITY_LEVELS:
                _fail(
                    f"qa/security-review.md '**max_severity:**' value '{max_sev}' is not one of: {', '.join(sorted(VALID_SEVERITY_LEVELS))}",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            else:
                thresholds["max_severity"] = max_sev.lower()
                state_updates["max_severity"] = max_sev.lower()

            sign_off = _extract_field_value(text, "sign_off")
            if sign_off is None:
                _fail(
                    "qa/security-review.md missing '**sign_off:**' field",
                    "Re-run the responsible skill targeting only the missing sections",
                )

    elif phase == "deploy":
        text = _require_file(artifact_path("deploy-steps"))
        if text is not None:
            # Check ## Rollback section has ≥ 1 non-empty line of content
            if not _has_section(text, "## Rollback"):
                _fail(
                    "ops/deploy-steps.md missing '## Rollback' section",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            else:
                rollback_text = _extract_section_text(text, "## Rollback")
                non_empty = [l for l in rollback_text.splitlines() if l.strip()]
                if not non_empty:
                    _fail(
                        "ops/deploy-steps.md '## Rollback' section has no content (≥ 1 non-empty line required)",
                        "Re-run the responsible skill targeting only the missing sections",
                    )
            # Check ## Health Checks section has ≥ 1 non-empty line
            if not _has_section(text, "## Health Checks"):
                _fail(
                    "ops/deploy-steps.md missing '## Health Checks' section",
                    "Re-run the responsible skill targeting only the missing sections",
                )
            else:
                hc_text = _extract_section_text(text, "## Health Checks")
                non_empty = [l for l in hc_text.splitlines() if l.strip()]
                if not non_empty:
                    _fail(
                        "ops/deploy-steps.md '## Health Checks' section has no content (≥ 1 non-empty line required)",
                        "Re-run the responsible skill targeting only the missing sections",
                    )

    elif phase == "done":
        _require_file(artifact_path("verification-manifest"))
        state_updates["artifact_contract_met"] = True

    else:
        _fail(
            f"Unknown phase: '{phase}'",
            "Check phase name spelling (grill/prd/plan/build/review/qa/security/deploy/done)",
        )

    result = SealResult(
        passed=len(failures) == 0,
        failures=failures,
        recoveries=recoveries,
        warnings=warnings,
        artifacts=artifacts,
        thresholds=thresholds,
        waivers=waivers,
        state_updates=state_updates,
    )

    # Write manifest only on pass
    if result.passed:
        _write_manifest(phase, slug, issue_id, feature_dir, result)

    return result


# ---------------------------------------------------------------------------
# Verification manifest writer
# ---------------------------------------------------------------------------

def _write_manifest(
    phase: str,
    slug: str,
    issue_id: str,
    feature_dir: Path,
    result: SealResult,
) -> None:
    """Write/update ops/verification-manifest.json under feature_dir."""
    manifest_path = feature_dir / "ops" / "verification-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing manifest or create fresh
    existing: dict = {}
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    existing.setdefault("schema_version", "v3")
    existing.setdefault("feature_slug", slug)
    existing.setdefault("issue_id", issue_id)
    existing.setdefault("phases", {})

    existing["phases"][phase] = {
        "sealed_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": result.artifacts,
        "thresholds": result.thresholds,
        "waivers": result.waivers,
        "warnings": result.warnings,
    }

    if phase == "done":
        existing["artifact_contract_met"] = True

    manifest_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
