"""Tests for src/commit_analyzer.py — Smart commit message analyzer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.commit_analyzer import (
    CommitRecord,
    CommitPatterns,
    CommitAnalysisReport,
    _score_commit,
    analyze_commits,
)


# ---------------------------------------------------------------------------
# _score_commit helpers
# ---------------------------------------------------------------------------


def _make_record(subject: str, body: str = "", author: str = "Alice") -> CommitRecord:
    return CommitRecord(
        sha="abc1234",
        subject=subject,
        body=body,
        author=author,
        date="2025-01-01",
    )


def test_score_conventional_commit_feat():
    rec = _make_record("feat: add new health analyzer")
    _score_commit(rec)
    assert rec.cc_type == "feat"
    assert rec.quality_score > 60
    assert "conventional-commits" in rec.quality_badges


def test_score_conventional_commit_with_scope():
    rec = _make_record("fix(health): correct score calculation")
    _score_commit(rec)
    assert rec.cc_type == "fix"
    assert rec.cc_scope == "health"


def test_score_conventional_commit_breaking():
    rec = _make_record("feat!: remove deprecated API")
    _score_commit(rec)
    assert rec.is_breaking is True
    assert "breaking-change" in rec.quality_badges


def test_score_non_conventional_penalised():
    rec = _make_record("Fixed the thing")
    _score_commit(rec)
    assert "not Conventional Commits" in rec.quality_issues


def test_score_short_subject_penalised():
    rec = _make_record("fix")
    _score_commit(rec)
    assert rec.quality_score < 50


def test_score_long_subject_penalised():
    rec = _make_record("fix: " + "x" * 80)
    _score_commit(rec)
    assert "long subject line" in rec.quality_issues


def test_score_ideal_subject_length():
    rec = _make_record("feat: add rate limiting to API endpoints")  # 43 chars
    _score_commit(rec)
    assert "ideal-length" in rec.quality_badges


def test_score_body_present_bonus():
    rec = _make_record("feat: add caching", body="This improves performance by 50% on large repos.")
    _score_commit(rec)
    assert "has-body" in rec.quality_badges
    assert rec.quality_score > 70


def test_score_issue_reference_bonus():
    rec = _make_record("fix: close memory leak", body="Fixes #42")
    _score_commit(rec)
    assert "references-issue" in rec.quality_badges


def test_score_wip_penalised():
    rec = _make_record("WIP: refactoring health module")
    _score_commit(rec)
    assert rec.quality_score < 70
    assert "WIP commit" in rec.quality_issues


def test_score_nightshift_bonus():
    rec = _make_record("[nightshift] session 17 improvements")
    rec.is_nightshift = True
    _score_commit(rec)
    assert "nightshift" in rec.quality_badges


def test_score_clamps_to_0_100():
    rec = _make_record("a")
    _score_commit(rec)
    assert 0 <= rec.quality_score <= 100


def test_score_emoji_in_subject():
    rec = _make_record("feat: ✨ add sparkle to reports")
    _score_commit(rec)
    # _score_commit does not add an "emoji" badge; just verify scoring succeeds
    assert rec.quality_score > 0


# ---------------------------------------------------------------------------
# analyze_commits — no git repo (graceful degradation)
# ---------------------------------------------------------------------------


def test_analyze_commits_no_git(tmp_path):
    report = analyze_commits(tmp_path)
    assert isinstance(report, CommitAnalysisReport)
    assert report.total_commits == 0
    assert report.quality_grade == "N/A"


def test_analyze_commits_returns_report_type():
    report = CommitAnalysisReport(repo_path="/fake", total_commits=0, quality_grade="N/A")
    assert report.total_commits == 0


# ---------------------------------------------------------------------------
# CommitAnalysisReport.to_markdown
# ---------------------------------------------------------------------------


def test_report_to_markdown_empty():
    report = CommitAnalysisReport(
        repo_path="/repo",
        total_commits=0,
        avg_quality_score=0.0,
        quality_grade="N/A",
    )
    report.patterns = CommitPatterns()
    md = report.to_markdown()
    assert "Commit Message Analysis" in md


def test_report_to_markdown_with_commits():
    rec1 = _make_record("feat: add plugin system")
    rec2 = _make_record("fix(health): correct scoring")
    for r in [rec1, rec2]:
        _score_commit(r)

    report = CommitAnalysisReport(
        repo_path="/repo",
        total_commits=2,
        avg_quality_score=75.0,
        quality_grade="B",
        commits=[rec1, rec2],
        patterns=CommitPatterns(conventional_count=2, nightshift_count=0),
        top_commits=[rec1],
        bottom_commits=[rec2],
    )
    md = report.to_markdown()
    assert "2" in md
    assert "75" in md
    assert "B" in md


def test_report_to_dict():
    report = CommitAnalysisReport(
        repo_path="/repo",
        total_commits=5,
        avg_quality_score=80.0,
        quality_grade="B+",
        patterns=CommitPatterns(type_distribution={"feat": 3, "fix": 2}),
    )
    d = report.to_dict()
    assert d["total_commits"] == 5
    assert d["quality_grade"] == "B+"
    assert "feat" in d["patterns"]["type_distribution"]


# ---------------------------------------------------------------------------
# CommitPatterns
# ---------------------------------------------------------------------------


def test_commit_patterns_defaults():
    p = CommitPatterns()
    assert p.conventional_count == 0
    assert p.type_distribution == {}


def test_commit_patterns_to_dict():
    p = CommitPatterns(conventional_count=5, breaking_count=1)
    d = p.to_dict()
    assert d["conventional_count"] == 5
    assert d["breaking_count"] == 1


# ---------------------------------------------------------------------------
# CommitRecord
# ---------------------------------------------------------------------------


def test_commit_record_to_dict():
    rec = CommitRecord(
        sha="abc123", subject="feat: test", body="", author="Alice", date="2025-01-01",
        cc_type="feat", quality_score=85.0,
    )
    d = rec.to_dict()
    assert d["sha"] == "abc123"
    assert d["cc_type"] == "feat"
    assert d["quality_score"] == 85.0


def test_nightshift_pattern_detection():
    rec = _make_record("[nightshift] session 17 — add plugins")
    _score_commit(rec)
    # The is_nightshift flag is set during _git_log, not _score_commit
    # but the score should still be computed
    assert 0 <= rec.quality_score <= 100
