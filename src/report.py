"""Repository health report generator."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .utils import run_cmd


@dataclass
class ReportConfig:
    """Configuration for report generation."""

    model: str = "gpt-4o-mini"
    format: str = "markdown"  # markdown | html | json
    since: Optional[str] = None  # git ref or ISO date
    include_sections: Optional[list[str]] = None  # None = all
    max_files: int = 100


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def _count_commits(repo: Path, since: Optional[str] = None) -> int:
    args = ["git", "log", "--oneline"]
    if since:
        args += [f"--since={since}"]
    try:
        out = run_cmd(args, cwd=repo)
        return len([l for l in out.splitlines() if l.strip()])
    except Exception:
        return 0


def _count_python_files(repo: Path) -> int:
    return len(list(repo.glob("**/*.py")))


def _count_test_files(repo: Path) -> int:
    return len(list(repo.glob("**/test_*.py"))) + len(list(repo.glob("**/*_test.py")))


def _top_contributors(repo: Path, n: int = 5) -> list[dict]:
    try:
        out = run_cmd(
            ["git", "log", "--format=%an", "--no-merges"],
            cwd=repo,
        )
        from collections import Counter
        counts = Counter(line.strip() for line in out.splitlines() if line.strip())
        return [{"author": a, "commits": c} for a, c in counts.most_common(n)]
    except Exception:
        return []


def _recent_activity(repo: Path, n: int = 10) -> list[dict]:
    try:
        out = run_cmd(
            [
                "git",
                "log",
                f"-{n}",
                "--format=%H|%an|%ae|%s|%ci",
                "--no-merges",
            ],
            cwd=repo,
        )
        activity = []
        for line in out.splitlines():
            parts = line.split("|", 4)
            if len(parts) == 5:
                activity.append(
                    {
                        "hash": parts[0][:7],
                        "author": parts[1],
                        "email": parts[2],
                        "subject": parts[3],
                        "date": parts[4],
                    }
                )
        return activity
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_markdown(data: dict) -> str:
    lines = [
        f"# Repository Health Report",
        f"",
        f"**Generated:** {data['generated_at']}",
        f"**Repository:** {data['repo']}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Python files | {data['python_files']} |",
        f"| Test files | {data['test_files']} |",
        f"| Commits | {data['commits']} |",
        f"",
    ]

    if data.get("top_contributors"):
        lines += ["## Top Contributors", ""]
        for c in data["top_contributors"]:
            lines.append(f"- **{c['author']}**: {c['commits']} commits")
        lines.append("")

    if data.get("recent_activity"):
        lines += ["## Recent Activity", ""]
        for a in data["recent_activity"]:
            lines.append(f"- `{a['hash']}` {a['subject']} ({a['author']}, {a['date'][:10]})")
        lines.append("")

    return "\n".join(lines)


def _render_json(data: dict) -> str:
    import json
    return json.dumps(data, indent=2, default=str)


def _render_html(data: dict) -> str:
    body = _render_markdown(data).replace("\n", "<br>")
    return f"<html><body>{body}</body></html>"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(
    repo: Path,
    config: Optional[ReportConfig] = None,
) -> str:
    """Generate a health report for *repo*."""
    from datetime import datetime

    cfg = config or ReportConfig()

    data = {
        "repo": str(repo),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "python_files": _count_python_files(repo),
        "test_files": _count_test_files(repo),
        "commits": _count_commits(repo, since=cfg.since),
        "top_contributors": _top_contributors(repo),
        "recent_activity": _recent_activity(repo),
    }

    if cfg.format == "json":
        return _render_json(data)
    if cfg.format == "html":
        return _render_html(data)
    return _render_markdown(data)
