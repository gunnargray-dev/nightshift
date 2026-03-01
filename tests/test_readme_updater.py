"""Tests for src/readme_updater.py"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.readme_updater import (
    FileEntry,
    RoadmapProgress,
    CommitEntry,
    RepoSnapshot,
    _parse_docstring_summary,
    _count_lines,
    _parse_commit_line,
    _parse_roadmap,
    _parse_test_status,
    _get_recent_commits,
    _get_pr_count_from_log,
    _get_session_count,
    build_snapshot,
    render_readme,
    update_readme,
)


# ---------------------------------------------------------------------------
# Unit tests: data classes
# ---------------------------------------------------------------------------


class TestRoadmapProgress:
    def test_percent_computed_correctly(self):
        rp = RoadmapProgress(checked=3, total=10)
        assert rp.percent == 30.0

    def test_zero_total_gives_zero_percent(self):
        rp = RoadmapProgress(checked=0, total=0)
        assert rp.percent == 0.0

    def test_full_completion(self):
        rp = RoadmapProgress(checked=5, total=5)
        assert rp.percent == 100.0

    def test_partial_completion_rounds(self):
        rp = RoadmapProgress(checked=1, total=3)
        assert rp.percent == 33.3


class TestFileEntry:
    def test_basic_creation(self):
        fe = FileEntry(path="src/foo.py", description="Does something", lines=100)
        assert fe.path == "src/foo.py"
        assert fe.lines == 100


class TestCommitEntry:
    def test_fields_stored(self):
        ce = CommitEntry(sha="abc1234", commit_type="feat", description="add stuff", session=3)
        assert ce.session == 3
        assert ce.commit_type == "feat"


# ---------------------------------------------------------------------------
# Unit tests: _parse_docstring_summary
# ---------------------------------------------------------------------------


class TestParseDocstringSummary:
    def test_double_quoted_docstring(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text('"""Module docstring.\n\nMore details.\n"""\n', encoding="utf-8")
        assert _parse_docstring_summary(f) == "Module docstring"

    def test_single_quoted_docstring(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("'''Single quoted module.'''\n", encoding="utf-8")
        assert _parse_docstring_summary(f) == "Single quoted module"

    def test_no_docstring_returns_empty(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text("x = 1\n", encoding="utf-8")
        assert _parse_docstring_summary(f) == ""

    def test_missing_file_returns_empty(self, tmp_path):
        assert _parse_docstring_summary(tmp_path / "missing.py") == ""

    def test_strips_trailing_period(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text('"""Trailing period."""\n', encoding="utf-8")
        result = _parse_docstring_summary(f)
        assert not result.endswith(".")

    def test_multiline_returns_first_line(self, tmp_path):
        f = tmp_path / "mod.py"
        f.write_text('"""First line.\nSecond line.\n"""\n', encoding="utf-8")
        assert _parse_docstring_summary(f) == "First line"


# ---------------------------------------------------------------------------
# Unit tests: _count_lines
# ---------------------------------------------------------------------------


class TestCountLines:
    def test_counts_correctly(self, tmp_path):
        f = tmp_path / "f.py"
        f.write_text("a\nb\nc\n", encoding="utf-8")
        assert _count_lines(f) == 3

    def test_missing_file_returns_zero(self, tmp_path):
        assert _count_lines(tmp_path / "missing.py") == 0

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        assert _count_lines(f) == 0


# ---------------------------------------------------------------------------
# Unit tests: _parse_commit_line
# ---------------------------------------------------------------------------


class TestParseCommitLine:
    def test_standard_awake_commit(self):
        line = "abc1234 [awake] feat: add readme updater"
        result = _parse_commit_line(line)
        assert result is not None
        assert result.sha == "abc1234"
        assert result.commit_type == "feat"
        assert result.description == "add readme updater"
        assert result.session is None

    def test_commit_with_session_number(self):
        line = "def5678 [awake] meta: session 3 wrap-up"
        result = _parse_commit_line(line)
        assert result is not None
        assert result.session == 3

    def test_non_awake_commit_returns_none(self):
        line = "abc1234 fix: normal commit message"
        assert _parse_commit_line(line) is None

    def test_short_line_returns_none(self):
        assert _parse_commit_line("abc") is None

    def test_empty_line_returns_none(self):
        assert _parse_commit_line("") is None

    def test_fix_type(self):
        line = "aaa1111 [awake] fix: resolve import error"
        result = _parse_commit_line(line)
        assert result.commit_type == "fix"


# ---------------------------------------------------------------------------
# Unit tests: _parse_roadmap
# ---------------------------------------------------------------------------


class TestParseRoadmap:
    def test_counts_checked_and_total(self, tmp_path):
        f = tmp_path / "ROADMAP.md"
        f.write_text(
            "# Roadmap\n- [x] done\n- [ ] pending\n- [x] also done\n",
            encoding="utf-8",
        )
        result = _parse_roadmap(f)
        assert result.total == 3
        assert result.checked == 2

    def test_empty_roadmap(self, tmp_path):
        f = tmp_path / "ROADMAP.md"
        f.write_text("# No items\n", encoding="utf-8")
        result = _parse_roadmap(f)
        assert result.total == 0
        assert result.checked == 0

    def test_missing_file_returns_zeros(self, tmp_path):
        result = _parse_roadmap(tmp_path / "missing.md")
        assert result.total == 0
        assert result.checked == 0

    def test_all_unchecked(self, tmp_path):
        f = tmp_path / "ROADMAP.md"
        f.write_text("- [ ] a\n- [ ] b\n- [ ] c\n", encoding="utf-8")
        result = _parse_roadmap(f)
        assert result.checked == 0
        assert result.total == 3
        assert result.percent == 0.0

    def test_all_checked(self, tmp_path):
        f = tmp_path / "ROADMAP.md"
        f.write_text("- [x] a\n- [x] b\n", encoding="utf-8")
        result = _parse_roadmap(f)
        assert result.checked == 2
        assert result.total == 2
        assert result.percent == 100.0


# ---------------------------------------------------------------------------
# Unit tests: _get_pr_count_from_log / _get_session_count
# ---------------------------------------------------------------------------


class TestLogParsers:
    def test_pr_count_extracts_pr_references(self, tmp_path):
        f = tmp_path / "LOG.md"
        f.write_text(
            "## Session 1\nPR #1 merged\nPR #2 merged\n## Session 2\nPR #3 merged\n",
            encoding="utf-8",
        )
        assert _get_pr_count_from_log(f) == 3

    def test_pr_count_missing_file(self, tmp_path):
        assert _get_pr_count_from_log(tmp_path / "missing.md") == 0

    def test_session_count(self, tmp_path):
        f = tmp_path / "LOG.md"
        f.write_text("## Session 1\n\n## Session 2\n\n## Session 3\n", encoding="utf-8")
        assert _get_session_count(f) == 3

    def test_session_count_missing_file(self, tmp_path):
        assert _get_session_count(tmp_path / "missing.md") == 0


# ---------------------------------------------------------------------------
# Unit tests: render_readme
# ---------------------------------------------------------------------------


class TestRenderReadme:
    def _make_snapshot(self, **kwargs) -> RepoSnapshot:
        defaults = dict(
            project="Awake",
            version="0.1.0",
            session_count=3,
            last_run="2026-02-27 03:00 UTC",
            source_files=[
                FileEntry("src/stats.py", "Self-stats engine", 216),
                FileEntry("src/health.py", "Code health monitor", 305),
            ],
            test_count=174,
            tests_passing=True,
            recent_commits=[
                CommitEntry("abc1234", "feat", "add readme updater", 3),
                CommitEntry("def5678", "fix", "resolve import error", 3),
            ],
            roadmap=RoadmapProgress(checked=2, total=10),
            total_lines=1500,
            pr_count=6,
        )
        defaults.update(kwargs)
        return RepoSnapshot(**defaults)

    def test_contains_project_name(self):
        snap = self._make_snapshot()
        output = render_readme(snap)
        assert "Awake" in output

    def test_contains_test_badge(self):
        snap = self._make_snapshot(tests_passing=True, test_count=174)
        output = render_readme(snap)
        assert "174" in output

    def test_failing_tests_shows_fail_badge(self):
        snap = self._make_snapshot(tests_passing=False)
        output = render_readme(snap)
        assert "FAILING" in output

    def test_contains_source_file_table(self):
        snap = self._make_snapshot()
        output = render_readme(snap)
        assert "src/stats.py" in output
        assert "Self-stats engine" in output

    def test_contains_recent_commits(self):
        snap = self._make_snapshot()
        output = render_readme(snap)
        assert "add readme updater" in output

    def test_contains_roadmap_progress(self):
        snap = self._make_snapshot()
        output = render_readme(snap)
        assert "2/10" in output

    def test_contains_last_run(self):
        snap = self._make_snapshot(last_run="2026-02-27 03:00 UTC")
        output = render_readme(snap)
        assert "2026-02-27" in output

    def test_contains_session_count(self):
        snap = self._make_snapshot(session_count=3)
        output = render_readme(snap)
        assert "3" in output

    def test_is_valid_markdown(self):
        snap = self._make_snapshot()
        output = render_readme(snap)
        # Has H1 heading
        assert output.startswith("# ")
        # Has table
        assert "|" in output

    def test_empty_commits_shows_placeholder(self):
        snap = self._make_snapshot(recent_commits=[])
        output = render_readme(snap)
        assert "No commits yet" in output

    def test_pr_count_in_stats(self):
        snap = self._make_snapshot(pr_count=6)
        output = render_readme(snap)
        assert "6" in output

    def test_total_lines_formatted(self):
        snap = self._make_snapshot(total_lines=1500)
        output = render_readme(snap)
        assert "1,500" in output


# ---------------------------------------------------------------------------
# Integration test: build_snapshot with mocked subprocess
# ---------------------------------------------------------------------------


class TestBuildSnapshot:
    def test_returns_snapshot_with_source_files(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text("")
        (src_dir / "stats.py").write_text('"""Self-stats engine."""\nx = 1\n')

        with patch("src.readme_updater._parse_test_status", return_value=(100, True)):
            with patch("src.readme_updater._get_recent_commits", return_value=[]):
                snap = build_snapshot(tmp_path, run_tests=False)

        assert len(snap.source_files) == 1
        assert snap.source_files[0].path == "src/stats.py"

    def test_run_tests_false_skips_pytest(self, tmp_path):
        (tmp_path / "src").mkdir()
        snap = build_snapshot(tmp_path, run_tests=False)
        assert snap.test_count == 0

    def test_snapshot_has_timestamp(self, tmp_path):
        (tmp_path / "src").mkdir()
        snap = build_snapshot(tmp_path, run_tests=False)
        assert "UTC" in snap.last_run

    def test_snapshot_uses_roadmap_when_present(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "ROADMAP.md").write_text("- [x] done\n- [ ] pending\n")
        snap = build_snapshot(tmp_path, run_tests=False)
        assert snap.roadmap.total == 2
        assert snap.roadmap.checked == 1


# ---------------------------------------------------------------------------
# Integration test: update_readme dry_run
# ---------------------------------------------------------------------------


class TestUpdateReadme:
    def test_dry_run_does_not_write(self, tmp_path):
        (tmp_path / "src").mkdir()
        result = update_readme(tmp_path, dry_run=True, run_tests=False)
        assert not (tmp_path / "README.md").exists()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_writes_readme_when_not_dry_run(self, tmp_path):
        (tmp_path / "src").mkdir()
        update_readme(tmp_path, dry_run=False, run_tests=False)
        assert (tmp_path / "README.md").exists()

    def test_written_readme_has_content(self, tmp_path):
        (tmp_path / "src").mkdir()
        update_readme(tmp_path, dry_run=False, run_tests=False)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert len(content) > 100
        assert "Awake" in content
