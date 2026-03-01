"""Tests for src/pr_scorer.py"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pr_scorer import (
    DimensionScore,
    PRScore,
    Leaderboard,
    _score_description_quality,
    _score_test_coverage_signal,
    _score_code_clarity,
    _score_diff_scope,
    _score_session_metadata,
    score_pr,
    load_scores,
    save_scores,
    upsert_score,
    render_leaderboard,
    render_pr_report,
)


# ---------------------------------------------------------------------------
# Data class tests
# ---------------------------------------------------------------------------


class TestPRScore:
    def _make_score(self, **kwargs) -> PRScore:
        dims = [
            DimensionScore("Description Quality", 15),
            DimensionScore("Test Coverage Signal", 18),
            DimensionScore("Code Clarity", 16),
            DimensionScore("Diff Scope", 20),
            DimensionScore("Session Metadata", 14),
        ]
        defaults = dict(
            pr_number=7,
            title="[awake] feat: add pr scorer",
            branch="awake/session-3-pr-scorer",
            session=3,
            dimensions=dims,
        )
        defaults.update(kwargs)
        return PRScore(**defaults)

    def test_total_sums_dimensions(self):
        score = self._make_score()
        assert score.total == 83

    def test_max_total_is_100(self):
        score = self._make_score()
        assert score.max_total == 100

    def test_grade_a_plus(self):
        dims = [DimensionScore(f"dim{i}", 20) for i in range(5)]
        score = self._make_score(dimensions=dims)
        assert score.grade == "A+"

    def test_grade_a(self):
        dims = [DimensionScore(f"dim{i}", 16) for i in range(5)]  # 80/100
        score = self._make_score(dimensions=dims)
        assert score.grade == "A"

    def test_grade_b(self):
        dims = [DimensionScore(f"dim{i}", 14) for i in range(5)]  # 70/100
        score = self._make_score(dimensions=dims)
        assert score.grade == "B"

    def test_grade_f(self):
        dims = [DimensionScore(f"dim{i}", 5) for i in range(5)]  # 25/100
        score = self._make_score(dimensions=dims)
        assert score.grade == "F"

    def test_scored_at_auto_populated(self):
        score = self._make_score()
        assert score.scored_at != ""


class TestLeaderboard:
    def _make_leaderboard(self) -> Leaderboard:
        def make_pr(num, scores):
            dims = [DimensionScore(f"d{i}", s) for i, s in enumerate(scores)]
            return PRScore(
                pr_number=num,
                title=f"PR {num}",
                branch=f"awake/session-1-pr-{num}",
                session=1,
                dimensions=dims,
            )

        return Leaderboard(
            scores=[
                make_pr(1, [15, 18, 16, 20, 14]),  # total=83
                make_pr(2, [20, 20, 20, 20, 20]),  # total=100
                make_pr(3, [10, 10, 10, 10, 10]),  # total=50
            ]
        )

    def test_ranked_by_descending_score(self):
        lb = self._make_leaderboard()
        ranked = lb.ranked
        assert ranked[0].pr_number == 2
        assert ranked[1].pr_number == 1
        assert ranked[2].pr_number == 3

    def test_average_score(self):
        lb = self._make_leaderboard()
        assert lb.average == round((83 + 100 + 50) / 3, 1)

    def test_top_is_highest_score(self):
        lb = self._make_leaderboard()
        assert lb.top.pr_number == 2

    def test_empty_leaderboard(self):
        lb = Leaderboard(scores=[])
        assert lb.average == 0.0
        assert lb.top is None
        assert lb.ranked == []


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------


class TestScoreDescriptionQuality:
    GOOD_BODY = """## What
Add a PR scorer module.

## Why
We need to track PR quality over time.

## How
Parse body text and score across 5 dimensions.

