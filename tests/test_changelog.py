"""Tests for changelog generation utilities."""

import pytest

from src.release_notes import (
    ReleaseEntry,
    ReleaseNotes,
    generate_release_notes,
    parse_commit,
    parse_commits,
    render_markdown,
)
from datetime import date


# ---------------------------------------------------------------------------
# parse_commit
# ---------------------------------------------------------------------------


class TestParseCommit:
    def test_simple_feat(self):
        entry = parse_commit("feat: add dark mode")
        assert entry is not None
        assert entry.category == "feat"
        assert entry.scope is None
        assert entry.description == "add dark mode"
        assert not entry.breaking

    def test_scoped_fix(self):
        entry = parse_commit("fix(api): handle null response")
        assert entry is not None
        assert entry.category == "fix"
        assert entry.scope == "api"
        assert entry.description == "handle null response"

    def test_breaking_change(self):
        entry = parse_commit("feat(auth)!: replace JWT with passkeys")
        assert entry is not None
        assert entry.breaking is True
        assert entry.scope == "auth"

    def test_with_pr_number(self):
        entry = parse_commit("chore: bump deps", pr_number=42)
        assert entry is not None
        assert entry.pr_number == 42

    def test_non_conventional(self):
        assert parse_commit("Update README") is None
        assert parse_commit("WIP") is None
        assert parse_commit("") is None

    def test_leading_whitespace_stripped(self):
        entry = parse_commit("  feat: trim me  ")
        assert entry is not None
        assert entry.description == "trim me"


# ---------------------------------------------------------------------------
# parse_commits
# ---------------------------------------------------------------------------


class TestParseCommits:
    def test_filters_non_conventional(self):
        msgs = ["feat: a", "not conventional", "fix(ui): b"]
        entries = parse_commits(msgs)
        assert len(entries) == 2

    def test_pr_numbers_aligned(self):
        msgs = ["feat: a", "fix: b"]
        entries = parse_commits(msgs, pr_numbers=[1, 2])
        assert entries[0].pr_number == 1
        assert entries[1].pr_number == 2

    def test_empty_list(self):
        assert parse_commits([]) == []

    def test_all_non_conventional(self):
        assert parse_commits(["foo", "bar"]) == []


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def _make_notes(self, entries=None):
        return ReleaseNotes(
            version="1.0.0",
            release_date=date(2025, 1, 15),
            entries=entries or [],
        )

    def test_heading_with_date(self):
        md = render_markdown(self._make_notes())
        assert "## 1.0.0 (2025-01-15)" in md

    def test_heading_without_date(self):
        md = render_markdown(self._make_notes(), include_date=False)
        assert "## 1.0.0" in md
        assert "2025" not in md

    def test_feat_section(self):
        entries = [ReleaseEntry(category="feat", scope=None, description="new thing")]
        md = render_markdown(self._make_notes(entries))
        assert "### Features" in md
        assert "- new thing" in md

    def test_scoped_entry(self):
        entries = [ReleaseEntry(category="fix", scope="db", description="null ptr")]
        md = render_markdown(self._make_notes(entries))
        assert "**db:** null ptr" in md

    def test_breaking_marker(self):
        entries = [
            ReleaseEntry(
                category="feat", scope=None, description="big change", breaking=True
            )
        ]
        md = render_markdown(self._make_notes(entries))
        assert "**(BREAKING)**" in md

    def test_pr_link(self):
        entries = [
            ReleaseEntry(
                category="fix",
                scope=None,
                description="crash on startup",
                pr_number=99,
            )
        ]
        md = render_markdown(
            self._make_notes(entries), link_prs="https://github.com/o/r/pull"
        )
        assert "[#99](https://github.com/o/r/pull/99)" in md

    def test_pr_plain(self):
        entries = [
            ReleaseEntry(
                category="fix", scope=None, description="crash", pr_number=7
            )
        ]
        md = render_markdown(self._make_notes(entries))
        assert "(#7)" in md

    def test_category_order(self):
        entries = [
            ReleaseEntry(category="chore", scope=None, description="c"),
            ReleaseEntry(category="feat", scope=None, description="f"),
            ReleaseEntry(category="fix", scope=None, description="b"),
        ]
        md = render_markdown(self._make_notes(entries))
        feat_pos = md.index("### Features")
        fix_pos = md.index("### Bug Fixes")
        chore_pos = md.index("### Chores")
        assert feat_pos < fix_pos < chore_pos

    def test_intro_rendered(self):
        notes = ReleaseNotes(
            version="2.0.0",
            release_date=date(2025, 6, 1),
            intro="This is a big release.",
        )
        md = render_markdown(notes)
        assert "This is a big release." in md

    def test_empty_entries(self):
        md = render_markdown(self._make_notes())
        # Only heading, no category sections
        assert "###" not in md


# ---------------------------------------------------------------------------
# generate_release_notes (integration)
# ---------------------------------------------------------------------------


class TestGenerateReleaseNotes:
    def test_basic_generation(self):
        notes = generate_release_notes(
            "0.1.0",
            ["feat: hello world", "fix(db): connection leak"],
            release_date=date(2025, 3, 1),
        )
        assert "0.1.0" in notes
        assert "hello world" in notes
        assert "connection leak" in notes

    def test_no_commits(self):
        notes = generate_release_notes("1.0.0", [], release_date=date(2025, 1, 1))
        assert "1.0.0" in notes

    def test_filters_non_cc_commits(self):
        notes = generate_release_notes(
            "1.0.0",
            ["merge branch", "feat: something"],
            release_date=date(2025, 1, 1),
        )
        assert "merge branch" not in notes
        assert "something" in notes
