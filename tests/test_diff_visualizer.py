"""Tests for src/diff_visualizer.py"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.diff_visualizer import (
    FileDelta,
    CommitSummary,
    SessionDiff,
    _parse_numstat,
    _parse_diff_name_status,
    _count_tests,
    _get_commits_for_range,
    _bar,
    build_session_diff,
    render_session_diff,
    write_session_diff,
)


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------


class TestFileDelta:
    def test_net_positive(self):
        fd = FileDelta(path="src/foo.py", added=100, deleted=30, status="M")
        assert fd.net == 70

    def test_net_negative(self):
        fd = FileDelta(path="src/foo.py", added=10, deleted=50, status="M")
        assert fd.net == -40

    def test_churn_is_sum(self):
        fd = FileDelta(path="src/foo.py", added=100, deleted=30, status="M")
        assert fd.churn == 130

    def test_zero_change(self):
        fd = FileDelta(path="src/foo.py", added=0, deleted=0, status="M")
        assert fd.net == 0
        assert fd.churn == 0


class TestSessionDiff:
    def _make_diff(self, **kwargs) -> SessionDiff:
        defaults = dict(
            session_number=3,
            start_sha="abc1234",
            end_sha="def5678",
            commits=[
                CommitSummary("abc1234", "feat", "add stuff", "2026-02-27 03:00"),
                CommitSummary("def5678", "test", "add tests", "2026-02-27 03:15"),
            ],
            file_deltas=[
                FileDelta("src/foo.py", added=100, deleted=20, status="M"),
                FileDelta("src/bar.py", added=50, deleted=0, status="A"),
                FileDelta("src/baz.py", added=0, deleted=30, status="D"),
            ],
            tests_before=100,
            tests_after=130,
        )
        defaults.update(kwargs)
        return SessionDiff(**defaults)

    def test_files_added_filter(self):
        diff = self._make_diff()
        assert len(diff.files_added) == 1
        assert diff.files_added[0].path == "src/bar.py"

    def test_files_modified_filter(self):
        diff = self._make_diff()
        assert len(diff.files_modified) == 1
        assert diff.files_modified[0].path == "src/foo.py"

    def test_files_deleted_filter(self):
        diff = self._make_diff()
        assert len(diff.files_deleted) == 1
        assert diff.files_deleted[0].path == "src/baz.py"

    def test_total_added(self):
        diff = self._make_diff()
        assert diff.total_added == 150

    def test_total_deleted(self):
        diff = self._make_diff()
        assert diff.total_deleted == 50

    def test_tests_delta(self):
        diff = self._make_diff(tests_before=100, tests_after=130)
        assert diff.tests_delta == 30

    def test_biggest_change(self):
        diff = self._make_diff()
        assert diff.biggest_change.path == "src/foo.py"  # churn=120

    def test_biggest_change_empty_deltas(self):
        diff = self._make_diff(file_deltas=[])
        assert diff.biggest_change is None


# ---------------------------------------------------------------------------
# Utility: _bar
# ---------------------------------------------------------------------------


class TestBar:
    def test_full_value_fills_bar(self):
        bar = _bar(100, 100, width=10)
        assert bar == "\u2588" * 10

    def test_zero_value_empties_bar(self):
        bar = _bar(0, 100, width=10)
        assert bar == "\u2591" * 10

    def test_half_value(self):
        bar = _bar(50, 100, width=10)
        assert "\u2588" in bar
        assert "\u2591" in bar
        assert len(bar) == 10

    def test_zero_max_gives_empty(self):
        bar = _bar(50, 0, width=10)
        assert bar == "\u2591" * 10

    def test_width_is_correct(self):
        bar = _bar(30, 100, width=20)
        assert len(bar) == 20


# ---------------------------------------------------------------------------
# _parse_numstat
# ---------------------------------------------------------------------------


class TestParseNumstat:
    def test_basic_parsing(self):
        output = "10\t5\tsrc/foo.py\n20\t0\tsrc/bar.py\n"
        deltas = _parse_numstat(output)
        assert len(deltas) == 2
        assert deltas[0].added == 10
        assert deltas[0].deleted == 5
        assert deltas[0].path == "src/foo.py"

    def test_binary_files_skipped(self):
        output = "-\t-\tsome.png\n10\t5\tsrc/foo.py\n"
        deltas = _parse_numstat(output)
        assert len(deltas) == 1
        assert deltas[0].path == "src/foo.py"

    def test_empty_input(self):
        assert _parse_numstat("") == []

    def test_default_status_is_M(self):
        output = "5\t2\tsrc/foo.py\n"
        deltas = _parse_numstat(output)
        assert deltas[0].status == "M"

    def test_handles_tab_in_path(self):
        output = "5\t2\tsrc/foo bar.py\n"
        deltas = _parse_numstat(output)
        assert deltas[0].path == "src/foo bar.py"


# ---------------------------------------------------------------------------
# _parse_diff_name_status
# ---------------------------------------------------------------------------


class TestParseDiffNameStatus:
    def test_enriches_status(self):
        deltas = [FileDelta("src/new.py", 50, 0, "M")]
        name_status = "A\tsrc/new.py\n"
        result = _parse_diff_name_status(name_status, deltas)
        assert result[0].status == "A"

    def test_deleted_file(self):
        deltas = [FileDelta("src/old.py", 0, 100, "M")]
        name_status = "D\tsrc/old.py\n"
        result = _parse_diff_name_status(name_status, deltas)
        assert result[0].status == "D"

    def test_unknown_file_keeps_original_status(self):
        deltas = [FileDelta("src/foo.py", 10, 5, "M")]
        name_status = "A\tsrc/bar.py\n"
        result = _parse_diff_name_status(name_status, deltas)
        assert result[0].status == "M"

    def test_empty_name_status(self):
        deltas = [FileDelta("src/foo.py", 10, 5, "M")]
        result = _parse_diff_name_status("", deltas)
        assert result[0].status == "M"


# ---------------------------------------------------------------------------
# _count_tests
# ---------------------------------------------------------------------------


class TestCountTests:
    def test_counts_test_functions(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text(
            "def test_a():\n    pass\ndef test_b():\n    pass\n"
        )
        assert _count_tests(tmp_path) == 2

    def test_ignores_non_test_files(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "conftest.py").write_text("def setup():\n    pass\n")
        assert _count_tests(tmp_path) == 0

    def test_missing_tests_dir(self, tmp_path):
        assert _count_tests(tmp_path) == 0

    def test_counts_across_multiple_files(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_a.py").write_text("def test_1(): pass\ndef test_2(): pass\n")
        (tests_dir / "test_b.py").write_text("def test_3(): pass\n")
        assert _count_tests(tmp_path) == 3


# ---------------------------------------------------------------------------
# render_session_diff
# ---------------------------------------------------------------------------


class TestRenderSessionDiff:
    def _make_diff(self) -> SessionDiff:
        return SessionDiff(
            session_number=3,
            start_sha="abc12345",
            end_sha="def67890",
            commits=[
                CommitSummary("abc12345", "feat", "add diff visualizer", "2026-02-27 03:00"),
                CommitSummary("def67890", "test", "add visualizer tests", "2026-02-27 03:30"),
            ],
            file_deltas=[
                FileDelta("src/diff_visualizer.py", added=300, deleted=0, status="A"),
                FileDelta("tests/test_diff_visualizer.py", added=200, deleted=0, status="A"),
                FileDelta("src/stats.py", added=10, deleted=5, status="M"),
            ],
            tests_before=140,
            tests_after=174,
        )

    def test_contains_session_number(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "Session 3" in output

    def test_contains_commit_descriptions(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "add diff visualizer" in output

    def test_contains_file_paths(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "diff_visualizer" in output

    def test_contains_test_counts(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "174" in output
        assert "140" in output

    def test_contains_heatmap_section(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "Heatmap" in output

    def test_contains_summary_table(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "Files changed" in output

    def test_biggest_change_callout(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "Biggest change" in output

    def test_empty_commits_handled(self):
        diff = self._make_diff()
        diff.commits = []
        output = render_session_diff(diff)
        assert "Session 3" in output  # Still renders

    def test_empty_file_deltas_handled(self):
        diff = self._make_diff()
        diff.file_deltas = []
        output = render_session_diff(diff)
        assert "Session 3" in output

    def test_commit_types_with_emoji(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert "feat" in output
        assert "test" in output

    def test_is_valid_markdown(self):
        diff = self._make_diff()
        output = render_session_diff(diff)
        assert output.startswith("#")
        assert "|" in output


# ---------------------------------------------------------------------------
# write_session_diff
# ---------------------------------------------------------------------------


class TestWriteSessionDiff:
    def test_writes_to_output_path(self, tmp_path):
        output_path = tmp_path / "docs" / "session_3_diff.md"
        with patch("src.diff_visualizer._run_git", return_value=""):
            with patch("src.diff_visualizer._count_tests", return_value=174):
                content = write_session_diff(
                    tmp_path,
                    session_number=3,
                    output_path=output_path,
                    start_sha="abc1234",
                    end_sha="def5678",
                )
        assert output_path.exists()
        assert "Session 3" in content

    def test_returns_content_string(self, tmp_path):
        with patch("src.diff_visualizer._run_git", return_value=""):
            with patch("src.diff_visualizer._count_tests", return_value=100):
                content = write_session_diff(
                    tmp_path,
                    session_number=1,
                    start_sha="aaa",
                    end_sha="bbb",
                )
        assert isinstance(content, str)
        assert len(content) > 0

    def test_no_output_path_does_not_write(self, tmp_path):
        with patch("src.diff_visualizer._run_git", return_value=""):
            with patch("src.diff_visualizer._count_tests", return_value=100):
                write_session_diff(
                    tmp_path,
                    session_number=1,
                    start_sha="aaa",
                    end_sha="bbb",
                )
        # Nothing should be written to tmp_path
        md_files = list(tmp_path.glob("*.md"))
        assert len(md_files) == 0


# ---------------------------------------------------------------------------
# build_session_diff with mocked git
# ---------------------------------------------------------------------------


class TestBuildSessionDiff:
    def test_builds_with_mocked_git(self, tmp_path):
        numstat_output = "100\t0\tsrc/new_file.py\n50\t20\tsrc/existing.py\n"
        name_status_output = "A\tsrc/new_file.py\nM\tsrc/existing.py\n"

        def mock_run_git(args, cwd):
            if "--numstat" in args:
                return numstat_output
            elif "--name-status" in args:
                return name_status_output
            elif "log" in args:
                return "abc12345\t2026-02-27 03:00:00 +0000\t[nightshift] feat: new file\n"
            return ""

        with patch("src.diff_visualizer._run_git", side_effect=mock_run_git):
            with patch("src.diff_visualizer._count_tests", return_value=174):
                diff = build_session_diff(tmp_path, 3, start_sha="abc", end_sha="def")

        assert diff.session_number == 3
        assert len(diff.file_deltas) == 2
        assert diff.tests_after == 174
