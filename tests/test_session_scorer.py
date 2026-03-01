"""
Tests for session_scorer.py — Session quality scoring.

Session 18 — Awake
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from session_scorer import (
    DimensionScore,
    SessionQualityScore,
    score_session,
    format_session_score,
    session_score_to_json,
    score_all_sessions,
    SESSION_DATA,
    _interpolate,
    _grade,
    FEATURE_RUBRIC,
    TEST_RUBRIC,
)


# ---------------------------------------------------------------------------
# _interpolate
# ---------------------------------------------------------------------------

class TestInterpolate:
    def test_below_minimum_returns_first(self):
        rubric = [(0, 0.0), (10, 1.0)]
        assert _interpolate(-5, rubric) == 0.0

    def test_above_maximum_returns_last(self):
        rubric = [(0, 0.0), (10, 1.0)]
        assert _interpolate(100, rubric) == 1.0

    def test_midpoint_interpolated(self):
        rubric = [(0, 0.0), (10, 1.0)]
        result = _interpolate(5, rubric)
        assert abs(result - 0.5) < 0.01

    def test_exact_boundary(self):
        rubric = [(0, 0.0), (5, 0.5), (10, 1.0)]
        assert abs(_interpolate(5, rubric) - 0.5) < 0.01

    def test_monotonic_result(self):
        values = [0, 2, 4, 6, 8, 10]
        results = [_interpolate(v, FEATURE_RUBRIC) for v in values]
        for i in range(len(results) - 1):
            assert results[i] <= results[i + 1]


# ---------------------------------------------------------------------------
# _grade
# ---------------------------------------------------------------------------

class TestGrade:
    def test_a_plus_at_95(self):
        assert _grade(95) == "A+"
        assert _grade(97) == "A+"
        assert _grade(100) == "A+"

    def test_a_at_90_to_94(self):
        assert _grade(90) == "A"
        assert _grade(92) == "A"
        assert _grade(94.9) == "A"

    def test_a_minus_at_85_to_89(self):
        assert _grade(85) == "A-"
        assert _grade(89.9) == "A-"

    def test_b_plus_at_80_to_84(self):
        assert _grade(80) == "B+"
        assert _grade(83) == "B+"

    def test_b_at_75_to_79(self):
        assert _grade(75) == "B"
        assert _grade(79) == "B"

    def test_b_minus_at_70_to_74(self):
        assert _grade(70) == "B-"
        assert _grade(74) == "B-"

    def test_c_plus_at_65_to_69(self):
        assert _grade(65) == "C+"
        assert _grade(69) == "C+"

    def test_c_at_60_to_64(self):
        assert _grade(60) == "C"
        assert _grade(64) == "C"

    def test_c_minus_at_55_to_59(self):
        assert _grade(55) == "C-"
        assert _grade(59) == "C-"

    def test_d_plus_at_50_to_54(self):
        assert _grade(50) == "D+"
        assert _grade(54) == "D+"

    def test_d_at_45_to_49(self):
        assert _grade(45) == "D"
        assert _grade(49) == "D"

    def test_d_minus_at_40_to_44(self):
        assert _grade(40) == "D-"
        assert _grade(44) == "D-"

    def test_f_below_40(self):
        assert _grade(39) == "F"
        assert _grade(0) == "F"


# ---------------------------------------------------------------------------
# score_session
# ---------------------------------------------------------------------------

class TestScoreSession:
    def test_basic_score_returns_dataclass(self):
        result = score_session(18, 4, 140, 4, 4, 4.0)
        assert isinstance(result, SessionQualityScore)

    def test_session_number_preserved(self):
        result = score_session(42, 3, 100, 2, 2, 2.0)
        assert result.session == 42

    def test_five_dimensions_always_present(self):
        result = score_session(1, 1, 20, 1, 0, 1.0)
        assert len(result.dimensions) == 5

    def test_dimension_names_correct(self):
        result = score_session(1, 1, 20, 1, 0, 1.0)
        names = {d.name for d in result.dimensions}
        assert "Features Shipped" in names
        assert "Tests Added" in names
        assert "CLI Commands Added" in names
        assert "API Endpoints Added" in names
        assert "Code Health Delta" in names

    def test_weights_sum_to_100(self):
        result = score_session(1, 1, 20, 1, 0, 1.0)
        weight_sum = sum(d.weight for d in result.dimensions)
        assert abs(weight_sum - 1.0) < 0.001

    def test_weighted_sum_equals_total(self):
        result = score_session(1, 1, 20, 1, 0, 1.0)
        weighted_sum = sum(d.weighted for d in result.dimensions)
        assert abs(weighted_sum - result.total) < 0.5  # allow for rounding

    def test_total_in_valid_range(self):
        for features in range(0, 10):
            r = score_session(1, features, features * 30, features, features, float(features))
            assert 0 <= r.total <= 100

    def test_high_delivery_session_scores_well(self):
        result = score_session(17, 9, 160, 8, 8, 5.0)
        assert result.total >= 80
        assert result.grade in ("A+", "A", "B+")

    def test_minimal_session_scores_low(self):
        result = score_session(1, 0, 0, 0, 0, 0.0)
        assert result.total < 20
        assert result.grade == "F"

    def test_architectural_note_included_in_verdict(self):
        result = score_session(6, 3, 100, 4, 6, 4.0,
                               architectural_note="Introduced brain.py decision engine")
        assert "brain.py" in result.verdict or len(result.verdict) > 10

    def test_strengths_are_strings(self):
        result = score_session(17, 9, 160, 8, 8, 5.0)
        assert all(isinstance(s, str) for s in result.strengths)

    def test_weaknesses_are_strings(self):
        result = score_session(1, 0, 5, 0, 0, 0.0)
        assert all(isinstance(w, str) for w in result.weaknesses)

    def test_recommendation_is_non_empty(self):
        result = score_session(5, 2, 80, 2, 0, 2.0)
        assert isinstance(result.recommendation, str)
        assert len(result.recommendation) > 0


# ---------------------------------------------------------------------------
# format_session_score
# ---------------------------------------------------------------------------

class TestFormatSessionScore:
    def test_output_is_string(self):
        score = score_session(18, 4, 140, 4, 4, 4.0)
        out = format_session_score(score)
        assert isinstance(out, str)

    def test_output_contains_session_number(self):
        score = score_session(18, 4, 140, 4, 4, 4.0)
        out = format_session_score(score)
        assert "18" in out

    def test_output_contains_grade(self):
        score = score_session(18, 4, 140, 4, 4, 4.0)
        out = format_session_score(score)
        assert score.grade in out

    def test_output_contains_all_dimension_names(self):
        score = score_session(18, 4, 140, 4, 4, 4.0)
        out = format_session_score(score)
        assert "Features" in out
        assert "Tests" in out
        assert "CLI" in out
        assert "API" in out
        assert "Health" in out

    def test_output_contains_recommendation(self):
        score = score_session(5, 2, 50, 1, 0, 1.0)
        out = format_session_score(score)
        assert "Recommendation" in out or "recommendation" in out.lower()


# ---------------------------------------------------------------------------
# session_score_to_json
# ---------------------------------------------------------------------------

class TestSessionScoreToJson:
    def test_valid_json(self):
        score = score_session(18, 4, 140, 4, 4, 4.0)
        data = json.loads(session_score_to_json(score))
        assert isinstance(data, dict)

    def test_json_has_total(self):
        score = score_session(18, 4, 140, 4, 4, 4.0)
        data = json.loads(session_score_to_json(score))
        assert "total" in data
        assert 0 <= data["total"] <= 100

    def test_json_has_dimensions(self):
        score = score_session(18, 4, 140, 4, 4, 4.0)
        data = json.loads(session_score_to_json(score))
        assert "dimensions" in data
        assert len(data["dimensions"]) == 5

    def test_json_has_grade(self):
        score = score_session(17, 9, 160, 8, 8, 5.0)
        data = json.loads(session_score_to_json(score))
        assert "grade" in data
        assert data["grade"] in ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F")


# ---------------------------------------------------------------------------
# score_all_sessions
# ---------------------------------------------------------------------------

class TestScoreAllSessions:
    def test_returns_correct_count(self):
        scores = score_all_sessions()
        assert len(scores) == len(SESSION_DATA)

    def test_all_are_session_quality_scores(self):
        scores = score_all_sessions()
        assert all(isinstance(s, SessionQualityScore) for s in scores)

    def test_session_numbers_match_data(self):
        scores = score_all_sessions()
        data_sessions = [row[0] for row in SESSION_DATA]
        score_sessions = [s.session for s in scores]
        assert data_sessions == score_sessions

    def test_all_totals_in_range(self):
        scores = score_all_sessions()
        for s in scores:
            assert 0 <= s.total <= 100, f"Session {s.session} has invalid total: {s.total}"

    def test_session_14_is_high_scorer(self):
        """Session 14 had 4 modules and 254 tests — should rank high."""
        scores = score_all_sessions()
        s14 = next(s for s in scores if s.session == 14)
        assert s14.total >= 65

    def test_session_17_is_top_scorer(self):
        """Session 17 had 9 modules — should be highest or near-highest."""
        scores = score_all_sessions()
        s17 = next(s for s in scores if s.session == 17)
        all_totals = sorted([s.total for s in scores], reverse=True)
        # Should be in top 3
        assert s17.total >= all_totals[2]
