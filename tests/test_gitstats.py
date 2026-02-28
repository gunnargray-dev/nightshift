"""Tests for src/gitstats.py — Git Statistics Deep-Dive."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.gitstats import (
    CommitRecord,
    ContributorStats,
    GitStatsReport,
    compute_git_stats,
    save_git_stats_report,
    _parse_commits,
    _git,
)


class TestCommitRecord:
    def _make(self, ins=100, dels=20) -> CommitRecord:
        return CommitRecord(
            sha="abc123" * 6 + "ab", author="Alice", date="2026-02-01",
            weekday="Sunday", hour=23, insertions=ins, deletions=dels,
            files_changed=5, subject="feat: add feature",
        )

    def test_churn(self):
        r = self._make(ins=100, dels=40)
        assert r.churn == 140

    def test_net(self):
        r = self._make(ins=100, dels=40)
        assert r.net == 60

    def test_net_negative(self):
        r = self._make(ins=10, dels=50)
        assert r.net == -40


class TestContributorStats:
    def test_churn(self):
        c = ContributorStats(name="Alice", commits=5, insertions=200, deletions=50)
        assert c.churn == 250

    def test_to_dict(self):
        c = ContributorStats(name="Bob", commits=10, insertions=500, deletions=100)
        d = c.to_dict()
        assert d["name"] == "Bob"
        assert d["commits"] == 10


class TestParseCommits:
    def _sha(self) -> str:
        return "a" * 40

    def test_parse_single_commit(self):
        line = f"{self._sha()}|Alice|2026-01-15 23:45:00 +0000|feat: add feature"
        records = _parse_commits(line)
        assert len(records) == 1
        assert records[0].author == "Alice"
        assert records[0].date == "2026-01-15"
        assert records[0].hour == 23
        assert records[0].subject == "feat: add feature"

    def test_parse_multiple_commits(self):
        sha = self._sha()
        lines = "\n".join([
            f"{sha}|Alice|2026-01-15 23:45:00 +0000|feat: a",
            f"{sha}|Bob|2026-01-16 10:00:00 +0000|fix: b",
            f"{sha}|Carol|2026-01-17 03:00:00 +0000|chore: c",
        ])
        records = _parse_commits(lines)
        assert len(records) == 3
        assert records[0].author == "Alice"
        assert records[1].author == "Bob"
        assert records[2].author == "Carol"

    def test_weekday_computed(self):
        sha = self._sha()
        line = f"{sha}|Alice|2026-01-15 10:00:00 +0000|test"
        records = _parse_commits(line)
        assert records[0].weekday == "Thursday"

    def test_empty_input(self):
        records = _parse_commits("")
        assert records == []

    def test_invalid_line_skipped(self):
        records = _parse_commits("not a valid commit line\nfoo bar baz")
        assert records == []

    def test_hour_extraction(self):
        sha = self._sha()
        line = f"{sha}|Alice|2026-01-15 14:30:00 +0000|commit"
        records = _parse_commits(line)
        assert records[0].hour == 14


class TestGitStatsReport:
    def _make_report(self) -> GitStatsReport:
        return GitStatsReport(
            total_commits=50, total_insertions=5000, total_deletions=2000,
            total_files_changed=200, avg_insertions_per_commit=100.0,
            avg_deletions_per_commit=40.0, avg_churn_per_commit=140.0,
            avg_files_per_commit=4.0,
            commits_by_weekday={"Monday": 5, "Tuesday": 10, "Wednesday": 8},
            commits_by_hour={23: 15, 0: 10, 1: 5},
            contributors=[
                ContributorStats("Alice", 30, 3000, 1200),
                ContributorStats("Bob", 20, 2000, 800),
            ],
            estimated_pr_count=37, avg_pr_size_lines=189.0, active_days=20,
            first_commit_date="2025-11-01", last_commit_date="2026-02-28",
            churn_rate_per_day=350.0, recent_velocity=15,
        )

    def test_to_dict_structure(self):
        r = self._make_report()
        d = r.to_dict()
        assert "total_commits" in d
        assert "contributors" in d
        assert "commits_by_weekday" in d
        assert isinstance(d["contributors"], list)

    def test_to_json_valid(self):
        r = self._make_report()
        data = json.loads(r.to_json())
        assert data["total_commits"] == 50
        assert data["estimated_pr_count"] == 37

    def test_to_markdown_has_overview(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "Overview" in md
        assert "50" in md

    def test_to_markdown_has_contributors(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "Alice" in md

    def test_to_markdown_has_weekday(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "Mon" in md or "Monday" in md

    def test_to_markdown_has_hour(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "23h" in md or "UTC" in md

    def test_to_markdown_empty(self):
        r = GitStatsReport()
        md = r.to_markdown()
        assert "Git Statistics" in md

    def test_date_range_shown(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "2025-11-01" in md
        assert "2026-02-28" in md


class TestGitHelper:
    def test_returns_string(self, tmp_path):
        result = _git(["--version"], tmp_path)
        assert isinstance(result, str)

    def test_returns_empty_on_failure(self, tmp_path):
        result = _git(["log", "--format=%H", "nonexistent-branch"], tmp_path)
        assert isinstance(result, str)


class TestComputeGitStats:
    def test_empty_repo_returns_report(self, tmp_path):
        with patch("src.gitstats._git", return_value=""):
            report = compute_git_stats(repo_path=tmp_path)
        assert isinstance(report, GitStatsReport)
        assert report.total_commits == 0

    def test_with_mocked_log(self, tmp_path):
        sha = "a" * 40
        fake_log = f"{sha}|Alice|2026-02-01 23:00:00 +0000|feat: session 15"

        def mock_git(cmd, cwd):
            if "--format=%H|%aN|%ai|%s" in cmd:
                return fake_log
            if "--format=%s" in cmd:
                return "Merge pull request #37 from feature"
            return ""

        with patch("src.gitstats._git", side_effect=mock_git):
            report = compute_git_stats(repo_path=tmp_path)

        assert report.total_commits == 1
        assert "Alice" in [c.name for c in report.contributors]
        assert report.estimated_pr_count == 1

    def test_churn_rate_calculation(self, tmp_path):
        sha = "b" * 40
        fake_log = "\n".join([
            f"{sha}|Alice|2026-02-01 10:00:00 +0000|feat: a",
            f"{sha}|Alice|2026-02-02 11:00:00 +0000|feat: b",
        ])

        def mock_git(cmd, cwd):
            if "--format=%H|%aN|%ai|%s" in cmd:
                return fake_log
            return ""

        with patch("src.gitstats._git", side_effect=mock_git):
            report = compute_git_stats(repo_path=tmp_path)

        assert report.active_days == 2
        assert report.churn_rate_per_day == 0.0

    def test_contributors_sorted_by_commits(self, tmp_path):
        sha = "c" * 40
        fake_log = "\n".join([
            f"{sha}|Alice|2026-01-01 10:00:00 +0000|commit",
            f"{sha}|Bob|2026-01-02 11:00:00 +0000|commit",
            f"{sha}|Bob|2026-01-03 12:00:00 +0000|commit",
        ])

        def mock_git(cmd, cwd):
            if "--format=%H|%aN|%ai|%s" in cmd:
                return fake_log
            return ""

        with patch("src.gitstats._git", side_effect=mock_git):
            report = compute_git_stats(repo_path=tmp_path)

        assert report.contributors[0].name == "Bob"


class TestSaveGitStatsReport:
    def test_creates_files(self, tmp_path):
        r = GitStatsReport(total_commits=10)
        out = tmp_path / "git_stats.md"
        save_git_stats_report(r, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_markdown_content(self, tmp_path):
        r = GitStatsReport(total_commits=42, active_days=5)
        out = tmp_path / "git_stats.md"
        save_git_stats_report(r, out)
        text = out.read_text()
        assert "42" in text

    def test_json_valid(self, tmp_path):
        r = GitStatsReport(total_commits=7)
        out = tmp_path / "git_stats.md"
        save_git_stats_report(r, out)
        data = json.loads(out.with_suffix(".json").read_text())
        assert data["total_commits"] == 7
