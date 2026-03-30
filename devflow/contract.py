"""
devflow contract — single source of truth for the artifact contract.

All pipeline artifacts, their local paths, Paperclip document keys,
upload criticality, and required sections are defined here.

Both ``gatekeeper.py`` (gate/seal validation) and ``artifact_publisher.py``
(Paperclip uploads) import from this module so a path or key change only
needs to happen in one place.

TODO: longer-term, ingest docs/artifact-contract.md directly so the markdown
      table is the authoritative source and this module regenerates from it.
      For now the dict below mirrors §15 of docs/aldc-integration-plan-v0.6.md.
"""
from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Canonical artifact definitions
# ---------------------------------------------------------------------------
# Fields:
#   key              : Paperclip document key (used in PUT /documents/<key>)
#   path             : local path relative to feature root (features/<slug>/)
#   blocking_upload  : True  → upload failure posts a blocking comment + exit 1
#                      False → upload failure is a warning only
#                      Note: security-review criticality is resolved dynamically
#                            by artifact_publisher based on max_severity
#   connector_only   : True  → only included when feature_type == "connector"
#   required_sections: markdown ## headings that seal validates are present

ARTIFACTS: dict[str, dict] = {
    "prd": {
        "key": "prd",
        "path": "specs/prd.md",
        "blocking_upload": False,
        "connector_only": False,
        "required_sections": [
            "## Goal",
            "## Background",
            "## Scope",
            "## Acceptance Criteria",
            "## Security Scope",
        ],
    },
    "plan": {
        "key": "plan",
        "path": "plans/plan.md",
        "blocking_upload": False,
        "connector_only": False,
        "required_sections": [
            "## Phases",
            "## ADRs",
            "## Rollback",
            "## Verification Commands",
        ],
    },
    "architecture": {
        "key": "architecture",
        "path": "ops/architecture.md",
        "blocking_upload": False,
        "connector_only": False,
        "required_sections": [],
    },
    "tdd-summary": {
        "key": "tdd-summary",
        "path": "build/tdd-summary.md",
        "blocking_upload": False,
        "connector_only": False,
        "required_sections": ["## Test Output"],
    },
    "review-report": {
        "key": "review-report",
        "path": "ops/review-report.md",
        "blocking_upload": True,
        "connector_only": False,
        "required_sections": ["## Checklist"],
    },
    "qa-evidence": {
        "key": "qa-evidence",
        "path": "qa/evidence.md",
        "blocking_upload": False,
        "connector_only": False,
        "required_sections": ["## Test Output"],
    },
    "security-review": {
        "key": "security-review",
        "path": "qa/security-review.md",
        # Dynamic: artifact_publisher resolves criticality based on max_severity >= medium.
        # Set True here as the safe default; publisher overrides when reading the file.
        "blocking_upload": True,
        "connector_only": False,
        "required_sections": [],
    },
    "deploy-steps": {
        "key": "deploy-steps",
        "path": "ops/deploy-steps.md",
        "blocking_upload": False,
        "connector_only": False,
        "required_sections": ["## Rollback", "## Health Checks"],
    },
    "verification-manifest": {
        "key": "verification-manifest",
        "path": "ops/verification-manifest.json",
        "blocking_upload": True,
        "connector_only": False,
        "required_sections": [],
    },
    "connector-checklist": {
        "key": "connector-checklist",
        "path": "ops/connector-checklist.md",
        "blocking_upload": False,
        "connector_only": True,
        "required_sections": [],
    },
}


# Phase → ordered list of artifact keys produced/published at that phase.
# Connector-only artifacts are included here; callers use artifacts_for_phase()
# to filter them by feature_type.
PHASE_ARTIFACT_KEYS: dict[str, list[str]] = {
    "grill":    [],
    "prd":      ["prd"],
    "plan":     ["plan", "architecture"],
    "build":    ["tdd-summary"],
    "review":   ["review-report"],
    "qa":       ["qa-evidence"],
    "security": ["security-review"],
    "deploy":   ["deploy-steps", "verification-manifest"],
    "done":     ["verification-manifest"],
}

PHASES: list[str] = list(PHASE_ARTIFACT_KEYS)


# ---------------------------------------------------------------------------
# Accessor helpers
# ---------------------------------------------------------------------------

def artifact_path(key: str) -> str:
    """
    Return the local file path (relative to feature root) for an artifact key.

    Raises KeyError for unknown keys — callers should use known keys only.
    """
    return ARTIFACTS[key]["path"]


def artifacts_for_phase(
    phase: str,
    feature_type: str = "new_feature",
) -> list[dict]:
    """
    Return the list of artifact dicts for a phase, filtered by feature_type.

    Connector-only artifacts are excluded unless feature_type == "connector".
    Returns copies so callers cannot mutate the canonical definitions.
    """
    keys = PHASE_ARTIFACT_KEYS.get(phase, [])
    result = []
    for k in keys:
        a = ARTIFACTS[k]
        if a["connector_only"] and feature_type != "connector":
            continue
        result.append(dict(a))  # shallow copy
    return result


def required_sections(key: str) -> list[str]:
    """Return the required markdown sections for an artifact (for seal validation)."""
    return list(ARTIFACTS[key].get("required_sections", []))


def is_blocking_upload(key: str) -> bool:
    """Return the default blocking_upload flag for an artifact."""
    return bool(ARTIFACTS[key].get("blocking_upload", False))
