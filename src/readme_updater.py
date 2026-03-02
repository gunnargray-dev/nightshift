"""README auto-updater for Awake.

Generates a dynamic README.md from live repo data including:
- Project description and badges
- Health score (from latest analysis)
- Feature list (from CLI commands)
- API endpoints (from openapi.py)
- Installation and quick-start instructions
- Changelog snippet (latest 3 entries)

CLI
---
    awake readme               # Preview to stdout
    awake readme --write       # Overwrite README.md
    awake readme --dry-run     # Show diff
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BadgeSpec:
    """Specification for a single README badge."""
    label: str
    message: str
    color: str
    url: Optional[str] = None

    def to_markdown(self) -> str:
        """Render the badge as a Markdown image (optionally wrapped in a link)."""
        img_url = (
            f"https://img.shields.io/badge/{_url_encode(self.label)}-"
            f"{_url_encode(self.message)}-{self.color}"
        )
        img_md = f"![{self.label}]({img_url})"
        if self.url:
            return f"[{img_md}]({self.url})"
        return img_md


@dataclass
class ReadmeSection:
    """A named section of the README with Markdown content."""
    heading: str
    content: str
    level: int = 2  # heading level (## by default)

    def to_markdown(self) -> str:
        """Render the section as Markdown with heading."""
        prefix = "#" * self.level
        return f"{prefix} {self.heading}\n\n{self.content}\n"


@dataclass
class ReadmeDoc:
    """Complete README document."""
    title: str
    tagline: str
    badges: list[BadgeSpec] = field(default_factory=list)
    sections: list[ReadmeSection] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the full README as Markdown."""
        lines = [
            f"# {self.title}",
            "",
            self.tagline,
            "",
        ]
        if self.badges:
            badge_line = "  ".join(b.to_markdown() for b in self.badges)
            lines += [badge_line, ""]
        for section in self.sections:
            lines.append(section.to_markdown())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _url_encode(s: str) -> str:
    """Minimally URL-encode a string for use in a shields.io badge URL."""
    return s.replace(" ", "%20").replace("-", "--").replace("_", "__")


def _load_health_score(repo_path: Path) -> Optional[float]:
    """Load the latest health score from docs/health_report.json if present."""
    health_file = repo_path / "docs" / "health_report.json"
    if health_file.exists():
        try:
            data = json.loads(health_file.read_text(encoding="utf-8"))
            return float(data.get("overall_score", 0.0))
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _load_changelog_snippet(repo_path: Path, n: int = 3) -> str:
    """Load the latest *n* changelog entries from CHANGELOG.md."""
    clog = repo_path / "CHANGELOG.md"
    if not clog.exists():
        return "_No changelog yet._"
    text = clog.read_text(encoding="utf-8")
    # Find entries starting with "## ["
    entries = re.split(r"(?=^## \[)", text, flags=re.MULTILINE)
    entries = [e.strip() for e in entries if e.strip().startswith("## [")]
    snippet = entries[:n]
    return "\n\n".join(snippet) if snippet else "_No entries yet._"


def _load_command_list(repo_path: Path) -> list[str]:
    """Extract the list of CLI commands from src/cli.py (best-effort)."""
    cli_file = repo_path / "src" / "cli.py"
    if not cli_file.exists():
        return []
    text = cli_file.read_text(encoding="utf-8")
    # Look for add_parser or add_command calls
    commands = re.findall(r'add_(?:parser|command)\(["\']([a-zA-Z_-]+)["\']', text)
    return sorted(set(commands))


