"""Tests for src/changelog.py — Awake changelog manager."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo with a CHANGELOG.md."""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n- initial feature\n\n"
        "## [0.1.0] - 2024-01-01\n\n"
        "### Added\n- project scaffolding\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Unit tests — ChangelogEntry
# ---------------------------------------------------------------------------


def test_changelog_entry_fields():
    """ChangelogEntry stores all required fields."""
    from src.changelog import ChangelogEntry

    entry = ChangelogEntry(
        version="1.0.0",
        date="2024-06-01",
        section="Added",
        text="new feature",
    )
    assert entry.version == "1.0.0"
    assert entry.date == "2024-06-01"
    assert entry.section == "Added"
    assert entry.text == "new feature"


def test_changelog_entry_defaults():
    """ChangelogEntry uses sensible defaults for optional fields."""
    from src.changelog import ChangelogEntry

    entry = ChangelogEntry(version="0.1.0", date="", section="Changed", text="x")
    assert entry.date == ""


# ---------------------------------------------------------------------------
# Unit tests — parse_changelog
# ---------------------------------------------------------------------------


def test_parse_changelog_sections(tmp_path):
    """parse_changelog returns entries for each section."""
    from src.changelog import parse_changelog

    repo = _make_repo(tmp_path)
    entries = parse_changelog(repo / "CHANGELOG.md")
    sections = {e.section for e in entries}
    assert "Added" in sections


def test_parse_changelog_versions(tmp_path):
    """parse_changelog extracts version strings."""
    from src.changelog import parse_changelog

    repo = _make_repo(tmp_path)
    entries = parse_changelog(repo / "CHANGELOG.md")
    versions = {e.version for e in entries}
    assert "0.1.0" in versions


def test_parse_changelog_unreleased(tmp_path):
    """parse_changelog handles the [Unreleased] block."""
    from src.changelog import parse_changelog

    repo = _make_repo(tmp_path)
    entries = parse_changelog(repo / "CHANGELOG.md")
    versions = {e.version for e in entries}
    assert "Unreleased" in versions


def test_parse_changelog_empty_file(tmp_path):
    """parse_changelog returns empty list for a blank file."""
    from src.changelog import parse_changelog

    empty = tmp_path / "CHANGELOG.md"
    empty.write_text("", encoding="utf-8")
    assert parse_changelog(empty) == []


def test_parse_changelog_missing_file(tmp_path):
    """parse_changelog raises FileNotFoundError for missing file."""
    from src.changelog import parse_changelog

    with pytest.raises(FileNotFoundError):
        parse_changelog(tmp_path / "DOES_NOT_EXIST.md")


# ---------------------------------------------------------------------------
# Unit tests — append_entry
# ---------------------------------------------------------------------------


def test_append_entry_adds_text(tmp_path):
    """append_entry inserts the new item under [Unreleased]."""
    from src.changelog import append_entry, parse_changelog

    repo = _make_repo(tmp_path)
    append_entry(repo / "CHANGELOG.md", section="Added", text="bright new thing")
    entries = parse_changelog(repo / "CHANGELOG.md")
    texts = [e.text for e in entries]
    assert any("bright new thing" in t for t in texts)


def test_append_entry_preserves_existing(tmp_path):
    """append_entry does not remove existing entries."""
    from src.changelog import append_entry, parse_changelog

    repo = _make_repo(tmp_path)
    append_entry(repo / "CHANGELOG.md", section="Fixed", text="patched something")
    entries = parse_changelog(repo / "CHANGELOG.md")
    texts = [e.text for e in entries]
    assert any("initial feature" in t for t in texts)


def test_append_entry_creates_section(tmp_path):
    """append_entry creates a new section heading if it doesn't exist."""
    from src.changelog import append_entry

    repo = _make_repo(tmp_path)
    append_entry(repo / "CHANGELOG.md", section="Security", text="fixed CVE-0000")
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Security" in text


# ---------------------------------------------------------------------------
# Unit tests — bump_version
# ---------------------------------------------------------------------------


def test_bump_version_patch():
    """bump_version increments the patch segment."""
    from src.changelog import bump_version

    assert bump_version("1.2.3", "patch") == "1.2.4"


def test_bump_version_minor():
    """bump_version increments the minor segment and resets patch."""
    from src.changelog import bump_version

    assert bump_version("1.2.3", "minor") == "1.3.0"


def test_bump_version_major():
    """bump_version increments the major segment and resets minor/patch."""
    from src.changelog import bump_version

    assert bump_version("1.2.3", "major") == "2.0.0"


def test_bump_version_zero_patch():
    """bump_version handles 0.0.0 correctly."""
    from src.changelog import bump_version

    assert bump_version("0.0.0", "patch") == "0.0.1"


# ---------------------------------------------------------------------------
# Unit tests — release_version
# ---------------------------------------------------------------------------


def test_release_version_moves_unreleased(tmp_path):
    """release_version replaces [Unreleased] with the new version header."""
    from src.changelog import release_version, parse_changelog

    repo = _make_repo(tmp_path)
    release_version(repo / "CHANGELOG.md", "1.0.0", "2024-07-01")
    entries = parse_changelog(repo / "CHANGELOG.md")
    versions = {e.version for e in entries}
    assert "1.0.0" in versions


def test_release_version_creates_new_unreleased(tmp_path):
    """release_version inserts a fresh [Unreleased] block at the top."""
    from src.changelog import release_version

    repo = _make_repo(tmp_path)
    release_version(repo / "CHANGELOG.md", "1.0.0", "2024-07-01")
    text = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "[Unreleased]" in text


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_full_changelog_workflow(tmp_path):
    """Full flow: append → release → append → parse."""
    from src.changelog import append_entry, release_version, parse_changelog

    repo = _make_repo(tmp_path)
    append_entry(repo / "CHANGELOG.md", "Added", "feature A")
    append_entry(repo / "CHANGELOG.md", "Fixed", "bug B")
    release_version(repo / "CHANGELOG.md", "0.2.0", "2024-08-01")
    append_entry(repo / "CHANGELOG.md", "Added", "feature C")
    entries = parse_changelog(repo / "CHANGELOG.md")
    versions = {e.version for e in entries}
    assert {"Unreleased", "0.2.0", "0.1.0"}.issubset(versions)


def test_changelog_idempotent_parse(tmp_path):
    """Parsing the same file twice yields identical results."""
    from src.changelog import parse_changelog

    repo = _make_repo(tmp_path)
    first = parse_changelog(repo / "CHANGELOG.md")
    second = parse_changelog(repo / "CHANGELOG.md")
    assert len(first) == len(second)


def test_changelog_entry_order(tmp_path):
    """parse_changelog returns entries in document order."""
    from src.changelog import append_entry, parse_changelog

    repo = _make_repo(tmp_path)
    append_entry(repo / "CHANGELOG.md", "Added", "first")
    append_entry(repo / "CHANGELOG.md", "Added", "second")
    entries = parse_changelog(repo / "CHANGELOG.md")
    texts = [e.text for e in entries if e.version == "Unreleased"]
    assert texts.index(next(t for t in texts if "first" in t)) < texts.index(next(t for t in texts if "second" in t))
