"""README updater for Awake."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ReadmeConfig:
    """Configuration for README updates."""

    model: str = "gpt-4o-mini"
    sections: Optional[list[str]] = None  # None = all sections
    dry_run: bool = False
    badge_style: str = "flat"
    include_toc: bool = True
    max_description_length: int = 500


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _extract_sections(markdown: str) -> dict[str, str]:
    """Return a mapping of section heading -> section content."""
    matches = list(_HEADING_RE.finditer(markdown))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        sections[heading] = markdown[start:end].strip()
    return sections


def _replace_section(markdown: str, heading: str, new_content: str) -> str:
    """Replace the content of a section identified by *heading*."""
    pattern = re.compile(
        rf"(^#{1,6}\s+{re.escape(heading)}\s*\n)(.*?)(?=^#{{1,6}}\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    replacement = rf"\1{new_content}\n\n"
    result = pattern.sub(replacement, markdown)
    return result


# ---------------------------------------------------------------------------
# Badge generation
# ---------------------------------------------------------------------------


def _make_badge(label: str, message: str, color: str, style: str = "flat") -> str:
    label_enc = label.replace("-", "--").replace("_", "__").replace(" ", "_")
    message_enc = message.replace("-", "--").replace("_", "__").replace(" ", "_")
    return f"![{label}](https://img.shields.io/badge/{label_enc}-{message_enc}-{color}?style={style})"


def _generate_badges(repo_path: Path, style: str = "flat") -> str:
    """Generate standard repository badges."""
    badges = []
    # Language badge
    py_files = list(repo_path.glob("**/*.py"))
    if py_files:
        badges.append(_make_badge("Python", "3.11+", "blue", style))
    # License badge
    license_file = repo_path / "LICENSE"
    if license_file.exists():
        badges.append(_make_badge("License", "MIT", "green", style))
    # Tests badge (check for pytest config)
    if (repo_path / "pyproject.toml").exists() or (repo_path / "setup.cfg").exists():
        badges.append(_make_badge("Tests", "passing", "brightgreen", style))
    return " ".join(badges)


# ---------------------------------------------------------------------------
# TOC generation
# ---------------------------------------------------------------------------


def _generate_toc(markdown: str) -> str:
    """Generate a Markdown table of contents."""
    lines = ["## Table of Contents", ""]
    for m in _HEADING_RE.finditer(markdown):
        level = len(m.group(1))
        heading = m.group(2).strip()
        if heading.lower() == "table of contents":
            continue
        anchor = re.sub(r"[^a-z0-9-]", "", heading.lower().replace(" ", "-"))
        indent = "  " * (level - 1)
        lines.append(f"{indent}- [{heading}](#{anchor})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main update logic
# ---------------------------------------------------------------------------


def update_readme(
    repo_path: Path,
    config: Optional[ReadmeConfig] = None,
) -> dict:
    """Update the README for the repository at *repo_path*.

    Returns a dict with keys ``path``, ``modified``, ``sections_updated``,
    and optionally ``new_content``.
    """
    cfg = config or ReadmeConfig()
    readme_path = repo_path / "README.md"

    if not readme_path.exists():
        return {"error": "README.md not found", "path": str(readme_path)}

    original = readme_path.read_text(encoding="utf-8")
    content = original
    sections_updated: list[str] = []

    # Refresh badges
    if cfg.sections is None or "badges" in (s.lower() for s in cfg.sections):
        badges = _generate_badges(repo_path, style=cfg.badge_style)
        if badges:
            badge_pattern = re.compile(r"(\[!\[.*?\]\(https://img\.shields\.io.*?\)\s*)+", re.MULTILINE)
            if badge_pattern.search(content):
                content = badge_pattern.sub(badges + "\n", content, count=1)
            sections_updated.append("badges")

    # Refresh TOC
    if cfg.include_toc and (cfg.sections is None or "table of contents" in (s.lower() for s in cfg.sections)):
        toc = _generate_toc(content)
        toc_pattern = re.compile(
            r"## Table of Contents.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL
        )
        if toc_pattern.search(content):
            content = toc_pattern.sub(toc + "\n\n", content, count=1)
        else:
            # Insert after the first heading
            first_h1 = re.search(r"^# .+$", content, re.MULTILINE)
            if first_h1:
                insert_pos = first_h1.end()
                content = content[:insert_pos] + "\n\n" + toc + "\n" + content[insert_pos:]
        sections_updated.append("table of contents")

    modified = content != original

    if modified and not cfg.dry_run:
        readme_path.write_text(content, encoding="utf-8")

    result: dict = {
        "path": str(readme_path),
        "modified": modified,
        "sections_updated": sections_updated,
    }
    if cfg.dry_run:
        result["new_content"] = content
    return result