def _load_endpoint_list(repo_path: Path) -> list[tuple[str, str]]:
    """Load API endpoints from docs/openapi.json if present."""
    spec_file = repo_path / "docs" / "openapi.json"
    if not spec_file.exists():
        return []
    try:
        data = json.loads(spec_file.read_text(encoding="utf-8"))
        paths = data.get("paths", {})
        endpoints = []
        for path, ops in paths.items():
            if "get" in ops:
                summary = ops["get"].get("summary", "")
                endpoints.append((path, summary))
        return endpoints
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_readme(repo_path: str | Path) -> ReadmeDoc:
    """Build a ``ReadmeDoc`` from live repo data.

    Parameters
    ----------
    repo_path:
        Path to the repository root.

    Returns
    -------
    ReadmeDoc
    """
    repo = Path(repo_path).expanduser().resolve()
    health_score = _load_health_score(repo)

    # Badges
    badges: list[BadgeSpec] = []
    if health_score is not None:
        color = "brightgreen" if health_score >= 80 else "yellow" if health_score >= 60 else "red"
        badges.append(
            BadgeSpec(
                label="health score",
                message=f"{health_score:.0f}",
                color=color,
            )
        )
    badges.append(BadgeSpec(label="python", message="3.11+", color="blue"))
    badges.append(BadgeSpec(label="license", message="MIT", color="lightgrey"))

    sections: list[ReadmeSection] = []

    # Overview
    sections.append(
        ReadmeSection(
            heading="What is Awake?",
            content=(
                "Awake is an autonomous AI coding assistant that runs as a background daemon, "
                "continuously monitoring your repository.  It scores code health, opens refactor "
                "PRs, keeps documentation up-to-date, and surfaces trends -- all without "
                "interrupting your flow."
            ),
        )
    )

    # Installation
    sections.append(
        ReadmeSection(
            heading="Installation",
            content=(
                "```bash\n"
                "pip install awake\n"
                "# or, for development:\n"
                "git clone https://github.com/gunnargray-dev/Awake\n"
                "cd Awake\n"
                "pip install -e .\n"
                "```"
            ),
        )
    )

    # Quick start
    sections.append(
        ReadmeSection(
            heading="Quick Start",
            content=(
                "```bash\n"
                "awake start          # Start the background daemon\n"
                "awake health         # Score code health\n"
                "awake pr --open      # Open a refactor PR\n"
                "awake readme --write # Regenerate this README\n"
                "awake stop           # Stop the daemon\n"
                "```"
            ),
        )
    )

    # CLI commands
    commands = _load_command_list(repo)
    if commands:
        cmd_lines = "\n".join(f"- `awake {c}`" for c in commands)
        sections.append(
            ReadmeSection(
                heading="CLI Commands",
                content=cmd_lines,
            )
        )

    # API endpoints
    endpoints = _load_endpoint_list(repo)
    if endpoints:
        table_lines = [
            "| Endpoint | Description |",
            "|----------|-------------|" ,
        ]
        for path, summary in endpoints:
            table_lines.append(f"| `{path}` | {summary} |")
        sections.append(
            ReadmeSection(
                heading="API Endpoints",
                content="\n".join(table_lines),
            )
        )

    # Changelog snippet
    changelog = _load_changelog_snippet(repo)
    sections.append(
        ReadmeSection(
            heading="Recent Changes",
            content=changelog,
        )
    )

    # Contributing
    sections.append(
        ReadmeSection(
            heading="Contributing",
            content=(
                "PRs welcome!  Run `awake health` before submitting to check code quality. "
                "See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines."
            ),
        )
    )

    return ReadmeDoc(
        title="Awake",
        tagline="> An autonomous AI coding assistant that never sleeps.",
        badges=badges,
        sections=sections,
    )


def render_diff(old: str, new: str) -> str:
    """Render a simple unified-style diff between two strings."""
    import difflib
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="README.md (current)",
        tofile="README.md (generated)",
    )
    return "".join(diff)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for README generation."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-readme")
    p.add_argument("--repo", default=None, help="Repository root")
    p.add_argument("--write", action="store_true", help="Write README.md")
    p.add_argument("--dry-run", action="store_true", help="Show diff only")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    doc = build_readme(repo_path)
    new_content = doc.to_markdown()

    if args.dry_run:
        readme_path = repo_path / "README.md"
        old_content = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
        diff = render_diff(old_content, new_content)
        print(diff if diff else "No changes.")
        return 0

    if args.write:
        readme_path = repo_path / "README.md"
        readme_path.write_text(new_content, encoding="utf-8")
        print(f"  Wrote {readme_path}")
        return 0

    print(new_content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
