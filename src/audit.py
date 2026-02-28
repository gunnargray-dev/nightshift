"""Comprehensive repo audit — Session 16.

``nightshift audit`` pulls together health, security, dead code, coverage map,
and complexity into a single unified report with an overall letter grade.

The audit intentionally re-uses existing analysis modules rather than
reimplementing checks, acting as an orchestrator / aggregator.  This means:

* Zero duplicated logic.
* Results are consistent with individual subcommand output.
* The audit grade is a weighted composite, not a separate heuristic.

Weighting
---------
Health score (src.health)        25 %
Security grade (src.security)    25 %
Dead code ratio (src.dead_code)  20 %
Coverage score (src.coverage_map) 20 %
Complexity (src.refactor CC)     10 %

Grade boundaries  A ≥ 90 · B ≥ 75 · C ≥ 60 · D ≥ 45 · F < 45
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from src.scoring import (
    score_to_grade as _score_to_grade_full,
    score_to_status as _score_to_status,
    score_to_overall_status as _overall_status,
)


def _grade(score: float) -> str:
    """Return a simple A/B/C/D/F grade (no +/- variants) for *score*."""
    return _score_to_grade_full(score, simple=True)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AuditSection:
    """Result for one dimension of the audit."""

    name: str
    score: float          # 0–100 normalised
    raw_value: str        # human-readable raw value (e.g. "B", "72/100", "3 dead")
    weight: float         # fraction of total weight (sums to 1.0 across all sections)
    status: str           # "pass" | "warn" | "fail"
    summary: str          # one-line explanation
    detail: Optional[str] = None  # optional extra detail lines

    def weighted_contribution(self) -> float:
        """Return *score* × *weight* — this section's contribution to the composite."""
        return self.score * self.weight

    def to_dict(self) -> dict:
        """Serialise this section to a plain dictionary."""
        return asdict(self)


@dataclass
class AuditReport:
    """Full audit report combining all dimensions."""

    sections: list[AuditSection]
    overall_score: float      # 0–100 weighted composite
    overall_grade: str        # A / B / C / D / F
    overall_status: str       # "healthy" | "needs-attention" | "critical"
    repo_path: str
    generated_at: str

    # convenience accessors
    @property
    def passes(self) -> list[AuditSection]:
        """Return all sections whose status is ``"pass"``."""
        return [s for s in self.sections if s.status == "pass"]

    @property
    def warnings(self) -> list[AuditSection]:
        """Return all sections whose status is ``"warn"``."""
        return [s for s in self.sections if s.status == "warn"]

    @property
    def failures(self) -> list[AuditSection]:
        """Return all sections whose status is ``"fail"``."""
        return [s for s in self.sections if s.status == "fail"]

    def to_dict(self) -> dict:
        """Serialise the full report to a plain dictionary (JSON-safe)."""
        d = asdict(self)
        d["passes"] = len(self.passes)
        d["warnings"] = len(self.warnings)
        d["failures"] = len(self.failures)
        return d

    def to_json(self) -> str:
        """Return the report serialised as a pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render the full audit report as a Markdown document."""
        lines: list[str] = []
        grade_emoji = {
            "A": "🏆", "B": "✅", "C": "⚠️", "D": "🔶", "F": "❌",
        }.get(self.overall_grade, "")
        lines.append(f"# Nightshift Comprehensive Audit\n")
        lines.append(f"**Generated:** {self.generated_at}  ")
        lines.append(f"**Repo:** `{self.repo_path}`\n")
        lines.append(
            f"## Overall Grade: {grade_emoji} **{self.overall_grade}**  "
            f"({self.overall_score:.1f}/100)\n"
        )

        status_map = {
            "healthy": "✅ Healthy",
            "needs-attention": "⚠️  Needs attention",
            "critical": "❌ Critical",
        }
        lines.append(f"**Status:** {status_map.get(self.overall_status, self.overall_status)}\n")

        # Summary bar
        lines.append(f"```")
        filled = int(self.overall_score / 5)
        bar = "█" * filled + "░" * (20 - filled)
        lines.append(f"[{bar}] {self.overall_score:.1f}%")
        lines.append(f"```\n")

        lines.append("## Dimension Breakdown\n")
        lines.append("| Dimension | Score | Raw | Weight | Status |")
        lines.append("|-----------|-------|-----|--------|--------|")
        for s in self.sections:
            status_icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(s.status, "")
            lines.append(
                f"| {s.name} | {s.score:.0f}/100 | {s.raw_value} "
                f"| {int(s.weight*100)}% | {status_icon} {s.status} |"
            )
        lines.append("")

        lines.append("## Details\n")
        for s in self.sections:
            icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(s.status, "")
            lines.append(f"### {icon} {s.name}")
            lines.append(f"- **Score:** {s.score:.0f}/100 (raw: {s.raw_value})")
            lines.append(f"- **Weight:** {int(s.weight*100)}% of composite")
            lines.append(f"- **Summary:** {s.summary}")
            if s.detail:
                lines.append(f"- **Detail:** {s.detail}")
            lines.append("")

        # Recommendations
        if self.failures or self.warnings:
            lines.append("## Recommendations\n")
            for s in self.failures:
                lines.append(f"- ❌ **Fix immediately — {s.name}:** {s.summary}")
            for s in self.warnings:
                lines.append(f"- ⚠️  **Improve — {s.name}:** {s.summary}")
            lines.append("")

        lines.append("---")
        lines.append("*Generated by `nightshift audit`*")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Score normalization helpers
