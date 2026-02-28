"""Tests for src/release_notes.py — changelog --release."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.release_notes import (
    ReleaseEntry,
    ReleaseSection,
    ReleaseNotes,
    generate_release_notes,
    _parse_commit,
    _CC_RE,
)


# ---------------------------------------------------------------------------
# _parse_commit
# ---------------------------------------------------------------------------


def _raw(subject: str, body: str = "", author: str = "Alice") -> dict:
    return {"sha": "abc1234", "subject": subject, "body": body, "author": author}


def test_parse_commit_feat():
    entry = _parse_commit(_raw("feat: add plugin system"))
    assert entry is not None
    assert entry.cc_type == "feat"
    assert entry.description == "add plugin system"


def test_parse_commit_with_scope():
    entry = _parse_commit(_raw("fix(health): correct score calculation"))
    assert entry is not None
    assert entry.cc_type == "fix"
    assert entry.cc_scope == "health"


def test_parse_commit_breaking():
    entry = _parse_commit(_raw("feat!: remove deprecated CLI flag"))
    assert entry is not None
    assert entry.is_breaking is True


def test_parse_commit_breaking_footer():
    entry = _parse_commit(_raw("feat: overhaul API", body="BREAKING CHANGE: all endpoints renamed"))
    assert entry is not None
    assert entry.is_breaking is True


def test_parse_commit_non_conventional_returns_none():
    entry = _parse_commit(_raw("Fixed the thing"))
    assert entry is None


def test_parse_commit_pr_reference():
    entry = _parse_commit(_raw("fix: resolve memory leak", body="Closes #42"))
    assert entry is not None
    assert "#42" in entry.pr_refs


def test_parse_commit_nightshift():
    entry = _parse_commit(_raw("[nightshift] feat: add openapi generator"))
    assert entry is not None
    # The [nightshift] prefix breaks CC parsing — that's fine
    # What matters is case-insensitive pattern matching in is_nightshift
    entry2 = _parse_commit(_raw("feat: add openapi generator", body="[nightshift] session 17"))
    assert entry2 is not None
    assert entry2.is_nightshift is True


# ---------------------------------------------------------------------------
# ReleaseEntry.format_line
# ---------------------------------------------------------------------------


def test_release_entry_format_line_simple():
    entry = ReleaseEntry(
        sha="abc", subject="feat: add plugin", cc_type="feat", scope="",
        description="add plugin", is_breaking=False, is_nightshift=False,
        pr_refs=[], author="Alice",
    )
    line = entry.format_line()
    assert line.startswith("- ")
    assert "add plugin" in line


def test_release_entry_format_line_scoped():
    entry = ReleaseEntry(
        sha="abc", subject="fix(health): score fix", cc_type="fix", scope="health",
        description="score fix", is_breaking=False, is_nightshift=False,
        pr_refs=["#42"], author="Alice",
    )
    line = entry.format_line()
    assert "**health:**" in line
    assert "score fix" in line
    assert "#42" in line


def test_release_entry_format_line_breaking():
    entry = ReleaseEntry(
        sha="abc", subject="feat!: overhaul", cc_type="feat", scope="",
        description="overhaul", is_breaking=True, is_nightshift=False,
        pr_refs=[], author="Alice",
    )
    line = entry.format_line()
    assert "BREAKING" in line


def test_release_entry_format_line_nightshift():
    entry = ReleaseEntry(
        sha="abc", subject="feat: add 🌙", cc_type="feat", scope="",
        description="add nightshift feature", is_breaking=False, is_nightshift=True,
        pr_refs=[], author="Computer",
    )
    line = entry.format_line()
    assert "🌙" in line


# ---------------------------------------------------------------------------
# ReleaseSection
# ---------------------------------------------------------------------------


def test_release_section_to_markdown():
    entry = ReleaseEntry(
        sha="abc", subject="feat: add x", cc_type="feat", scope="",
        description="add x", is_breaking=False, is_nightshift=False,
        pr_refs=[], author="Alice",
    )
    sec = ReleaseSection(title="✨ Features", order=1, entries=[entry])
    md = sec.to_markdown()
    assert "### ✨ Features" in md
    assert "add x" in md


def test_release_section_empty():
    sec = ReleaseSection(title="🐛 Bug Fixes", order=2)
    md = sec.to_markdown()
    assert "🐛 Bug Fixes" in md


# ---------------------------------------------------------------------------
# ReleaseNotes
# ---------------------------------------------------------------------------


def _sample_notes() -> ReleaseNotes:
    feat_entry = ReleaseEntry(
        sha="abc", subject="feat: add plugin system", cc_type="feat", scope="",
        description="add plugin system", is_breaking=False, is_nightshift=True,
        pr_refs=["#40"], author="Computer",
    )
    fix_entry = ReleaseEntry(
        sha="def", subject="fix: correct health score", cc_type="fix", scope="health",
        description="correct health score", is_breaking=False, is_nightshift=False,
        pr_refs=["#41"], author="Alice",
    )
    return ReleaseNotes(
        version="v0.17.0",
        date="2026-02-28",
        repo_url="https://github.com/gunnargray-dev/nightshift",
        sections=[
            ReleaseSection(title="✨ Features", order=1, entries=[feat_entry]),
            ReleaseSection(title="🐛 Bug Fixes", order=2, entries=[fix_entry]),
        ],
        contributors=["Computer", "Alice"],
        stats={"Commits in release": 25, "Nightshift contributions": 20},
        previous_version="v0.16.0",
        nightshift_session=17,
    )


def test_release_notes_to_markdown():
    notes = _sample_notes()
    md = notes.to_markdown()
    assert "# Release v0.17.0" in md
    assert "✨ Features" in md
    assert "🐛 Bug Fixes" in md
    assert "add plugin system" in md
    assert "correct health score" in md
    assert "Session 17" in md


def test_release_notes_version_prefix():
    notes = _sample_notes()
    assert notes.version.startswith("v")


def test_release_notes_stats_in_markdown():
    notes = _sample_notes()
    md = notes.to_markdown()
    assert "Commits in release" in md
    assert "25" in md


def test_release_notes_breaking_change_callout():
    notes = _sample_notes()
    bc = ReleaseEntry(
        sha="ghi", subject="feat!: breaking", cc_type="feat", scope="",
        description="major API change", is_breaking=True, is_nightshift=False,
        pr_refs=[], author="Alice",
    )
    notes.breaking_changes = [bc]
    md = notes.to_markdown()
    assert "Breaking Changes" in md
    assert "major API change" in md


def test_release_notes_changelog_link():
    notes = _sample_notes()
    md = notes.to_markdown()
    assert "v0.16.0" in md
    assert "v0.17.0" in md


def test_release_notes_contributors():
    notes = _sample_notes()
    md = notes.to_markdown()
    assert "Contributors" in md
    assert "@Computer" in md or "@Alice" in md


def test_release_notes_to_dict():
    notes = _sample_notes()
    d = notes.to_dict()
    assert d["version"] == "v0.17.0"
    assert "✨ Features" in d["sections"]
    assert d["nightshift_session"] == 17


def test_release_notes_save(tmp_path):
    notes = _sample_notes()
    out = tmp_path / "RELEASE_NOTES.md"
    notes.save(out)
    assert out.exists()
    content = out.read_text()
    assert "v0.17.0" in content


# ---------------------------------------------------------------------------
# generate_release_notes
# ---------------------------------------------------------------------------


def test_generate_release_notes_no_git(tmp_path):
    """Should return a valid ReleaseNotes even with no git history."""
    notes = generate_release_notes(tmp_path, version="0.17.0")
    assert isinstance(notes, ReleaseNotes)
    assert notes.version == "v0.17.0"


def test_generate_release_notes_reads_version_from_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.17.0"\n')
    notes = generate_release_notes(tmp_path)
    assert notes.version == "v0.17.0"


def test_generate_release_notes_version_prefix(tmp_path):
    notes = generate_release_notes(tmp_path, version="1.2.3")
    assert notes.version == "v1.2.3"


def test_generate_release_notes_detects_session(tmp_path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    log.write_text("## Session 17 — February 2026\n\n---\n")
    notes = generate_release_notes(tmp_path)
    assert notes.nightshift_session == 17
