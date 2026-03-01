"""Git blame integration for Awake.

Attributes human vs AI contribution per file and across the whole repo.
Awake commits are identified by the author name/email pattern
``Computer`` (the autonomous AI author used throughout sessions).

Public API
----------
- ``BlameEntry`` — per-line blame record (author, commit, line)
- ``FileBlame``  — aggregated human/AI stats for one file
- ``BlameReport`` — repo-wide attribution report
- ``analyze_blame(repo_path)`` → ``BlameReport``
- ``save_blame_report(report, out)``

CLI
---
    awake blame [--write] [--json]
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Author names / email fragments that identify the AI operator.
_AI_AUTHOR_PATTERNS = [
    re.compile(r"computer", re.IGNORECASE),
    re.compile(r"awake", re.IGNORECASE),
    re.compile(r"gunnar@perplexity", re.IGNORECASE),
]


def _is_ai_author(author: str) -> bool:
    """Return True if the author name/email looks like the AI operator."""
    return any(pat.search(author) for pat in _AI_AUTHOR_PATTERNS)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FileBlame:
    """Human vs AI contribution stats for a single file."""

    path: str
    total_lines: int = 0
    ai_lines: int = 0
    human_lines: int = 0
    ai_authors: list[str] = field(default_factory=list)
    human_authors: list[str] = field(default_factory=list)

    # ---------------------------------------------------------------------------
    # Derived metrics
    # ---------------------------------------------------------------------------

    @property
    def ai_pct(self) -> float:
        """Percentage of lines attributed to AI."""
        if self.total_lines == 0:
            return 0.0
        return round(self.ai_lines / self.total_lines * 100, 1)

    @property
    def human_pct(self) -> float:
        """Percentage of lines attributed to humans."""
        if self.total_lines == 0:
            return 0.0
        return round(self.human_lines / self.total_lines * 100, 1)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "path": self.path,
            "total_lines": self.total_lines,
            "ai_lines": self.ai_lines,
            "human_lines": self.human_lines,
            "ai_pct": self.ai_pct,
            "human_pct": self.human_pct,
            "ai_authors": sorted(set(self.ai_authors)),
            "human_authors": sorted(set(self.human_authors)),
        }


@dataclass
class BlameReport:
    """Repo-wide attribution report across all tracked Python source files."""

    files: list[FileBlame] = field(default_factory=list)
    repo_path: str = ""

    @property
    def total_lines(self) -> int:
        """Total blamed lines across all files."""
        return sum(f.total_lines for f in self.files)

    @property
    def total_ai_lines(self) -> int:
        """Total AI-attributed lines."""
        return sum(f.ai_lines for f in self.files)

    @property
    def total_human_lines(self) -> int:
        """Total human-attributed lines."""
        return sum(f.human_lines for f in self.files)

    @property
    def repo_ai_pct(self) -> float:
        """Repository-wide AI contribution percentage."""
        if self.total_lines == 0:
            return 0.0
        return round(self.total_ai_lines / self.total_lines * 100, 1)

    @property
    def repo_human_pct(self) -> float:
        """Repository-wide human contribution percentage."""
        if self.total_lines == 0:
            return 0.0
        return round(self.total_human_lines / self.total_lines * 100, 1)

    @property
    def unique_human_authors(self) -> list[str]:
        """All unique human author names found across files."""
        authors: set[str] = set()
        for f in self.files:
            authors.update(f.human_authors)
        return sorted(authors)

    @property
    def unique_ai_authors(self) -> list[str]:
        """All unique AI author names found across files."""
        authors: set[str] = set()
        for f in self.files:
            authors.update(f.ai_authors)
        return sorted(authors)

    def _bar(self, pct: float, width: int = 20) -> str:
        """Render a simple ASCII bar for a percentage value."""
        filled = round(pct / 100 * width)
        return "█" * filled + "░" * (width - filled)

    def to_markdown(self) -> str:
        """Render the full blame report as a Markdown string."""
        lines: list[str] = []
        lines.append("# Git Blame Attribution Report\n")
        lines.append(f"**Repo:** `{self.repo_path}`\n")
        lines.append("## Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total blamed lines | {self.total_lines:,} |")
        lines.append(f"| AI lines | {self.total_ai_lines:,} ({self.repo_ai_pct}%) |")
        lines.append(f"| Human lines | {self.total_human_lines:,} ({self.repo_human_pct}%) |")
        lines.append(f"| Human authors | {', '.join(self.unique_human_authors) or '—'} |")
        lines.append(f"| AI authors | {', '.join(self.unique_ai_authors) or '—'} |")
        lines.append("")
        ai_bar = self._bar(self.repo_ai_pct)
        hum_bar = self._bar(self.repo_human_pct)
        lines.append("## Attribution Overview\n")
        lines.append("```")
        lines.append(f"AI    [{ai_bar}] {self.repo_ai_pct:5.1f}%")
        lines.append(f"Human [{hum_bar}] {self.repo_human_pct:5.1f}%")
        lines.append("```\n")
        if not self.files:
            lines.append("_No files blamed (not a git repo, or no commits yet)._\n")
            return "\n".join(lines)
        lines.append("## Per-File Attribution\n")
        lines.append("| File | Lines | AI% | Human% | AI bar |")
        lines.append("|------|-------|-----|--------|--------|")
        for fb in sorted(self.files, key=lambda f: f.ai_pct, reverse=True):
            bar = self._bar(fb.ai_pct, width=12)
            lines.append(
                f"| `{fb.path}` | {fb.total_lines} "
                f"| {fb.ai_pct}% | {fb.human_pct}% | `{bar}` |"
            )
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "repo_path": self.repo_path,
            "total_lines": self.total_lines,
            "total_ai_lines": self.total_ai_lines,
            "total_human_lines": self.total_human_lines,
            "repo_ai_pct": self.repo_ai_pct,
            "repo_human_pct": self.repo_human_pct,
            "unique_human_authors": self.unique_human_authors,
            "unique_ai_authors": self.unique_ai_authors,
            "files": [f.to_dict() for f in self.files],
        }

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _run_git_blame(file_path: Path, repo_root: Path) -> list[tuple[str, str]]:
    """Run ``git blame`` on *file_path* and return (author, line) pairs."""
    try:
        result = subprocess.run(
            ["git", "blame", "--porcelain", str(file_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    entries: list[tuple[str, str]] = []
    current_author = ""
    for raw_line in result.stdout.splitlines():
        if raw_line.startswith("author "):
            current_author = raw_line[len("author "):].strip()
        elif raw_line.startswith("\t"):
            entries.append((current_author, raw_line[1:]))
    return entries


def _blame_file(py_file: Path, repo_root: Path) -> FileBlame:
    """Produce a ``FileBlame`` for a single Python source file."""
    rel = str(py_file.relative_to(repo_root))
    fb = FileBlame(path=rel)
    entries = _run_git_blame(py_file, repo_root)
    if not entries:
        try:
            raw = py_file.read_text(encoding="utf-8", errors="replace").splitlines()
            fb.total_lines = len(raw)
        except OSError:
            pass
        return fb
    for author, _line in entries:
        fb.total_lines += 1
        if _is_ai_author(author):
            fb.ai_lines += 1
            fb.ai_authors.append(author)
        else:
            fb.human_lines += 1
            fb.human_authors.append(author)
    return fb


def analyze_blame(repo_path: Optional[Path] = None) -> BlameReport:
    """Analyze git blame across all Python files in *repo_path*/src/."""
    if repo_path is None:
        repo_path = Path(__file__).resolve().parent.parent
    repo_path = Path(repo_path)
    src_dir = repo_path / "src"
    report = BlameReport(repo_path=str(repo_path))
    if not src_dir.exists():
        return report
    for py_file in sorted(src_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        fb = _blame_file(py_file, repo_path)
        report.files.append(fb)
    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_blame_report(report: BlameReport, out_path: Path) -> None:
    """Write the blame report as Markdown + JSON sidecar to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")
