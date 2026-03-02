"""Reporting helpers for awake session summaries."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class FileHealth:
    file: str
    score: float
    long_lines: int = 0
    todo_count: int = 0
    parse_error: bool = False
    docstring_coverage: float = 1.0


@dataclass
class SessionReport:
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    prs_merged: int
    tests_added: int
    features_shipped: int
    nights_active: int
    file_health: list[FileHealth]
    notes: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()

    @property
    def overall_health(self) -> Optional[float]:
        if not self.file_health:
            return None
        return round(sum(f.score for f in self.file_health) / len(self.file_health), 1)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _datetime_to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def report_to_dict(report: SessionReport) -> dict[str, Any]:
    """
    Serialize a SessionReport to a plain dict (JSON-safe).

    Args:
        report: The SessionReport to serialize.

    Returns:
        A JSON-serializable dict.
    """
    d = asdict(report)
    d["start_time"] = _datetime_to_iso(report.start_time)
    d["end_time"] = _datetime_to_iso(report.end_time)
    return d


def report_from_dict(data: dict[str, Any]) -> SessionReport:
    """
    Deserialize a SessionReport from a plain dict.

    Args:
        data: Dict as produced by report_to_dict.

    Returns:
        A SessionReport instance.
    """
    data = dict(data)
    data["start_time"] = datetime.fromisoformat(data["start_time"])
    if data.get("end_time"):
        data["end_time"] = datetime.fromisoformat(data["end_time"])
    else:
        data["end_time"] = None
    data["file_health"] = [FileHealth(**fh) for fh in data.get("file_health", [])]
    return SessionReport(**data)


def save_report(report: SessionReport, path: str) -> None:
    """
    Write a SessionReport to a JSON file.

    Args:
        report: The report to save.
        path: Destination file path.
    """
    Path(path).write_text(
        json.dumps(report_to_dict(report), indent=2), encoding="utf-8"
    )


def load_report(path: str) -> SessionReport:
    """
    Load a SessionReport from a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        A SessionReport instance.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return report_from_dict(data)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


_HEALTH_THRESHOLDS = [(85, "Excellent"), (70, "Good"), (0, "Needs work")]


def _health_label(score: float) -> str:
    for threshold, label in _HEALTH_THRESHOLDS:
        if score >= threshold:
            return label
    return "Needs work"


def render_markdown_report(report: SessionReport) -> str:
    """
    Render a human-readable Markdown summary of a SessionReport.

    Args:
        report: The session report to render.

    Returns:
        A Markdown string.
    """
    lines = [
        f"# Session Report: {report.session_id}",
        "",
        f"**Start:** {report.start_time.isoformat()}",
    ]
    if report.end_time:
        lines.append(f"**End:** {report.end_time.isoformat()}")
        if report.duration_seconds is not None:
            mins = int(report.duration_seconds // 60)
            secs = int(report.duration_seconds % 60)
            lines.append(f"**Duration:** {mins}m {secs}s")
    lines += [
        "",
        "## Stats",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| PRs merged | {report.prs_merged} |",
        f"| Tests added | {report.tests_added} |",
        f"| Features shipped | {report.features_shipped} |",
        f"| Nights active | {report.nights_active} |",
    ]
    if report.overall_health is not None:
        label = _health_label(report.overall_health)
        lines.append(f"| Code health | {report.overall_health}% ({label}) |")

    if report.file_health:
        lines += [
            "",
            "## File Health",
            "",
            "| File | Score | Status | Issues |",
            "|------|-------|--------|--------|",
        ]
        for fh in report.file_health:
            issues = []
            if fh.long_lines:
                issues.append(f"{fh.long_lines} long lines")
            if fh.todo_count:
                issues.append(f"{fh.todo_count} TODOs")
            if fh.parse_error:
                issues.append("parse error")
            issue_str = ", ".join(issues) or "None"
            lines.append(
                f"| {fh.file} | {fh.score}% | {_health_label(fh.score)} | {issue_str} |"
            )

    if report.notes:
        lines += ["", "## Notes", "", report.notes]

    return "\n".join(lines) + "\n"
