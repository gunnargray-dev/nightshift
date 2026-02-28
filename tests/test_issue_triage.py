"""Tests for src/issue_triage.py — 41 tests."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.issue_triage import (
    triage_issues,
    TriageReport,
    TriagedIssue,
    _classify_category,
    _compute_priority,
    load_issues_from_file,
    save_triage_report,
    save_triage_json,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_issue(
    number=1,
    title="Test issue",
    body="",
    labels=None,
    comments=0,
    created_at="2026-02-27T00:00:00Z",
) -> dict:
    """Build a minimal raw GitHub issue dict."""
    return {
        "number": number,
        "title": title,
        "body": body,
        "labels": labels or [],
        "comments": comments,
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# _classify_category
# ---------------------------------------------------------------------------

class TestClassifyCategory:
    def test_bug_via_label(self):
        assert _classify_category("foo", "bar", ["bug"]) == "BUG"

    def test_bug_via_title_text(self):
        assert _classify_category("Something is broken", "", []) == "BUG"

    def test_bug_via_body_text(self):
        assert _classify_category("issue", "it crashes on startup", []) == "BUG"

    def test_feature_via_label(self):
        assert _classify_category("foo", "bar", ["feature"]) == "FEATURE"

    def test_feature_via_text(self):
        result = _classify_category("[request] add dark mode", "", [])
        assert result == "FEATURE"

    def test_enhancement_via_label(self):
        assert _classify_category("foo", "bar", ["enhancement"]) == "ENHANCEMENT"

    def test_enhancement_via_text(self):
        result = _classify_category("improve the stats display", "", [])
        assert result in ("ENHANCEMENT", "FEATURE")  # both are valid

    def test_question_via_label(self):
        assert _classify_category("foo", "bar", ["question"]) == "QUESTION"

    def test_question_via_text(self):
        result = _classify_category("How do I run tests?", "", [])
        assert result == "QUESTION"

    def test_chore_via_text(self):
        result = _classify_category("Upgrade dependencies", "", [])
        assert result == "CHORE"

    def test_unknown_for_gibberish(self):
        result = _classify_category("xyz qrs mno", "pqr abc", [])
        assert result == "UNKNOWN"

    def test_label_overrides_text(self):
        result = _classify_category("how do I do this bug", "broken crash", ["question"])
        assert result == "QUESTION"


# ---------------------------------------------------------------------------
# _compute_priority
# ---------------------------------------------------------------------------

class TestComputePriority:
    def test_human_priority_label_raises_score(self):
        level, score, rationale = _compute_priority("UNKNOWN", ["human-priority"], 0, True)
        assert level <= 2
        assert score >= 3

    def test_bug_category_boosts_priority(self):
        level, score, rationale = _compute_priority("BUG", [], 0, False)
        assert score >= 2

    def test_triage_low_label_lowers_priority(self):
        level, score, _ = _compute_priority("UNKNOWN", ["triage:low"], 0, False)
        assert level >= 4

    def test_many_comments_boosts_score(self):
        _, score_few, _ = _compute_priority("UNKNOWN", [], 1, False)
        _, score_many, _ = _compute_priority("UNKNOWN", [], 5, False)
        assert score_many > score_few

    def test_wontfix_lowest_priority(self):
        level, score, _ = _compute_priority("UNKNOWN", ["wontfix"], 0, False)
        assert level == 5

    def test_bug_human_priority_combo(self):
        level, score, rationale = _compute_priority("BUG", ["human-priority", "triage:high"], 5, True)
        assert level == 1
        assert score >= 7

    def test_priority_level_range(self):
        for labels in [[], ["bug"], ["human-priority"], ["triage:low"], ["wontfix"]]:
            level, _, _ = _compute_priority("UNKNOWN", labels, 0, False)
            assert 1 <= level <= 5

    def test_rationale_not_empty_when_labels_present(self):
        _, _, rationale = _compute_priority("BUG", ["human-priority"], 3, True)
        assert len(rationale) > 0


# ---------------------------------------------------------------------------
# triage_issues
# ---------------------------------------------------------------------------

class TestTriageIssues:
    def test_empty_list_returns_empty_report(self):
        report = triage_issues([])
        assert report.total_open == 0
        assert len(report.issues) == 0

    def test_single_issue_returns_single_triage(self):
        issues = [make_issue(title="It crashes on startup", labels=["bug"])]
        report = triage_issues(issues)
        assert len(report.issues) == 1
        assert report.issues[0].category == "BUG"
        assert report.issues[0].priority <= 3

    def test_human_priority_issue_gets_high_priority(self):
        issues = [make_issue(title="Please add a dashboard", labels=["human-priority"])]
        report = triage_issues(issues)
        assert report.issues[0].priority <= 2

    def test_labels_as_dicts(self):
        """GitHub API returns labels as {"name": "...", ...} dicts."""
        issues = [make_issue(labels=[{"name": "bug"}, {"name": "human-priority"}])]
        report = triage_issues(issues)
        assert "bug" in report.issues[0].labels
        assert "human-priority" in report.issues[0].labels

    def test_multiple_issues_sorted_in_top_n(self):
        issues = [
            make_issue(1, "Low priority feature", labels=["triage:low"]),
            make_issue(2, "Critical bug crash", labels=["bug", "human-priority"]),
            make_issue(3, "Medium enhancement", labels=["enhancement"]),
        ]
        report = triage_issues(issues)
        top = report.top_n(3)
        assert top[0].number == 2

    def test_top_n_limits_results(self):
        issues = [make_issue(i) for i in range(1, 11)]
        report = triage_issues(issues)
        assert len(report.top_n(3)) == 3

    def test_by_category_groups_correctly(self):
        issues = [
            make_issue(1, "Crash on start", labels=["bug"]),
            make_issue(2, "Add feature X", labels=["feature"]),
            make_issue(3, "Another bug", labels=["bug"]),
        ]
        report = triage_issues(issues)
        by_cat = report.by_category()
        assert len(by_cat.get("BUG", [])) == 2
        assert len(by_cat.get("FEATURE", [])) == 1

    def test_body_truncated_at_500_chars(self):
        long_body = "x" * 600
        issues = [make_issue(body=long_body)]
        report = triage_issues(issues)
        assert len(report.issues[0].body) <= 500

    def test_generated_at_is_set(self):
        report = triage_issues([])
        assert report.generated_at != ""

    def test_comment_count_field_alternative(self):
        """Supports both 'comments' and 'comment_count' keys."""
        issue = {"number": 1, "title": "Test", "body": "", "labels": [], "comment_count": 5}
        report = triage_issues([issue])
        assert report.issues[0].comment_count == 5


# ---------------------------------------------------------------------------
# TriageReport.to_markdown
# ---------------------------------------------------------------------------

class TestTriageReportMarkdown:
    def test_empty_report_markdown(self):
        report = TriageReport(issues=[])
        md = report.to_markdown()
        assert "No open issues" in md

    def test_markdown_has_table_header(self):
        issues = [make_issue(title="A bug", labels=["bug"])]
        report = triage_issues(issues)
        md = report.to_markdown()
        assert "| # | Title" in md

    def test_markdown_includes_all_issues(self):
        issues = [make_issue(i, f"Issue {i}") for i in range(1, 4)]
        report = triage_issues(issues)
        md = report.to_markdown()
        for i in range(1, 4):
            assert f"#{i}" in md

    def test_markdown_has_category_breakdown(self):
        issues = [make_issue(1, "Bug!", labels=["bug"])]
        report = triage_issues(issues)
        md = report.to_markdown()
        assert "Category Breakdown" in md

    def test_priority_emoji_in_markdown(self):
        issues = [make_issue(1, "Critical", labels=["human-priority", "bug"])]
        report = triage_issues(issues)
        md = report.to_markdown()
        assert "🔴" in md or "🟠" in md


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

class TestFileIO:
    def test_load_issues_from_file(self, tmp_path):
        data = [make_issue(1, "Test")]
        p = tmp_path / "issues.json"
        p.write_text(json.dumps(data))
        loaded = load_issues_from_file(p)
        assert len(loaded) == 1
        assert loaded[0]["number"] == 1

    def test_save_triage_report(self, tmp_path):
        issues = [make_issue(1, "A bug", labels=["bug"])]
        report = triage_issues(issues)
        out = tmp_path / "triage_report.md"
        save_triage_report(report, out)
        assert out.exists()
        content = out.read_text()
        assert "Triage Report" in content

    def test_save_triage_json(self, tmp_path):
        issues = [make_issue(1, "A bug", labels=["bug"])]
        report = triage_issues(issues)
        out = tmp_path / "triage.json"
        save_triage_json(report, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert "issues" in data
        assert data["total_open"] == 1

    def test_save_creates_parent_dirs(self, tmp_path):
        issues = [make_issue(1)]
        report = triage_issues(issues)
        out = tmp_path / "docs" / "nested" / "report.md"
        save_triage_report(report, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# TriagedIssue
# ---------------------------------------------------------------------------

class TestTriagedIssue:
    def test_to_dict(self):
        issue = TriagedIssue(
            number=42,
            title="test",
            body="body",
            labels=["bug"],
            comment_count=2,
            created_at="2026-01-01",
            category="BUG",
            priority=1,
            priority_score=5.0,
            rationale="label:bug(+2)",
        )
        d = issue.to_dict()
        assert d["number"] == 42
        assert d["category"] == "BUG"

    def test_to_markdown_row(self):
        issue = TriagedIssue(
            number=7,
            title="Critical crash",
            body="",
            labels=["bug"],
            comment_count=0,
            created_at="2026-01-01",
            category="BUG",
            priority=1,
            priority_score=4.0,
            rationale="label:bug(+2)",
        )
        row = issue.to_markdown_row()
        assert "#7" in row
        assert "BUG" in row
        assert "P1" in row
