"""
Artifact Publisher — WS7 of the ALDC integration plan.

Uploads phase artifacts to Paperclip documents and records the results in
ops/verification-manifest.json.

Design constraints:
  - Zero Paperclip dependency in the core publish logic.  The PaperclipClient
    (``pc``) is injected by the CLI layer; the rest of this module is pure I/O.
  - No new pip dependencies — stdlib + existing project deps only.
  - Exit contract: publish_artifacts() returns PublishResult; CLI exits 0 on
    full success, 1 if any critical artifact failed to upload.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Artifact map
# ---------------------------------------------------------------------------

PHASE_ARTIFACTS: dict[str, list[dict]] = {
    "grill": [],
    "prd": [
        {"key": "prd", "path": "specs/prd.md", "critical": False},
    ],
    "plan": [
        {"key": "plan", "path": "plans/plan.md", "critical": False},
        {"key": "architecture", "path": "ops/architecture.md", "critical": False},
    ],
    "build": [
        {"key": "tdd-summary", "path": "build/tdd-summary.md", "critical": False},
    ],
    "review": [
        {"key": "review-report", "path": "ops/review-report.md", "critical": True},
    ],
    "qa": [
        {"key": "qa-evidence", "path": "qa/evidence.md", "critical": False},
    ],
    "security": [
        {"key": "security-review", "path": "qa/security-review.md", "critical": True},
    ],
    "deploy": [
        {"key": "deploy-steps", "path": "ops/deploy-steps.md", "critical": False},
        {"key": "verification-manifest", "path": "ops/verification-manifest.json", "critical": True},
    ],
    "done": [
        {"key": "verification-manifest", "path": "ops/verification-manifest.json", "critical": True},
    ],
}

# Severity levels in ascending order (matches gatekeeper.py).
_SEVERITY_ORDER = ["none", "low", "medium", "high", "critical"]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class UploadRecord:
    key: str
    path: str
    revision_id: str
    status: str          # "ok" | "missing" | "failed"
    error: str = ""


@dataclass
class PublishResult:
    phase: str
    uploads: list[UploadRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    critical_failures: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.critical_failures) == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_file(path: Path) -> Optional[str]:
    """Return file text or None if missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _extract_max_severity(text: str) -> str:
    """
    Read ``**max_severity:** <value>`` from a markdown file.
    Returns the value in lowercase, or "none" if the field is absent.
    """
    pattern = re.compile(r"\*\*max_severity\*\*\s*:?\s*(\S+)", re.IGNORECASE)
    m = pattern.search(text)
    if m:
        return m.group(1).strip().lower()
    return "none"


def _severity_at_least_medium(severity: str) -> bool:
    """Return True when severity >= medium."""
    try:
        return _SEVERITY_ORDER.index(severity) >= _SEVERITY_ORDER.index("medium")
    except ValueError:
        return True  # unknown severity → treat as medium+


def _is_critical(artifact: dict, local_text: Optional[str]) -> bool:
    """
    Resolve the effective critical flag for an artifact.

    For security-review the spec says: critical only when max_severity >= medium.
    All others use the static flag in PHASE_ARTIFACTS.
    """
    if artifact["key"] == "security-review" and local_text is not None:
        severity = _extract_max_severity(local_text)
        return _severity_at_least_medium(severity)
    return bool(artifact["critical"])


# ---------------------------------------------------------------------------
# Core publish logic  (no Paperclip import — pc is injected)
# ---------------------------------------------------------------------------

async def publish_artifacts(
    issue_id: str,
    slug: str,
    phase: str,
    feature_dir: Path,
    pc,  # PaperclipClient — passed in; no import here
) -> PublishResult:
    """
    Upload all artifacts defined for ``phase`` to Paperclip and record the
    results in ops/verification-manifest.json.

    Parameters
    ----------
    issue_id     : Paperclip issue UUID
    slug         : feature slug (used in manifest header)
    phase        : pipeline phase name (grill/prd/plan/…)
    feature_dir  : absolute Path to the feature root (e.g. features/<slug>/)
    pc           : PaperclipClient instance (already open as async context)

    Returns
    -------
    PublishResult — .success is False if any critical artifact failed.
    """
    result = PublishResult(phase=phase)

    artifacts = PHASE_ARTIFACTS.get(phase, [])
    if not artifacts:
        return result

    for artifact in artifacts:
        key: str = artifact["key"]
        rel_path: str = artifact["path"]
        local_path = feature_dir / rel_path
        local_text = _read_file(local_path)
        effective_critical = _is_critical(artifact, local_text)

        # ── 1. File existence check ──────────────────────────────────────────
        if local_text is None:
            msg = f"artifact missing: {rel_path}"
            record = UploadRecord(
                key=key,
                path=rel_path,
                revision_id="",
                status="missing",
                error=msg,
            )
            result.uploads.append(record)
            if effective_critical:
                result.critical_failures.append(msg)
                await _post_blocking_comment(pc, issue_id, key, msg)
            else:
                result.warnings.append(f"[non-critical] {msg}")
            continue

        # ── 2–4. Upload with conflict retry ──────────────────────────────────
        upload_record = await _upload_with_retry(
            pc=pc,
            issue_id=issue_id,
            key=key,
            rel_path=rel_path,
            content=local_text,
        )
        result.uploads.append(upload_record)

        # ── 5. Handle persistent failure ─────────────────────────────────────
        if upload_record.status == "failed":
            msg = f"upload failed for {key} ({rel_path}): {upload_record.error}"
            if effective_critical:
                result.critical_failures.append(msg)
                await _post_blocking_comment(pc, issue_id, key, upload_record.error)
            else:
                result.warnings.append(f"[non-critical] {msg}")

    # ── 6. Update verification-manifest.json ─────────────────────────────────
    _update_manifest(
        feature_dir=feature_dir,
        slug=slug,
        issue_id=issue_id,
        phase=phase,
        result=result,
    )

    return result