## Test Results
```
174 passed in 2.1s
```
Session: 3
"""

    def test_full_template_scores_high(self):
        result = _score_description_quality(self.GOOD_BODY)
        assert result.score >= 14

    def test_empty_body_scores_low(self):
        result = _score_description_quality("")
        assert result.score <= 4

    def test_has_what_section(self):
        body = "## What\nSomething\n"
        result = _score_description_quality(body)
        assert result.score > 0
        assert "What" in result.rationale

    def test_max_score_capped_at_20(self):
        result = _score_description_quality(self.GOOD_BODY)
        assert result.score <= 20

    def test_session_tag_adds_points(self):
        body_with = "## What\nSomething\nSession: 3"
        body_without = "## What\nSomething"
        with_score = _score_description_quality(body_with).score
        without_score = _score_description_quality(body_without).score
        assert with_score > without_score


class TestScoreTestCoverageSignal:
    def test_test_results_section_scores_high(self):
        body = "## Test Results\n```\n174 passed in 2.1s\n```\n"
        result = _score_test_coverage_signal(body)
        assert result.score >= 12

    def test_empty_body_low_score(self):
        result = _score_test_coverage_signal("## What\nSomething\n")
        assert result.score <= 4

    def test_pytest_output_in_code_block(self):
        body = "```\n174 passed in 3.2s\n```"
        result = _score_test_coverage_signal(body)
        assert result.score >= 8

    def test_max_score_capped(self):
        body = "## Test Results\n```\n174 passed\n```\n174 tests"
        result = _score_test_coverage_signal(body)
        assert result.score <= 20


class TestScoreCodeClarity:
    def test_awake_format_scores_high(self):
        title = "[awake] feat: add pr scorer"
        branch = "awake/session-3-pr-scorer"
        result = _score_code_clarity(title, branch)
        assert result.score >= 16

    def test_no_format_scores_low(self):
        result = _score_code_clarity("random PR title", "feature/random")
        assert result.score < 16

    def test_awake_branch_prefix_adds_points(self):
        good = _score_code_clarity("title", "awake/session-3-feature")
        basic = _score_code_clarity("title", "some-branch")
        assert good.score > basic.score

    def test_max_score_capped(self):
        result = _score_code_clarity(
            "[awake] feat: description",
            "awake/session-3-feature"
        )
        assert result.score <= 20


class TestScoreDiffScope:
    def test_ideal_scope_scores_20(self):
        result = _score_diff_scope(100, 50)  # total=150, ideal range
        assert result.score == 20

    def test_empty_diff_scores_zero(self):
        result = _score_diff_scope(0, 0)
        assert result.score == 0

    def test_very_large_diff_scores_low(self):
        result = _score_diff_scope(5000, 2000)
        assert result.score <= 10

    def test_small_focused_change(self):
        result = _score_diff_scope(20, 5)  # total=25, focused
        assert result.score >= 8

    def test_max_score_capped(self):
        result = _score_diff_scope(100, 80)
        assert result.score <= 20


class TestScoreSessionMetadata:
    def test_full_metadata_scores_high(self):
        body = "## What\nAdd scorer.\nSession: 3\n" * 3
        result = _score_session_metadata(body, "[awake] feat: add scorer", "awake/session-3-scorer")
        assert result.score >= 14

    def test_no_metadata_scores_low(self):
        result = _score_session_metadata("brief", "random title", "random-branch")
        assert result.score <= 4

    def test_awake_tag_in_title(self):
        with_tag = _score_session_metadata("body", "[awake] feat: x", "branch")
        without_tag = _score_session_metadata("body", "feat: x", "branch")
        assert with_tag.score >= without_tag.score

    def test_session_number_in_branch(self):
        with_session = _score_session_metadata("body", "title", "awake/session-3-feature")
        without_session = _score_session_metadata("body", "title", "awake/feature")
        assert with_session.score > without_session.score


# ---------------------------------------------------------------------------
# Main score_pr function
# ---------------------------------------------------------------------------


SAMPLE_PR_BODY = """## What
Add a PR quality scorer that analyzes PRs across 5 dimensions.

## Why
Tracking PR quality over time enables the system to improve its own output quality.
This is the kind of self-aware tooling that makes awake genuinely viral.

## How
Parse PR body text, title, and branch name. Score each dimension 0-20.
Store scores in docs/pr_scores.json.

