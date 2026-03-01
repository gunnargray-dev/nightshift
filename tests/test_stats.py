"""Tests for the Awake self-stats engine (src/stats.py)."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.stats import (
    RepoStats,
    _run_git,
    count_commits,
    count_lines_changed,
    count_awake_sessions,
    get_commit_messages,
    parse_awake_log,
    compute_stats,
    update_readme_stats,
)


# ---------------------------------------------------------------------------
# RepoStats
# ---------------------------------------------------------------------------


class TestRepoStats:
    def test_defaults(self):
        stats = RepoStats()
        assert stats.nights_active == 0
        assert stats.total_prs == 0
        assert stats.total_commits == 0
        assert stats.lines_changed == 0
        assert stats.sessions == []

    def test_to_dict(self):
        stats = RepoStats(nights_active=3, total_prs=7, total_commits=42, lines_changed=1500)
        d = stats.to_dict()
        assert d["nights_active"] == 3
        assert d["total_prs"] == 7
        assert d["total_commits"] == 42
        assert d["lines_changed"] == 1500

    def test_readme_table_format(self):
        stats = RepoStats(nights_active=5, total_prs=12, total_commits=88, lines_changed=3200)
        table = stats.readme_table()
        assert "| Nights active | 5 |" in table
        assert "| Total PRs | 12 |" in table
        assert "| Total commits | 88 |" in table
        assert "| Lines changed | 3200 |" in table
        assert table.startswith("| Metric | Count |")

    def test_readme_table_zero_values(self):
        stats = RepoStats()
        table = stats.readme_table()
        assert "| Nights active | 0 |" in table


# ---------------------------------------------------------------------------
# _run_git helper
# ---------------------------------------------------------------------------


class TestRunGit:
    def test_returns_empty_on_failure(self, tmp_path):
        # Run in a non-git directory — git rev-list will fail
        result = _run_git(["rev-list", "--count", "HEAD"], cwd=tmp_path)
        assert result == ""

    def test_returns_empty_on_missing_git(self, tmp_path):
        with patch("src.stats.subprocess.run", side_effect=FileNotFoundError):
            result = _run_git(["rev-list", "--count", "HEAD"], cwd=tmp_path)
        assert result == ""

    def test_returns_empty_on_timeout(self, tmp_path):
        with patch("src.stats.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            result = _run_git(["log"], cwd=tmp_path)
        assert result == ""


# ---------------------------------------------------------------------------
# count_commits
# ---------------------------------------------------------------------------


class TestCountCommits:
    def test_returns_int(self, tmp_path):
        with patch("src.stats._run_git", return_value="42"):
            result = count_commits(tmp_path)
        assert result == 42

    def test_handles_empty_output(self, tmp_path):
        with patch("src.stats._run_git", return_value=""):
            result = count_commits(tmp_path)
        assert result == 0

    def test_handles_non_integer(self, tmp_path):
        with patch("src.stats._run_git", return_value="not-a-number"):
            result = count_commits(tmp_path)
        assert result == 0

    def test_real_git_repo(self, tmp_path):
        """Integration test: counts commits in a real temp git repo."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "first commit"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file2.txt").write_text("world")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second commit"], cwd=tmp_path, capture_output=True)

        count = count_commits(tmp_path)
        assert count == 2


# ---------------------------------------------------------------------------
# count_lines_changed
# ---------------------------------------------------------------------------


class TestCountLinesChanged:
    def test_parses_insertions_and_deletions(self, tmp_path):
        fake_output = textwrap.dedent("""\
            abc123 feat: add feature
             3 files changed, 42 insertions(+), 7 deletions(-)
            def456 fix: remove bug
             1 file changed, 10 insertions(+), 2 deletions(-)
        """)
        with patch("src.stats._run_git", return_value=fake_output):
            result = count_lines_changed(tmp_path)
        assert result == 42 + 7 + 10 + 2

    def test_handles_insertions_only(self, tmp_path):
        fake_output = " 1 file changed, 5 insertions(+)"
        with patch("src.stats._run_git", return_value=fake_output):
            result = count_lines_changed(tmp_path)
        assert result == 5

    def test_handles_empty_repo(self, tmp_path):
        with patch("src.stats._run_git", return_value=""):
            result = count_lines_changed(tmp_path)
        assert result == 0


# ---------------------------------------------------------------------------
# get_commit_messages
# ---------------------------------------------------------------------------


class TestGetCommitMessages:
    def test_returns_list(self, tmp_path):
        with patch("src.stats._run_git", return_value="feat: add thing\nfix: remove bug\n"):
            messages = get_commit_messages(tmp_path)
        assert messages == ["feat: add thing", "fix: remove bug"]

    def test_empty_repo(self, tmp_path):
        with patch("src.stats._run_git", return_value=""):
            messages = get_commit_messages(tmp_path)
        assert messages == []

    def test_filters_empty_lines(self, tmp_path):
        with patch("src.stats._run_git", return_value="msg1\n\n\nmsg2\n"):
            messages = get_commit_messages(tmp_path)
        assert messages == ["msg1", "msg2"]


