"""
devflow migrate — v2 → v3 issue migration logic.

Called by: devflow sync <issue-id> --migrate-v3 [--apply]

Dry-run (default):
  - Maps v2 phase name to v3
  - Checks which artifacts are expected at the current phase
  - Reports what is present, missing, or partially complete
  - Writes migration-report.md locally
  - Makes NO state or Paperclip changes

--apply:
  - Stubs missing artifacts (preserves existing content)
  - Updates state document to v3 schema
  - Uploads stubs to Paperclip
  - Posts migration comment on issue
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Phase name mapping: v2 → v3
# ---------------------------------------------------------------------------

V2_TO_V3_PHASE: dict[str, str] = {
    "grill":  "grill",
    "prd":    "prd",
    "plan":   "plan",
    "build":  "build",
    "tdd":    "build",    # v2 alias
    "review": "review",
    "qa":     "qa",
    "deploy": "deploy",
    "done":   "done",
}

# Phases that imply prior phases are complete
_PHASE_IMPLIES_COMPLETE: dict[str, list[str]] = {
    "prd":     ["grill_complete"],
    "plan":    ["grill_complete", "prd_complete"],
    "build":   ["grill_complete", "prd_complete"],
    "review":  ["grill_complete", "prd_complete", "iron_law_met"],
    "qa":      ["grill_complete", "prd_complete", "iron_law_met", "review_passed"],
    "security":["grill_complete", "prd_complete", "iron_law_met", "review_passed"],
    "deploy":  ["grill_complete", "prd_complete", "iron_law_met", "review_passed"],
    "done":    ["grill_complete", "prd_complete", "iron_law_met", "review_passed",
                "artifact_contract_met"],
}

# Artifacts expected at each phase and beyond (cumulative)
# path relative to feature root
_PHASE_ARTIFACTS: dict[str, list[dict]] = {
    "grill":   [],
    "prd":     [{"path": "specs/prd.md",             "sections": ["## Goal", "## Background", "## Scope", "## Acceptance Criteria", "## Security Scope"]}],
    "plan":    [{"path": "specs/prd.md",             "sections": ["## Goal", "## Background", "## Scope", "## Acceptance Criteria", "## Security Scope"]},
                {"path": "plans/plan.md",            "sections": ["## Phases", "## ADRs", "## Rollback", "## Verification Commands"]}],
    "build":   [{"path": "specs/prd.md",             "sections": ["## Goal", "## Background", "## Scope", "## Acceptance Criteria", "## Security Scope"]},
                {"path": "plans/plan.md",            "sections": ["## Phases", "## ADRs", "## Rollback", "## Verification Commands"]},
                {"path": "build/tdd-summary.md",     "sections": ["## Test Output"]}],
    "review":  [{"path": "specs/prd.md",             "sections": ["## Goal", "## Background", "## Scope", "## Acceptance Criteria", "## Security Scope"]},
                {"path": "plans/plan.md",            "sections": ["## Phases", "## ADRs", "## Rollback", "## Verification Commands"]},
                {"path": "build/tdd-summary.md",     "sections": ["## Test Output"]},
                {"path": "ops/review-report.md",     "sections": ["## Checklist"]}],
    "qa":      [{"path": "specs/prd.md",             "sections": ["## Goal", "## Background", "## Scope", "## Acceptance Criteria", "## Security Scope"]},
                {"path": "plans/plan.md",            "sections": ["## Phases", "## ADRs", "## Rollback", "## Verification Commands"]},
                {"path": "build/tdd-summary.md",     "sections": ["## Test Output"]},
                {"path": "ops/review-report.md",     "sections": ["## Checklist"]},
                {"path": "qa/evidence.md",           "sections": ["## Test Output"]}],
    "deploy":  [{"path": "specs/prd.md",             "sections": ["## Goal", "## Background", "## Scope", "## Acceptance Criteria", "## Security Scope"]},
                {"path": "plans/plan.md",            "sections": ["## Phases", "## ADRs", "## Rollback", "## Verification Commands"]},
                {"path": "build/tdd-summary.md",     "sections": ["## Test Output"]},
                {"path": "ops/review-report.md",     "sections": ["## Checklist"]},
                {"path": "qa/evidence.md",           "sections": ["## Test Output"]},
                {"path": "ops/deploy-steps.md",      "sections": ["## Rollback", "## Health Checks"]}],
}
# security and done use deploy list
_PHASE_ARTIFACTS["security"] = _PHASE_ARTIFACTS["qa"]
_PHASE_ARTIFACTS["done"]     = _PHASE_ARTIFACTS["deploy"]

# Artifacts NOT yet due at a given phase (pending)
_ALL_ARTIFACT_PATHS = {
    "specs/prd.md", "plans/plan.md", "build/tdd-summary.md",
    "ops/review-report.md", "qa/evidence.md", "qa/security-review.md",
    "ops/deploy-steps.md", "ops/verification-manifest.json",
}


# ---------------------------------------------------------------------------
# Stub templates per artifact path
# ---------------------------------------------------------------------------

def _stub_content(path: str) -> str:
    """Return the full stub template for a given artifact path."""
    stubs = {
        "specs/prd.md": """\