# ---------------------------------------------------------------------------

def _security_grade_to_score(grade: str) -> float:
    """Convert letter grade A–F to 0–100 score."""
    return {"A": 95.0, "B": 82.0, "C": 68.0, "D": 50.0, "F": 25.0}.get(grade.upper(), 50.0)


def _coverage_avg_to_score(avg: float) -> float:
    """Coverage avg is already 0–100."""
    return max(0.0, min(100.0, avg))


def _dead_code_to_score(high_count: int, total_modules: int) -> float:
    """Fewer dead symbols = higher score."""
    if total_modules == 0:
        return 100.0
    # Penalise 5 pts per high-confidence dead symbol, capped at 100
    penalty = min(100.0, high_count * 5.0)
    return max(0.0, 100.0 - penalty)


def _complexity_to_score(avg_cc: float) -> float:
    """Lower cyclomatic complexity = higher score."""
    # CC ≤ 5 → 100, CC = 10 → 75, CC = 20 → 25, CC > 30 → 0
    if avg_cc <= 5:
        return 100.0
    if avg_cc <= 10:
        return 100.0 - (avg_cc - 5) * 5.0
    if avg_cc <= 20:
        return 75.0 - (avg_cc - 10) * 5.0
    return max(0.0, 25.0 - (avg_cc - 20) * 2.5)


# _score_to_status: imported from src.scoring as _score_to_status


# ---------------------------------------------------------------------------
# Main audit function
# ---------------------------------------------------------------------------