# ---------------------------------------------------------------------------
# count_awake_sessions
# ---------------------------------------------------------------------------


class TestCountAwakeSessions:
    def test_counts_session_numbers(self, tmp_path):
        fake_log = textwrap.dedent("""\
            [awake] feat: add stats engine

            Session: 1

            [awake] feat: add logger

            Session: 1

            [awake] feat: add CI

            Session: 2
        """)
        with patch("src.stats._run_git", return_value=fake_log):
            count = count_awake_sessions(tmp_path)
        assert count == 2

    def test_no_awake_commits(self, tmp_path):
        with patch("src.stats._run_git", return_value=""):
            pass
        with patch("src.stats.get_commit_messages", return_value=[]):
            with patch("src.stats._run_git", return_value=""):
                count = count_awake_sessions(tmp_path)
        assert count == 0


# ---------------------------------------------------------------------------
# parse_awake_log
# ---------------------------------------------------------------------------


class TestParseAwakeLog:
    def test_parses_sessions(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(textwrap.dedent("""\
            # Awake Log

            ## Session 0 — February 27, 2026 (Setup)

            **Operator:** Gunnar Gray (human)

            ---

            ## Session 1 — February 28, 2026

            **Operator:** Computer (autonomous)
            - **Self-stats engine** → PR #1

            ---
        """))
        sessions = parse_awake_log(log)
        assert len(sessions) == 2
        assert sessions[0]["session"] == 0
        assert sessions[1]["session"] == 1
        assert sessions[1]["date"] == "February 28, 2026"

    def test_missing_log_returns_empty(self, tmp_path):
        result = parse_awake_log(tmp_path / "nonexistent.md")
        assert result == []

    def test_extracts_pr_references(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(textwrap.dedent("""\
            ## Session 1 — February 28, 2026

            PRs opened: PR #1, PR #2, PR #3

            ---
        """))
        sessions = parse_awake_log(log)
        assert sessions[0]["prs"] == 3


# ---------------------------------------------------------------------------
# compute_stats
# ---------------------------------------------------------------------------


class TestComputeStats:
    def test_returns_repo_stats(self, tmp_path):
        with patch("src.stats.count_commits", return_value=10):
            with patch("src.stats.count_lines_changed", return_value=500):
                with patch("src.stats.count_awake_sessions", return_value=2):
                    with patch("src.stats.parse_awake_log", return_value=[]):
                        stats = compute_stats(repo_path=tmp_path, pr_count=5)
        assert isinstance(stats, RepoStats)
        assert stats.total_commits == 10
        assert stats.lines_changed == 500
        assert stats.total_prs == 5
        assert stats.nights_active == 2

    def test_uses_log_sessions_when_git_returns_zero(self, tmp_path):
        log_sessions = [
            {"session": 1, "date": "Feb 28, 2026", "prs": 3, "tasks": 4},
        ]
        with patch("src.stats.count_commits", return_value=0):
            with patch("src.stats.count_lines_changed", return_value=0):
                with patch("src.stats.count_awake_sessions", return_value=0):
                    with patch("src.stats.parse_awake_log", return_value=log_sessions):
                        stats = compute_stats(repo_path=tmp_path)
        assert stats.nights_active == 1


# ---------------------------------------------------------------------------
# update_readme_stats
# ---------------------------------------------------------------------------


class TestUpdateReadmeStats:
    def test_replaces_existing_table(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text(textwrap.dedent("""\
            # Awake

            ## Stats

            | Metric | Count |
            |--------|-------|
            | Nights active | 0 |
            | Total PRs | 0 |
            | Total commits | 1 |
            | Lines changed | 0 |

            *Stats are updated by Computer each session.*
        """))
        stats = RepoStats(nights_active=1, total_prs=4, total_commits=25, lines_changed=800)
        new_content = update_readme_stats(readme, stats)
        assert "| Nights active | 1 |" in new_content
        assert "| Total PRs | 4 |" in new_content
        assert "| Total commits | 25 |" in new_content
        assert "| Lines changed | 800 |" in new_content
        assert "| Total PRs | 0 |" not in new_content

    def test_appends_when_no_stats_section(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# Awake\n\nSome content.\n")
        stats = RepoStats(nights_active=1, total_prs=1, total_commits=5, lines_changed=100)
        new_content = update_readme_stats(readme, stats)
        assert "## Stats" in new_content
        assert "| Nights active | 1 |" in new_content
