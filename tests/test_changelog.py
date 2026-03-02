"""Tests for changelog generation."""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.changelog import (
    ChangelogEntry,
    ChangelogRelease,
    _parse_commit_message,
    get_commits_between,
    render_markdown,
    write_changelog,
)


# ---------------------------------------------------------------------------
# _parse_commit_message
# ---------------------------------------------------------------------------


def test_parse_conventional_commit():
    ctype, desc, scope, breaking, body = _parse_commit_message("feat(auth): add OAuth support")
    assert ctype == "feat"
    assert desc == "add OAuth support"
    assert scope == "auth"
    assert not breaking


def test_parse_breaking_commit():
    ctype, desc, scope, breaking, body = _parse_commit_message("feat!: drop Python 3.9")
    assert breaking is True


def test_parse_non_conventional():
    ctype, desc, scope, breaking, body = _parse_commit_message("Initial commit")
    assert ctype == "chore"
    assert desc == "Initial commit"


def test_parse_with_body():
    msg = "fix(core): handle None input\n\nThis was causing a crash."
    ctype, desc, scope, breaking, body = _parse_commit_message(msg)
    assert ctype == "fix"
    assert "crash" in body


# ---------------------------------------------------------------------------
# ChangelogRelease helpers
# ---------------------------------------------------------------------------


def _make_entry(ctype="feat", desc="some feature", scope=None, breaking=False):
    return ChangelogEntry(
        commit_hash="abc1234",
        type=ctype,
        scope=scope,
        breaking=breaking,
        description=desc,
    )


def test_release_sections_grouping():
    release = ChangelogRelease(
        version="1.0.0",
        release_date=date(2024, 1, 1),
        entries=[
            _make_entry("feat", "new button"),
            _make_entry("fix", "null pointer"),
            _make_entry("chore", "update deps"),
        ],
    )
    sections = release.sections()
    assert "Features" in sections
    assert "Bug Fixes" in sections
    assert "Chores" in sections


def test_release_breaking_changes():
    release = ChangelogRelease(
        version="2.0.0",
        release_date=date(2024, 6, 1),
        entries=[
            _make_entry("feat", "old api removed", breaking=True),
            _make_entry("feat", "new shiny thing"),
        ],
    )
    breaking = release.breaking_changes()
    assert len(breaking) == 1
    assert breaking[0].description == "old api removed"


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


def test_render_markdown_basic():
    release = ChangelogRelease(
        version="1.2.3",
        release_date=date(2024, 3, 15),
        entries=[_make_entry("feat", "cool feature", scope="ui")],
    )
    md = render_markdown(release)
    assert "## [1.2.3]" in md
    assert "cool feature" in md
    assert "**ui**" in md


def test_render_markdown_breaking():
    release = ChangelogRelease(
        version="2.0.0",
        release_date=date(2024, 1, 1),
        entries=[_make_entry("feat", "removed old api", breaking=True)],
    )
    md = render_markdown(release)
    assert "BREAKING CHANGES" in md


def test_render_markdown_no_hashes():
    release = ChangelogRelease(
        version="1.0.0",
        release_date=date(2024, 1, 1),
        entries=[_make_entry()],
    )
    md = render_markdown(release, include_hashes=False)
    assert "abc1234" not in md


def test_render_markdown_section_order():
    release = ChangelogRelease(
        version="1.0.0",
        release_date=date(2024, 1, 1),
        entries=[
            _make_entry("fix", "bug fix"),
            _make_entry("feat", "new thing"),
        ],
    )
    md = render_markdown(release)
    feat_pos = md.index("Features")
    fix_pos = md.index("Bug Fixes")
    assert feat_pos < fix_pos


# ---------------------------------------------------------------------------
# get_commits_between
# ---------------------------------------------------------------------------


def test_get_commits_between_parses_output():
    fake_log = (
        "deadbeef\x00feat(api): add endpoint\x00---END---\n"
        "cafebabe\x00fix: typo\x00---END---\n"
    )
    with patch("src.changelog.run_cmd", return_value=fake_log):
        entries = get_commits_between("v1.0.0")
    assert len(entries) == 2
    assert entries[0].type == "feat"
    assert entries[1].type == "fix"


def test_get_commits_between_empty():
    with patch("src.changelog.run_cmd", return_value=""):
        entries = get_commits_between("v1.0.0")
    assert entries == []


# ---------------------------------------------------------------------------
# write_changelog
# ---------------------------------------------------------------------------


def test_write_changelog_creates_file(tmp_path):
    release = ChangelogRelease(
        version="1.0.0",
        release_date=date(2024, 1, 1),
        entries=[_make_entry()],
    )
    out = tmp_path / "CHANGELOG.md"
    write_changelog(release, out, prepend=False)
    assert out.exists()
    assert "1.0.0" in out.read_text()


def test_write_changelog_prepend(tmp_path):
    existing = "# Old content\n"
    out = tmp_path / "CHANGELOG.md"
    out.write_text(existing)
    release = ChangelogRelease(
        version="2.0.0",
        release_date=date(2024, 6, 1),
        entries=[_make_entry()],
    )
    write_changelog(release, out, prepend=True)
    content = out.read_text()
    assert content.index("2.0.0") < content.index("Old content")