async def _fetch_revision_id(pc, issue_id: str, key: str) -> Optional[str]:
    """GET /api/issues/{id}/documents/{key} and return its revisionId."""
    try:
        doc = await pc.get_document(issue_id, key)
        return doc.get("revisionId") or doc.get("revision_id")
    except Exception:
        return None


async def _upload_with_retry(
    pc,
    issue_id: str,
    key: str,
    rel_path: str,
    content: str,
    max_attempts: int = 3,
) -> UploadRecord:
    """
    PUT the document to Paperclip.

    Retry strategy:
      - On 409 conflict: re-fetch revisionId, retry once.
      - On any other error: retry up to max_attempts total.
      - After max_attempts failures: return a failed UploadRecord.
    """
    # Determine format from file extension.
    fmt = "json" if rel_path.endswith(".json") else "markdown"
    # Use the key as the document title (human-readable).
    title = key.replace("-", " ").title()

    revision_id = await _fetch_revision_id(pc, issue_id, key)
    last_error = ""

    for attempt in range(max_attempts):
        try:
            doc = await pc.put_document(
                issue_id=issue_id,
                key=key,
                title=title,
                body=content,
                format=fmt,
                base_revision_id=revision_id,
            )
            new_revision_id = (
                doc.get("revisionId") or doc.get("revision_id") or revision_id or ""
            )
            return UploadRecord(
                key=key,
                path=rel_path,
                revision_id=new_revision_id,
                status="ok",
            )
        except Exception as exc:
            last_error = str(exc)
            # Detect 409 conflict by inspecting the exception message.
            is_conflict = "409" in last_error or "conflict" in last_error.lower()
            if is_conflict:
                # Re-fetch revisionId and retry once.
                revision_id = await _fetch_revision_id(pc, issue_id, key)
                continue
            # For non-conflict errors, let the retry loop handle it.

    return UploadRecord(
        key=key,
        path=rel_path,
        revision_id="",
        status="failed",
        error=last_error,
    )


async def _post_blocking_comment(pc, issue_id: str, key: str, error: str) -> None:
    """Post a blocking comment on the Paperclip issue for a critical failure."""
    try:
        await pc.post_comment(
            issue_id,
            f"## publish-artifacts: BLOCKED\n\n"
            f"Critical artifact **{key}** failed to upload.\n\n"
            f"**Error:** {error}\n\n"
            f"Resolve the issue and re-run `devflow publish-artifacts` before proceeding.",
        )
    except Exception:
        pass  # best-effort; don't mask the original failure


# ---------------------------------------------------------------------------
# Manifest update
# ---------------------------------------------------------------------------

def _update_manifest(
    feature_dir: Path,
    slug: str,
    issue_id: str,
    phase: str,
    result: PublishResult,
) -> None:
    """
    Merge a ``published`` record for ``phase`` into
    ops/verification-manifest.json without overwriting existing sealed-phase
    data.
    """
    manifest_path = feature_dir / "ops" / "verification-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

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
    existing["phases"].setdefault(phase, {})

    existing["phases"][phase]["published_at"] = datetime.now(timezone.utc).isoformat()
    existing["phases"][phase]["uploads"] = [
        {
            "key": u.key,
            "path": u.path,
            "revision_id": u.revision_id,
            "status": u.status,
            **({"error": u.error} if u.error else {}),
        }
        for u in result.uploads
    ]

    if result.warnings:
        existing["phases"][phase].setdefault("warnings", [])
        existing["phases"][phase]["warnings"].extend(result.warnings)

    manifest_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
