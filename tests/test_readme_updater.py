"""Tests for README updater."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.readme_updater import (
    ReadmeConfig,
    _extract_sections,
    _generate_badges,
    _generate_toc,
    _make_badge,
    _replace_section,
    update_readme,
)


# ---------------------------------------------------------------------------
# _make_badge
# ---------------------------------------------------------------------------


def test_make_badge_format():
    badge = _make_badge("Python", "3.11", "blue")
    assert badge.startswith("![Python]")
    assert "img.shields.io" in badge
    assert "blue" in badge


def test_make_badge_encodes_spaces():
    badge = _make_badge("my label", "my value", "green")
    assert " " not in badge


def test_make_badge_style():
    badge = _make_badge("Status", "passing", "green", style="for-the-badge")
    assert "for-the-badge" in badge


# ---------------------------------------------------------------------------
# _extract_sections
# ---------------------------------------------------------------------------


def test_extract_sections_basic():
    md = "# Title\nSome intro.\n## Installation\nInstall here.\n## Usage\nUse here."
    sections = _extract_sections(md)
    assert "Installation" in sections
    assert "Usage" in sections
    assert "Install here." in sections["Installation"]


def test_extract_sections_empty():
    sections = _extract_sections("no headings here")
    assert sections == {}


def test_extract_sections_nested_headings():
    md = "# H1\n## H2\n### H3\ncontent"
    sections = _extract_sections(md)
    assert "H1" in sections
    assert "H2" in sections
    assert "H3" in sections


# ---------------------------------------------------------------------------
# _generate_toc
# ---------------------------------------------------------------------------


def test_generate_toc_contains_links():
    md = "# Title\n## Installation\n## Usage\n## Contributing"
    toc = _generate_toc(md)
    assert "Installation" in toc
    assert "Usage" in toc
    assert "Contributing" in toc
    assert "#" in toc  # anchor links


def test_generate_toc_skips_self():
    md = "# Title\n## Table of Contents\n## Installation"
    toc = _generate_toc(md)
    # Should not include Table of Contents in the TOC itself
    lines = toc.splitlines()
    assert not any("Table of Contents" in l for l in lines if l.startswith("-"))


def test_generate_toc_indents_subheadings():
    md = "# H1\n## H2\n### H3"
    toc = _generate_toc(md)
    # H3 should be indented more than H2
    h2_line = next(l for l in toc.splitlines() if "H2" in l)
    h3_line = next(l for l in toc.splitlines() if "H3" in l)
    assert h3_line.startswith("  ")  # indented


# ---------------------------------------------------------------------------
# _generate_badges
# ---------------------------------------------------------------------------


def test_generate_badges_with_python_files(tmp_path):
    (tmp_path / "main.py").write_text("# py")
    badges = _generate_badges(tmp_path)
    assert "Python" in badges


def test_generate_badges_with_license(tmp_path):
    (tmp_path / "LICENSE").write_text("MIT")
    (tmp_path / "main.py").write_text("# py")
    badges = _generate_badges(tmp_path)
    assert "License" in badges


def test_generate_badges_empty_repo(tmp_path):
    badges = _generate_badges(tmp_path)
    assert badges == ""


# ---------------------------------------------------------------------------
# _replace_section
# ---------------------------------------------------------------------------


def test_replace_section_updates_content():
    md = "# Title\n\n## Installation\n\nOld content.\n\n## Usage\n\nUse it."
    result = _replace_section(md, "Installation", "New content.")
    assert "New content." in result
    assert "Old content." not in result


def test_replace_section_preserves_other_sections():
    md = "# Title\n\n## Installation\n\nOld.\n\n## Usage\n\nUse it."
    result = _replace_section(md, "Installation", "New.")
    assert "Use it." in result


# ---------------------------------------------------------------------------
# update_readme integration
# ---------------------------------------------------------------------------


def test_update_readme_no_readme(tmp_path):
    result = update_readme(tmp_path)
    assert "error" in result


def test_update_readme_dry_run(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# My Project\n\nSome content.\n")
    (tmp_path / "main.py").write_text("# py")
    result = update_readme(tmp_path, config=ReadmeConfig(dry_run=True))
    assert result["path"] == str(readme)
    # dry_run should return new_content
    assert "new_content" in result


def test_update_readme_writes_file(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# My Project\n\n"
        "[![Python](https://img.shields.io/badge/Python-3.11-blue)](x)\n\n"
        "## Table of Contents\n\nOld TOC.\n\n## Installation\n\nStuff.\n"
    )
    (tmp_path / "main.py").write_text("# py")
    result = update_readme(tmp_path, config=ReadmeConfig(dry_run=False))
    assert result["modified"] is True
    updated = readme.read_text()
    assert "Installation" in updated
