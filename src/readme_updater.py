"""README auto-updater for Awake.

This module injects live stats badges into the project README automatically
after each session. It scans for specially formatted comment markers and
replaces the content between them with fresh data.

Marker format::

    <!-- awake:stats -->
    ...replaced content...
    <!-- /awake:stats -->

Supported blocks:
    awake:stats   -- project stat badges (sessions, PRs, commits, etc.)
    awake:health  -- code health score badge
    awake:toc     -- auto-generated table of contents
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class UpdateResult:
    """Result of a README update operation."""
    path: Path
    blocks_found: int
    blocks_updated: int
    changed: bool
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Return dict representation of this result."""
        return {
            "path": str(self.path),
            "blocks_found": self.blocks_found,
            "blocks_updated": self.blocks_updated,
            "changed": self.changed,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], cwd: Path) -> str:
    """Run a subprocess command and return stdout, ignoring errors."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=10
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _gather_stats(repo_root: Path) -> dict[str, Any]:
    """Gather repo statistics for badge generation."""
    commits = _run(["git", "rev-list", "--count", "HEAD"], repo_root)
    total_commits = int(commits) if commits.isdigit() else 0

    log = _run(["git", "log", "--oneline", "--all"], repo_root)
    pr_lines = [l for l in log.splitlines() if "[awake]" in l.lower() and "merge" in l.lower()]
    total_prs = len(pr_lines)

    awake_lines = [l for l in log.splitlines() if l.startswith("[awake]") or "[awake]" in l]
    sessions_set: set[str] = set()
    for line in awake_lines:
        m = re.search(r"session[\s#-]*(\d+)", line, re.IGNORECASE)
        if m:
            sessions_set.add(m.group(1))
    nights_active = len(sessions_set) if sessions_set else max(1, total_commits // 20)

    return {
        "total_commits": total_commits,
        "total_prs": total_prs,
        "nights_active": nights_active,
    }


def _make_stat_badges(stats: dict[str, Any]) -> str:
    """Render stat badges as Markdown."""
    sessions = stats.get("nights_active", 0)
    prs = stats.get("total_prs", 0)
    commits = stats.get("total_commits", 0)
    lines = [
        f"![Sessions](https://img.shields.io/badge/sessions-{sessions}-blue)",
        f"![PRs](https://img.shields.io/badge/PRs-{prs}-green)",
        f"![Commits](https://img.shields.io/badge/commits-{commits}-lightgrey)",
    ]
    return "  ".join(lines)


def _make_health_badge(health_score: Optional[int] = None) -> str:
    """Render a health score badge as Markdown."""
    if health_score is None:
        return "![Health](https://img.shields.io/badge/health-unknown-lightgrey)"
    if health_score >= 85:
        color = "brightgreen"
    elif health_score >= 70:
        color = "yellow"
    else:
        color = "red"
    return f"![Health](https://img.shields.io/badge/health-{health_score}%25-{color})"


# ---------------------------------------------------------------------------
# TOC generator
# ---------------------------------------------------------------------------

def _make_toc(content: str) -> str:
    """Generate a Markdown TOC from headings in ``content``."""
    lines = []
    for line in content.splitlines():
        m = re.match(r"^(#{1,6})\s+(.+)", line)
        if not m:
            continue
        level = len(m.group(1))
        title = m.group(2).strip()
        # Skip the TOC heading itself
        if re.match(r"table of contents", title, re.IGNORECASE):
            continue
        anchor = re.sub(r"[^\w\s-]", "", title.lower())
        anchor = re.sub(r"[\s]+", "-", anchor).strip("-")
        indent = "  " * (level - 1)
        lines.append(f"{indent}- [{title}](#{anchor})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core updater
# ---------------------------------------------------------------------------

def _replace_block(content: str, tag: str, replacement: str) -> tuple[str, bool]:
    """Replace the content between ``<!-- tag -->`` and ``<!-- /tag -->`` markers."""
    pattern = rf"(<!-- {re.escape(tag)} -->)[\s\S]*?(<!-- /{re.escape(tag)} -->)"
    new_content = f"\n{replacement}\n"
    result, n = re.subn(pattern, rf"\g<1>{new_content}\g<2>", content)
    return result, n > 0


def update_readme(
    repo_root: Path,
    readme_name: str = "README.md",
    health_score: Optional[int] = None,
    dry_run: bool = False,
) -> UpdateResult:
    """Update the README with fresh stats and health badges.

    Parameters
    ----------
    repo_root:
        Root directory of the repository.
    readme_name:
        Name of the README file (default: ``README.md``).
    health_score:
        Pre-computed health score; if ``None``, the badge shows "unknown".
    dry_run:
        If ``True``, compute changes but do not write to disk.

    Returns
    -------
    UpdateResult
        Summary of changes made.
    """
    readme_path = repo_root / readme_name
    if not readme_path.exists():
        return UpdateResult(
            path=readme_path,
            blocks_found=0,
            blocks_updated=0,
            changed=False,
            error=f"README not found: {readme_path}",
        )

    original = readme_path.read_text(encoding="utf-8")
    content = original
    blocks_found = 0
    blocks_updated = 0

    # --- awake:stats block ---
    if "<!-- awake:stats -->" in content:
        blocks_found += 1
        stats = _gather_stats(repo_root)
        badge_str = _make_stat_badges(stats)
        content, changed = _replace_block(content, "awake:stats", badge_str)
        if changed:
            blocks_updated += 1

    # --- awake:health block ---
    if "<!-- awake:health -->" in content:
        blocks_found += 1
        badge_str = _make_health_badge(health_score)
        content, changed = _replace_block(content, "awake:health", badge_str)
        if changed:
            blocks_updated += 1

    # --- awake:toc block ---
    if "<!-- awake:toc -->" in content:
        blocks_found += 1
        toc = _make_toc(content)
        content, changed = _replace_block(content, "awake:toc", toc)
        if changed:
            blocks_updated += 1

    file_changed = content != original
    if file_changed and not dry_run:
        readme_path.write_text(content, encoding="utf-8")

    return UpdateResult(
        path=readme_path,
        blocks_found=blocks_found,
        blocks_updated=blocks_updated,
        changed=file_changed,
    )


def update_readme_to_dict(result: UpdateResult) -> dict:
    """Serialize an ``UpdateResult`` to the /api/readme JSON response format."""
    return result.to_dict()