# PRD: [STUB — migrated from v2, requires completion]

## Goal
<!-- TODO: describe the goal of this feature -->

## Background
<!-- TODO: describe background and motivation -->

## Scope
<!-- TODO: list what is in and out of scope -->

## Acceptance Criteria
<!-- TODO: numbered list of testable acceptance criteria -->
1.

## Security Scope
<!-- TODO: state whether security review is triggered and why -->
Not assessed — migrated from v2.
""",
        "plans/plan.md": """\
# Plan: [STUB — migrated from v2, requires completion]

## Phases
<!-- TODO: list implementation phases -->
1.

## ADRs
N/A — no architectural decisions recorded during migration.

## Rollback
<!-- TODO: describe how to undo this change in production -->
1.

## Verification Commands
<!-- TODO: commands to confirm the feature works post-deploy -->
```bash
# TODO
```
""",
        "build/tdd-summary.md": """\
# TDD Summary: [STUB — migrated from v2, requires completion]

**Timestamp:** <!-- TODO: ISO 8601 -->
**Plan source:** plans/plan.md
**Iron Law:** PENDING

## Phases completed
<!-- TODO -->

## Test results
<!-- TODO -->

## Test Output
<!-- TODO: paste verbatim test runner output here -->
```
STUB — requires completion
```

## Files touched
<!-- TODO -->

## Commands run
<!-- TODO -->

## Design notes
<!-- TODO -->
""",
        "ops/review-report.md": """\
# Review Report: [STUB — migrated from v2, requires completion]

**Decision:** PENDING
**Reviewer:** <!-- TODO -->
**Timestamp:** <!-- TODO: ISO 8601 -->

## Checklist
| Item | Status | Notes |
|---|---|---|
| Cognitive debt | PENDING | [STUB — migration] |
| OWASP scan | PENDING | [STUB — migration] |
| AC coverage | PENDING | [STUB — migration] |
| git blame | PENDING | [STUB — migration] |
| Iron Law | PENDING | [STUB — migration] |
| No over-engineering | PENDING | [STUB — migration] |

## Findings
<!-- TODO: list any FAIL items -->

## Acceptance Criteria Coverage
<!-- TODO -->
""",
        "qa/evidence.md": """\
# QA Evidence: [STUB — migrated from v2, requires completion]

**Tier:** <!-- TODO: 1, 2, or 3 -->
**coverage_pct:** <!-- TODO: numeric percentage -->

## Test Output
<!-- TODO: paste verbatim test runner output here -->
```
STUB — requires completion
```
""",
        "qa/security-review.md": """\
# Security Review: [STUB — migrated from v2, requires completion]

**max_severity:** none
**sign_off:** [STUB — migration]

## OWASP Checklist
<!-- TODO: complete security review -->
""",
        "ops/deploy-steps.md": """\