def run_audit(repo_path: Path) -> AuditReport:
    """Run the comprehensive audit and return an AuditReport."""
    import datetime

    sections: list[AuditSection] = []

    # ------------------------------------------------------------------
    # 1. Health (25 %)
    # ------------------------------------------------------------------
    try:
        from src.health import generate_health_report
        health = generate_health_report(repo_path=repo_path)
        h_score = float(health.overall_health_score)
        h_status = _score_to_status(h_score, warn_threshold=70, fail_threshold=50)
        sections.append(AuditSection(
            name="Code Health",
            score=h_score,
            raw_value=f"{h_score:.0f}/100",
            weight=0.25,
            status=h_status,
            summary=(
                f"{health.total_functions} functions, "
                f"{health.total_classes} classes, "
                f"doc coverage {health.docstring_coverage:.0%}"
            ),
        ))
    except Exception as exc:
        sections.append(AuditSection(
            name="Code Health",
            score=50.0,
            raw_value="error",
            weight=0.25,
            status="warn",
            summary=f"Could not run health check: {exc}",
        ))

    # ------------------------------------------------------------------
    # 2. Security (25 %)
    # ------------------------------------------------------------------
    try:
        from src.security import audit_security
        sec = audit_security(repo_path=repo_path)
        s_score = _security_grade_to_score(sec.grade)
        s_status = _score_to_status(s_score, warn_threshold=68, fail_threshold=50)
        high_count = sum(1 for f in sec.findings if f.severity == "HIGH")
        sections.append(AuditSection(
            name="Security",
            score=s_score,
            raw_value=f"Grade {sec.grade}",
            weight=0.25,
            status=s_status,
            summary=(
                f"{len(sec.findings)} findings "
                f"({high_count} HIGH, "
                f"{sum(1 for f in sec.findings if f.severity == 'MEDIUM')} MEDIUM)"
            ),
        ))
    except Exception as exc:
        sections.append(AuditSection(
            name="Security",
            score=50.0,
            raw_value="error",
            weight=0.25,
            status="warn",
            summary=f"Could not run security audit: {exc}",
        ))

    # ------------------------------------------------------------------
    # 3. Dead Code (20 %)
    # ------------------------------------------------------------------
    try:
        from src.dead_code import find_dead_code
        dc = find_dead_code(repo_path=repo_path)
        high_dead = len(dc.high_confidence)
        total_mods = len(list((repo_path / "src").glob("*.py"))) if (repo_path / "src").exists() else 1
        dc_score = _dead_code_to_score(high_dead, total_mods)
        dc_status = _score_to_status(dc_score, warn_threshold=70, fail_threshold=50)
        sections.append(AuditSection(
            name="Dead Code",
            score=dc_score,
            raw_value=f"{high_dead} dead symbols",
            weight=0.20,
            status=dc_status,
            summary=(
                f"{high_dead} high-confidence dead symbols, "
                f"{len(dc.items) - high_dead} medium-confidence"
            ),
        ))
    except Exception as exc:
        sections.append(AuditSection(
            name="Dead Code",
            score=75.0,
            raw_value="error",
            weight=0.20,
            status="warn",
            summary=f"Could not run dead code analysis: {exc}",
        ))

    # ------------------------------------------------------------------
    # 4. Test Coverage (20 %)
    # ------------------------------------------------------------------
    try:
        from src.coverage_map import build_coverage_map
        cov = build_coverage_map(repo_path=repo_path)
        cov_score = _coverage_avg_to_score(cov.avg_score)
        cov_status = _score_to_status(cov_score, warn_threshold=60, fail_threshold=40)
        no_tests = len(cov.modules_without_tests)
        sections.append(AuditSection(
            name="Test Coverage",
            score=cov_score,
            raw_value=f"{cov_score:.0f}/100 avg",
            weight=0.20,
            status=cov_status,
            summary=(
                f"{len(cov.entries)} modules analysed, "
                f"{no_tests} with no tests, "
                f"avg score {cov_score:.0f}/100"
            ),
        ))
    except Exception as exc:
        sections.append(AuditSection(
            name="Test Coverage",
            score=50.0,
            raw_value="error",
            weight=0.20,
            status="warn",
            summary=f"Could not run coverage map: {exc}",
        ))

    # ------------------------------------------------------------------
    # 5. Complexity (10 %)
    # ------------------------------------------------------------------
    try:
        from src.refactor import find_refactor_candidates
        candidates = find_refactor_candidates(repo_path=repo_path)
        # Estimate average CC from candidates that have cc_score
        cc_values = [c.complexity_score for c in candidates if hasattr(c, "complexity_score") and c.complexity_score]
        avg_cc = sum(cc_values) / len(cc_values) if cc_values else 5.0
        cx_score = _complexity_to_score(avg_cc)
        cx_status = _score_to_status(cx_score, warn_threshold=70, fail_threshold=50)
        critical = sum(1 for c in candidates if hasattr(c, "complexity_score") and c.complexity_score and c.complexity_score >= 20)
        sections.append(AuditSection(
            name="Complexity",
            score=cx_score,
            raw_value=f"avg CC {avg_cc:.1f}",
            weight=0.10,
            status=cx_status,
            summary=(
                f"{len(candidates)} refactor candidates, "
                f"{critical} with CC ≥ 20 (critical)"
            ),
        ))
    except Exception as exc:
        sections.append(AuditSection(
            name="Complexity",
            score=75.0,
            raw_value="error",
            weight=0.10,
            status="warn",
            summary=f"Could not compute complexity: {exc}",
        ))

    # ------------------------------------------------------------------
    # Composite score
    # ------------------------------------------------------------------
    overall = sum(s.weighted_contribution() for s in sections)

    return AuditReport(
        sections=sections,
        overall_score=round(overall, 2),
        overall_grade=_grade(overall),
        overall_status=_overall_status(overall),
        repo_path=str(repo_path),
        generated_at=datetime.datetime.now().isoformat(timespec="seconds"),
    )


def save_audit_report(report: AuditReport, out_path: Path) -> None:
    """Write markdown + JSON sidecar to *out_path*."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(report.to_json(), encoding="utf-8")
