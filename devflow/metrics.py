"""
devflow/metrics.py — Aggregate verification-manifest.json data.

Importable standalone; no Paperclip dependency.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import mean
from typing import Optional


# ---------------------------------------------------------------------------
# CEO threshold defaults (overridable via env vars)
# ---------------------------------------------------------------------------

CEO_IRON_LAW_MIN = float(os.environ.get("CEO_IRON_LAW_MIN", "80"))
CEO_ARTIFACT_CONTRACT_MIN = float(os.environ.get("CEO_ARTIFACT_CONTRACT_MIN", "100"))

# Severity ordering for "≥ high" check
_SEVERITY_ORDER = ["none", "info", "low", "medium", "high", "critical"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _severity_gte_high(severity: str) -> bool:
    """Return True if severity is high or critical."""
    try:
        return _SEVERITY_ORDER.index(severity.lower()) >= _SEVERITY_ORDER.index("high")
    except ValueError:
        return False


def _derive_metrics(manifest: dict) -> dict:
    """
    Derive per-feature metrics from a verification-manifest dict.

    Returns a dict with keys:
      slug, schema_version, migrated,
      artifact_contract_met, iron_law_met,
      coverage_pct, max_security_severity,
      waivers, warnings,
      seal_failures_per_phase
    """
    phases: dict = manifest.get("phases", {})

    # iron_law_met — from build phase thresholds
    build_phase = phases.get("build", {})
    build_thresholds = build_phase.get("thresholds", {})
    iron_law_met: Optional[bool] = build_thresholds.get("iron_law_met", None)

    # coverage_pct — from qa phase thresholds
    qa_phase = phases.get("qa", {})
    qa_thresholds = qa_phase.get("thresholds", {})
    coverage_pct = qa_thresholds.get("coverage_pct", None)

    # max_security_severity — prefer security phase, fall back to qa
    security_phase = phases.get("security", {})
    security_thresholds = security_phase.get("thresholds", {})
    if "max_severity" in security_thresholds:
        max_severity = security_thresholds["max_severity"]
    elif "max_severity" in qa_thresholds:
        max_severity = qa_thresholds["max_severity"]
    else:
        max_severity = None

    # Collect waivers and warnings across all phases
    all_waivers: list = []
    all_warnings: list = []
    seal_failures_per_phase: dict[str, int] = {}

    for phase_name, phase_data in phases.items():
        waivers = phase_data.get("waivers", [])
        warnings = phase_data.get("warnings", [])
        all_waivers.extend(waivers)
        all_warnings.extend(warnings)
        if warnings:
            seal_failures_per_phase[phase_name] = len(warnings)

    # artifact_contract_met — top-level field or derived from phases present
    artifact_contract_met = manifest.get("artifact_contract_met", None)
    if artifact_contract_met is None:
        # Derive: consider met if at least one phase sealed with no waivers that
        # indicate hard failures. Simple heuristic: phases dict is non-empty.
        artifact_contract_met = len(phases) > 0

    schema_version = manifest.get("schema_version")
    migrated = schema_version == "v3-migrated"

    return {
        "slug": manifest.get("feature_slug", "<unknown>"),
        "schema_version": schema_version,
        "migrated": migrated,
        "artifact_contract_met": artifact_contract_met,
        "iron_law_met": iron_law_met,
        "coverage_pct": coverage_pct,
        "max_security_severity": max_severity,
        "waivers": all_waivers,
        "warnings": all_warnings,
        "seal_failures_per_phase": seal_failures_per_phase,
    }


# ---------------------------------------------------------------------------
# Per-feature report
# ---------------------------------------------------------------------------

def report_slug(slug: str, scan_root: Path) -> dict:
    """
    Load and return metrics for a single feature slug.
    Raises FileNotFoundError if manifest is missing.
    """
    manifest_path = scan_root / "features" / slug / "ops" / "verification-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return _derive_metrics(manifest)


def print_slug_report(metrics: dict) -> None:
    """Print a per-feature metrics report to stdout."""
    slug = metrics["slug"]
    print(f"Feature: {slug}")
    if metrics.get("migrated"):
        print("  [migrated: v3-migrated]")

    acm = metrics["artifact_contract_met"]
    print(f"  artifact_contract_met : {str(acm).lower() if isinstance(acm, bool) else acm}")

    ilm = metrics["iron_law_met"]
    print(f"  iron_law_met          : {str(ilm).lower() if isinstance(ilm, bool) else ('N/A' if ilm is None else ilm)}")

    cov = metrics["coverage_pct"]
    print(f"  coverage_pct          : {cov if cov is not None else 'N/A'}")

    sev = metrics["max_security_severity"]
    print(f"  max_security_severity : {sev if sev is not None else 'N/A'}")

    waivers = metrics["waivers"]
    print(f"  waivers               : {len(waivers)}")
    for w in waivers:
        print(f"    - {w}")

    warnings = metrics["warnings"]
    print(f"  warnings              : {len(warnings)}")

    sfpp = metrics["seal_failures_per_phase"]
    if sfpp:
        print("  seal_failures_per_phase:")
        for phase, count in sfpp.items():
            print(f"    {phase}: {count}")


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def compute_summary(scan_root: Path) -> dict:
    """
    Scan features/*/ops/verification-manifest.json under scan_root.
    Excludes manifests with schema_version: null (unmigrated pre-v3).
    Returns a summary dict.
    """
    import glob as _glob

    pattern = str(scan_root / "features" / "*" / "ops" / "verification-manifest.json")
    manifest_paths = _glob.glob(pattern)

    all_metrics: list[dict] = []
    skipped_null_schema: int = 0

    for path in sorted(manifest_paths):
        try:
            manifest = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue

        schema_version = manifest.get("schema_version")
        if schema_version is None:
            skipped_null_schema += 1
            continue  # exclude unmigrated pre-v3

        all_metrics.append(_derive_metrics(manifest))

    total = len(all_metrics)

    if total == 0:
        return {
            "total_features": 0,
            "skipped_null_schema": skipped_null_schema,
            "iron_law_compliance_pct": None,
            "artifact_contract_compliance_pct": None,
            "avg_coverage_pct": None,
            "waiver_rate_pct": None,
            "security_escalations_pct": None,
            "seal_failures_per_phase": {},
            "migrated_count": 0,
            "features": [],
        }

    iron_law_met_count = sum(1 for m in all_metrics if m["iron_law_met"] is True)
    artifact_met_count = sum(1 for m in all_metrics if m["artifact_contract_met"] is True)

    coverage_values = [m["coverage_pct"] for m in all_metrics if m["coverage_pct"] is not None]
    avg_coverage = mean(coverage_values) if coverage_values else None

    waiver_count = sum(len(m["waivers"]) for m in all_metrics)
    features_with_waivers = sum(1 for m in all_metrics if len(m["waivers"]) > 0)

    security_escalations = sum(
        1 for m in all_metrics
        if m["max_security_severity"] is not None and _severity_gte_high(m["max_security_severity"])
    )

    # Aggregate seal failures per phase
    agg_failures: dict[str, int] = {}
    for m in all_metrics:
        for phase, count in m["seal_failures_per_phase"].items():
            agg_failures[phase] = agg_failures.get(phase, 0) + count

    migrated_count = sum(1 for m in all_metrics if m["migrated"])

    return {
        "total_features": total,
        "skipped_null_schema": skipped_null_schema,
        "iron_law_compliance_pct": round(iron_law_met_count / total * 100, 1),
        "artifact_contract_compliance_pct": round(artifact_met_count / total * 100, 1),
        "avg_coverage_pct": round(avg_coverage, 1) if avg_coverage is not None else None,
        "waiver_rate_pct": round(features_with_waivers / total * 100, 1),
        "security_escalations_pct": round(security_escalations / total * 100, 1),
        "seal_failures_per_phase": agg_failures,
        "migrated_count": migrated_count,
        "features": all_metrics,
    }


def print_summary_report(summary: dict) -> None:
    """Print summary metrics to stdout."""
    total = summary["total_features"]
    skipped = summary["skipped_null_schema"]

    print(f"devflow metrics — summary ({total} features")
    if skipped:
        print(f"  [{skipped} manifest(s) excluded: schema_version=null / unmigrated pre-v3]")
    if summary["migrated_count"]:
        print(f"  [{summary['migrated_count']} migrated (v3-migrated) feature(s) included, tagged migrated=true]")
    print(")")

    if total == 0:
        print("  No qualifying manifests found.")
        return

    def _fmt(val, suffix=""):
        return f"{val}{suffix}" if val is not None else "N/A"

    il = summary["iron_law_compliance_pct"]
    ac = summary["artifact_contract_compliance_pct"]
    cov = summary["avg_coverage_pct"]
    wr = summary["waiver_rate_pct"]
    se = summary["security_escalations_pct"]

    print(f"  Iron Law compliance           : {_fmt(il, '%')}  (target ≥ 90%)")
    print(f"  Artifact contract compliance  : {_fmt(ac, '%')}  (target 100%)")
    print(f"  Avg coverage                  : {_fmt(cov, '%')}  (target ≥ 70%)")
    print(f"  Waiver rate                   : {_fmt(wr, '%')}  (target < 20%)")
    print(f"  Security escalations          : {_fmt(se, '%')}  (track only)")

    sfpp = summary["seal_failures_per_phase"]
    if sfpp:
        print("  Seal failures per phase:")
        for phase, count in sorted(sfpp.items()):
            print(f"    {phase}: {count}")

    # CEO threshold checks
    _check_ceo_thresholds(summary)


def _check_ceo_thresholds(summary: dict) -> None:
    """Print CEO alerts if compliance drops below configured thresholds."""
    il = summary["iron_law_compliance_pct"]
    ac = summary["artifact_contract_compliance_pct"]

    if il is not None and il < CEO_IRON_LAW_MIN:
        print(f"[CEO ALERT] Iron Law compliance below threshold ({il}% < {CEO_IRON_LAW_MIN}%)")

    if ac is not None and ac < CEO_ARTIFACT_CONTRACT_MIN:
        print(f"[CEO ALERT] Artifact contract compliance below threshold ({ac}% < {CEO_ARTIFACT_CONTRACT_MIN}%)")


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------

def build_markdown_report(summary: dict) -> str:
    """Return a markdown string for the summary report."""
    total = summary["total_features"]
    skipped = summary["skipped_null_schema"]
    lines: list[str] = []

    lines.append("# devflow Metrics Report")
    lines.append("")
    lines.append(f"**Features analysed:** {total}")
    if skipped:
        lines.append(f"**Excluded (null schema_version):** {skipped}")
    if summary["migrated_count"]:
        lines.append(f"**Migrated (v3-migrated):** {summary['migrated_count']} (tagged `migrated: true`)")
    lines.append("")

    def _fmt(val, suffix=""):
        return f"{val}{suffix}" if val is not None else "N/A"

    lines.append("## Summary Metrics")
    lines.append("")
    lines.append("| Metric | Value | Target |")
    lines.append("|---|---|---|")
    lines.append(f"| Iron Law compliance | {_fmt(summary['iron_law_compliance_pct'], '%')} | ≥ 90% |")
    lines.append(f"| Artifact contract compliance | {_fmt(summary['artifact_contract_compliance_pct'], '%')} | 100% |")
    lines.append(f"| Avg coverage | {_fmt(summary['avg_coverage_pct'], '%')} | ≥ 70% |")
    lines.append(f"| Waiver rate | {_fmt(summary['waiver_rate_pct'], '%')} | < 20% |")
    lines.append(f"| Security escalations | {_fmt(summary['security_escalations_pct'], '%')} | Track only |")
    lines.append("")

    sfpp = summary["seal_failures_per_phase"]
    if sfpp:
        lines.append("## Seal Failures per Phase")
        lines.append("")
        lines.append("| Phase | Failures |")
        lines.append("|---|---|")
        for phase, count in sorted(sfpp.items()):
            lines.append(f"| {phase} | {count} |")
        lines.append("")

    # CEO alerts
    il = summary["iron_law_compliance_pct"]
    ac = summary["artifact_contract_compliance_pct"]
    alerts: list[str] = []
    if il is not None and il < CEO_IRON_LAW_MIN:
        alerts.append(f"**[CEO ALERT]** Iron Law compliance below threshold ({il}% < {CEO_IRON_LAW_MIN}%)")
    if ac is not None and ac < CEO_ARTIFACT_CONTRACT_MIN:
        alerts.append(f"**[CEO ALERT]** Artifact contract compliance below threshold ({ac}% < {CEO_ARTIFACT_CONTRACT_MIN}%)")
    if alerts:
        lines.append("## CEO Alerts")
        lines.append("")
        for alert in alerts:
            lines.append(f"- {alert}")
        lines.append("")

    # Per-feature table
    features = summary.get("features", [])
    if features:
        lines.append("## Per-Feature Detail")
        lines.append("")
        lines.append("| Feature | Iron Law | Artifact Contract | Coverage | Max Severity | Waivers | Migrated |")
        lines.append("|---|---|---|---|---|---|---|")
        for m in features:
            ilm = str(m["iron_law_met"]).lower() if isinstance(m["iron_law_met"], bool) else "N/A"
            acm = str(m["artifact_contract_met"]).lower() if isinstance(m["artifact_contract_met"], bool) else "N/A"
            cov = f"{m['coverage_pct']}%" if m["coverage_pct"] is not None else "N/A"
            sev = m["max_security_severity"] or "N/A"
            wc = len(m["waivers"])
            mig = "yes" if m["migrated"] else "no"
            lines.append(f"| {m['slug']} | {ilm} | {acm} | {cov} | {sev} | {wc} | {mig} |")
        lines.append("")

    return "\n".join(lines)