# Deploy Steps: [STUB — migrated from v2, requires completion]

**Deployed at:** <!-- TODO: ISO 8601 -->
**Environment:** <!-- TODO -->
**Branch:** <!-- TODO -->
**Commit:** <!-- TODO -->

## Steps Executed
<!-- TODO -->

## Health Checks
| Check | Command | Result |
|---|---|---|
| <!-- TODO --> | <!-- TODO --> | PENDING |

## Rollback
<!-- TODO: steps to revert if deploy fails -->
1.

## Verification Evidence
<!-- TODO -->

## Release Notes
### What changed
<!-- TODO -->
""",
    }
    return stubs.get(path, f"# [STUB — migrated from v2, requires completion]\n\n<!-- TODO: {path} -->\n")


def _stub_section(section: str) -> str:
    """Return a stub block for a single missing section."""
    return f"\n{section}\n<!-- [STUB — migration] TODO: complete this section -->\n"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ArtifactStatus:
    path: str
    status: str          # "present" | "partial" | "absent"
    missing_sections: list[str] = field(default_factory=list)
    stub_written: bool = False


@dataclass
class MigrateResult:
    issue_id: str
    slug: str
    v2_phase: str
    v3_phase: str
    artifacts: list[ArtifactStatus] = field(default_factory=list)
    pending_artifacts: list[str] = field(default_factory=list)   # not due at this phase
    state_updated: bool = False
    comment_posted: bool = False
    report_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Core migration logic
# ---------------------------------------------------------------------------

def migrate_issue(
    issue_id: str,
    slug: str,
    feature_dir: Path,
    v2_state: dict,
    apply: bool = False,
) -> MigrateResult:
    """
    Analyse a v2 issue and optionally apply v3 migration.

    Parameters
    ----------
    issue_id   : Paperclip issue UUID
    slug       : feature slug (used for report path and stub headers)
    feature_dir: local path to the feature root (features/<slug>/)
    v2_state   : raw state dict loaded from Paperclip (may be empty for new issues)
    apply      : if True, write stubs and prepare updated state

    Returns a MigrateResult. The caller (CLI) handles Paperclip writes when apply=True.
    """
    # 1. Map phase
    raw_phase = (v2_state.get("phase") or "").lower().strip()
    v3_phase = V2_TO_V3_PHASE.get(raw_phase, "prd")  # default to prd if unknown

    result = MigrateResult(
        issue_id=issue_id,
        slug=slug,
        v2_phase=raw_phase or "(none)",
        v3_phase=v3_phase,
    )

    # 2. Check artifacts expected at current phase
    expected = _PHASE_ARTIFACTS.get(v3_phase, [])
    expected_paths = {a["path"] for a in expected}

    for artifact in expected:
        path = artifact["path"]
        required_sections = artifact["sections"]
        local_file = feature_dir / path
        status = _check_artifact(local_file, required_sections)
        result.artifacts.append(status)

        if apply:
            if status.status == "absent":
                _write_stub(local_file, _stub_content(path))
                status.stub_written = True
            elif status.status == "partial":
                _fill_missing_sections(local_file, status.missing_sections)
                status.stub_written = True

    # 3. Identify pending artifacts (not due at this phase)
    result.pending_artifacts = sorted(_ALL_ARTIFACT_PATHS - expected_paths)

    # 4. Write migration report
    report = _build_report(result)
    report_path = feature_dir / "ops" / "migration-report.md"
    if apply:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        result.report_path = str(report_path)

    return result


def build_v3_state(v2_state: dict, v3_phase: str) -> dict:
    """
    Produce a v3-schema state document from the v2 state dict.
    Sets completion flags implied by the current phase.
    Preserves any v2 fields that map cleanly to v3.
    """
    implied = _PHASE_IMPLIES_COMPLETE.get(v3_phase, [])

    state: dict = {
        "schema_version": "v3",
        "phase": v3_phase,
        "feature_type": v2_state.get("feature_type", "new_feature"),
        "model_tier": v2_state.get("model_tier", ""),
        "model_tier_justification": v2_state.get("model_tier_justification", ""),
        "grill_complete": "grill_complete" in implied,
        "prd_complete": "prd_complete" in implied,
        "plan_approved": v2_state.get("plan_approved", False),
        "iron_law_met": "iron_law_met" in implied,
        "review_passed": "review_passed" in implied,
        "security_triggered": v2_state.get("security_triggered", False),
        "max_severity": v2_state.get("max_severity", "none"),
        "artifact_contract_met": "artifact_contract_met" in implied,
        "heartbeat_count": 0,
        "seal_failures": 0,
        "last_heartbeat_start": None,
        "last_read_comment_id": None,
        "waivers": [],
        "migrated_from_v2": True,
        "migration_date": datetime.now(timezone.utc).isoformat(),
    }
    return state


def build_migration_comment(result: MigrateResult) -> str:
    present = [a for a in result.artifacts if a.status == "present"]
    partial = [a for a in result.artifacts if a.status == "partial"]
    absent  = [a for a in result.artifacts if a.status == "absent"]

    lines = [
        "## v3 migration complete",
        "",
        f"- **v2 phase mapped:** `{result.v2_phase}` → `{result.v3_phase}`",
        f"- **Artifacts present:** {len(present)}",
        f"- **Artifacts partially completed (stubs filled):** {len(partial)}",
        f"- **Artifacts missing (full stubs written):** {len(absent)}",
        f"- **Artifacts pending (not due at this phase):** {len(result.pending_artifacts)}",
        "",
        "Next step: run `devflow gate --entering " + result.v3_phase + "` to verify the migration.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_artifact(local_file: Path, required_sections: list[str]) -> ArtifactStatus:
    path_str = str(local_file.name) if local_file.name else str(local_file)
    # Use the path relative to feature dir for display
    rel = "/".join(local_file.parts[-2:]) if len(local_file.parts) >= 2 else str(local_file)

    if not local_file.exists():
        return ArtifactStatus(path=rel, status="absent", missing_sections=required_sections)

    content = local_file.read_text(encoding="utf-8", errors="replace")
    missing = [s for s in required_sections if s not in content]

    if missing:
        return ArtifactStatus(path=rel, status="partial", missing_sections=missing)
    return ArtifactStatus(path=rel, status="present")


def _write_stub(local_file: Path, content: str) -> None:
    local_file.parent.mkdir(parents=True, exist_ok=True)
    local_file.write_text(content, encoding="utf-8")


def _fill_missing_sections(local_file: Path, missing_sections: list[str]) -> None:
    """Append stub blocks for missing sections to an existing file."""
    existing = local_file.read_text(encoding="utf-8", errors="replace")
    additions = "".join(_stub_section(s) for s in missing_sections)
    local_file.write_text(existing.rstrip() + "\n" + additions, encoding="utf-8")


def _build_report(result: MigrateResult) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Migration Report",
        f"**Issue:** {result.issue_id}",
        f"**Slug:** {result.slug}",
        f"**Date:** {ts}",
        f"**Phase:** v2 `{result.v2_phase}` → v3 `{result.v3_phase}`",
        "",
        "## Artifact Status",
        "",
        "| Artifact | Status | Missing sections | Stub written |",
        "|---|---|---|---|",
    ]
    for a in result.artifacts:
        missing_str = ", ".join(a.missing_sections) if a.missing_sections else "—"
        stubbed = "yes" if a.stub_written else "no"
        lines.append(f"| `{a.path}` | {a.status} | {missing_str} | {stubbed} |")

    lines += [
        "",
        "## Pending Artifacts (not due at this phase)",
        "",
    ]
    for p in result.pending_artifacts:
        lines.append(f"- `{p}`")

    lines += [
        "",
        "## Next Steps",
        "",
        f"1. Review any stub files and complete them",
        f"2. Run: `devflow gate --entering {result.v3_phase} --slug {result.slug}`",
    ]
    return "\n".join(lines) + "\n"