## Test Results
```
58 passed in 1.2s
```
Session: 3
"""


class TestScorePR:
    def test_returns_pr_score_object(self):
        result = score_pr(
            pr_number=7,
            title="[awake] feat: add pr scorer",
            body=SAMPLE_PR_BODY,
            branch="awake/session-3-pr-scorer",
            lines_added=300,
            lines_deleted=0,
        )
        assert isinstance(result, PRScore)

    def test_score_is_bounded(self):
        result = score_pr(7, "[awake] feat: x", SAMPLE_PR_BODY, "awake/session-3-x", 200, 50)
        assert 0 <= result.total <= 100

    def test_five_dimensions(self):
        result = score_pr(7, "title", "body", "branch", 0, 0)
        assert len(result.dimensions) == 5

    def test_extracts_session_from_body(self):
        result = score_pr(7, "title", "Session: 3\nbody", "branch", 0, 0)
        assert result.session == 3

    def test_extracts_session_from_branch(self):
        result = score_pr(7, "title", "body", "awake/session-2-feature", 0, 0)
        assert result.session == 2

    def test_explicit_session_overrides(self):
        result = score_pr(7, "title", "Session: 3\nbody", "awake/session-2-x", 0, 0, session=5)
        assert result.session == 5

    def test_perfect_pr_scores_high(self):
        result = score_pr(
            1,
            "[awake] feat: add readme updater",
            SAMPLE_PR_BODY,
            "awake/session-3-readme-updater",
            lines_added=200,
            lines_deleted=50,
            session=3,
        )
        assert result.total >= 70

    def test_empty_pr_scores_low(self):
        result = score_pr(99, "untitled", "", "branch", 0, 0)
        assert result.total < 40


# ---------------------------------------------------------------------------
# Storage tests
# ---------------------------------------------------------------------------


class TestStorage:
    def _make_score(self, num: int) -> PRScore:
        dims = [DimensionScore(f"d{i}", 15 + i) for i in range(5)]
        return PRScore(
            pr_number=num,
            title=f"PR #{num}",
            branch=f"awake/session-3-pr-{num}",
            session=3,
            dimensions=dims,
            scored_at="2026-02-27T03:00:00+00:00",
        )

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "pr_scores.json"
        scores = [self._make_score(1), self._make_score(2)]
        save_scores(scores, path)
        loaded = load_scores(path)
        assert len(loaded) == 2
        assert loaded[0].pr_number in (1, 2)

    def test_load_missing_file_returns_empty(self, tmp_path):
        result = load_scores(tmp_path / "missing.json")
        assert result == []

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        path = tmp_path / "scores.json"
        path.write_text("NOT JSON", encoding="utf-8")
        result = load_scores(path)
        assert result == []

    def test_upsert_adds_new_score(self, tmp_path):
        path = tmp_path / "scores.json"
        score = self._make_score(1)
        upsert_score(score, path)
        loaded = load_scores(path)
        assert len(loaded) == 1
        assert loaded[0].pr_number == 1

    def test_upsert_replaces_existing(self, tmp_path):
        path = tmp_path / "scores.json"
        score_v1 = self._make_score(1)
        upsert_score(score_v1, path)
        dims = [DimensionScore(f"d{i}", 20) for i in range(5)]
        score_v2 = PRScore(1, "Updated", "awake/updated", 3, dims, "2026-02-27T04:00:00+00:00")
        upsert_score(score_v2, path)
        loaded = load_scores(path)
        assert len(loaded) == 1
        assert loaded[0].total == 100

    def test_saves_multiple_and_loads_correctly(self, tmp_path):
        path = tmp_path / "scores.json"
        for i in range(5):
            upsert_score(self._make_score(i + 1), path)
        loaded = load_scores(path)
        assert len(loaded) == 5

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "docs" / "sub" / "scores.json"
        save_scores([self._make_score(1)], path)
        assert path.exists()


# ---------------------------------------------------------------------------
# Rendering tests
# ---------------------------------------------------------------------------


class TestRenderLeaderboard:
    def _make_leaderboard(self) -> Leaderboard:
        def make_pr(num, total_per_dim):
            dims = [DimensionScore(f"d{i}", total_per_dim) for i in range(5)]
            return PRScore(num, f"PR {num}", f"awake/session-3-pr-{num}", 3, dims)

        return Leaderboard(scores=[
            make_pr(1, 18),  # 90
            make_pr(2, 16),  # 80
            make_pr(3, 10),  # 50
        ])

    def test_contains_pr_numbers(self):
        lb = self._make_leaderboard()
        output = render_leaderboard(lb)
        assert "#1" in output or "1" in output

    def test_contains_grade(self):
        lb = self._make_leaderboard()
        output = render_leaderboard(lb)
        assert "A" in output or "B" in output

    def test_contains_average(self):
        lb = self._make_leaderboard()
        output = render_leaderboard(lb)
        assert "Average" in output or "average" in output

    def test_is_markdown_table(self):
        lb = self._make_leaderboard()
        output = render_leaderboard(lb)
        assert "|" in output

    def test_has_top_pr_breakdown(self):
        lb = self._make_leaderboard()
        output = render_leaderboard(lb)
        assert "Top PR" in output

    def test_empty_leaderboard_renders(self):
        lb = Leaderboard(scores=[])
        output = render_leaderboard(lb)
        assert "Leaderboard" in output


class TestRenderPRReport:
    def test_contains_pr_number(self):
        dims = [DimensionScore(f"d{i}", 15) for i in range(5)]
        score = PRScore(42, "[awake] feat: x", "awake/session-3-x", 3, dims)
        output = render_pr_report(score)
        assert "42" in output

    def test_contains_grade(self):
        dims = [DimensionScore(f"d{i}", 18) for i in range(5)]
        score = PRScore(1, "title", "branch", 1, dims)
        output = render_pr_report(score)
        assert score.grade in output

    def test_contains_dimension_names(self):
        dims = [DimensionScore("Description Quality", 15)]
        score = PRScore(1, "t", "b", 1, dims)
        output = render_pr_report(score)
        assert "Description Quality" in output

    def test_is_markdown(self):
        dims = [DimensionScore(f"d{i}", 10) for i in range(5)]
        score = PRScore(1, "t", "b", 1, dims)
        output = render_pr_report(score)
        assert "|" in output
        assert "#" in output
