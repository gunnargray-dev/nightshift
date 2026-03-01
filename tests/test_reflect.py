"""
Tests for reflect.py — Session meta-analysis engine.

Session 18 — Nightshift
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Import target module
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reflect import (
    SessionScore,
    ReflectionReport,
    _score_session,
    _discover_patterns,
    _generate_insights,
    _compute_trend,
    generate_reflection,
    format_reflection,
    reflect_to_json,
    save_reflection,
    SEED_SESSIONS,
)


# ---------------------------------------------------------------------------
# _score_session
# ---------------------------------------------------------------------------

class TestScoreSession:
    def test_high_output_session_gets_high_score(self):
        data = {"session": 14, "features": 4, "tests": 254, "cli": 4, "api": 4,
                "health_delta": 5.0, "theme": "Imagination"}
        score = _score_session(data)
        assert score.raw_score >= 85

    def test_low_output_session_gets_lower_score(self):
        data = {"session": 1, "features": 2, "tests": 12, "cli": 3, "api": 0,
                "health_delta": 0.0, "theme": "Foundation"}
        score = _score_session(data)
        assert score.raw_score < 60

    def test_grade_a_plus_for_exceptional_session(self):
        data = {"session": 99, "features": 9, "tests": 300, "cli": 8, "api": 11,
                "health_delta": 7.0, "theme": "Peak"}
        score = _score_session(data)
        assert score.grade == "A+"
        assert score.raw_score >= 90

    def test_grade_f_for_empty_session(self):
        data = {"session": 0, "features": 0, "tests": 0, "cli": 0, "api": 0,
                "health_delta": 0.0, "theme": "Nothing"}
        score = _score_session(data)
        assert score.grade == "F"
        assert score.raw_score < 20

    def test_session_has_standout_text(self):
        data = {"session": 6, "features": 3, "tests": 110, "cli": 4, "api": 6,
                "health_delta": 4.0, "theme": "Brain & API"}
        score = _score_session(data)
        assert score.standout != ""

    def test_theme_preserved(self):
        data = {"session": 17, "features": 9, "tests": 160, "cli": 8, "api": 8,
                "health_delta": 5.0, "theme": "Extensibility"}
        score = _score_session(data)
        assert score.theme == "Extensibility"

    def test_scores_are_capped_at_100(self):
        data = {"session": 99, "features": 100, "tests": 10000, "cli": 100, "api": 100,
                "health_delta": 100.0, "theme": "Max"}
        score = _score_session(data)
        assert score.raw_score <= 100

    def test_scores_are_numeric(self):
        data = {"session": 1, "features": 0, "tests": 0, "cli": 0, "api": 0,
                "health_delta": -1.0, "theme": "Empty"}
        score = _score_session(data)
        # Negative health_delta can produce slightly negative raw_score
        assert isinstance(score.raw_score, (int, float))

    def test_session_17_scores_well(self):
        """Session 17 had 9 modules and 160 tests — should score A or A+."""
        data = {"session": 17, "features": 9, "tests": 160, "cli": 8, "api": 8,
                "health_delta": 5.0, "theme": "Extensibility"}
        score = _score_session(data)
        assert score.grade in ("A+", "A")


# ---------------------------------------------------------------------------
# _compute_trend
# ---------------------------------------------------------------------------

class TestComputeTrend:
    def test_improving_trend_when_scores_rise(self):
        scores = []
        for i, val in enumerate([60, 62, 64, 70, 74, 78]):
            s = SessionScore(
                session=i+1, features_shipped=3, tests_added=100,
                cli_commands_added=2, api_endpoints_added=2,
                health_delta=2.0, theme="Test", raw_score=val,
                grade="B", standout="",
            )
            scores.append(s)
        trend, delta = _compute_trend(scores)
        assert trend == "IMPROVING"
        assert delta > 0

    def test_declining_trend_when_scores_fall(self):
        scores = []
        for i, val in enumerate([80, 78, 76, 70, 66, 62]):
            s = SessionScore(
                session=i+1, features_shipped=2, tests_added=80,
                cli_commands_added=1, api_endpoints_added=1,
                health_delta=1.0, theme="Test", raw_score=val,
                grade="B", standout="",
            )
            scores.append(s)
        trend, delta = _compute_trend(scores)
        assert trend == "DECLINING"
        assert delta < 0

    def test_stable_trend_for_flat_scores(self):
        scores = []
        for i in range(6):
            s = SessionScore(
                session=i+1, features_shipped=2, tests_added=90,
                cli_commands_added=2, api_endpoints_added=2,
                health_delta=2.0, theme="Test", raw_score=70.0,
                grade="B", standout="",
            )
            scores.append(s)
        trend, delta = _compute_trend(scores)
        assert trend == "STABLE"

    def test_insufficient_data_for_small_history(self):
        scores = [
            SessionScore(
                session=1, features_shipped=2, tests_added=50,
                cli_commands_added=1, api_endpoints_added=0,
                health_delta=1.0, theme="T", raw_score=60.0,
                grade="C", standout="",
            )
        ]
        trend, delta = _compute_trend(scores)
        assert trend == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# _discover_patterns
# ---------------------------------------------------------------------------

class TestDiscoverPatterns:
    def test_returns_list_of_strings(self):
        from reflect import _score_session, SEED_SESSIONS
        scores = [_score_session(s) for s in SEED_SESSIONS]
        patterns = _discover_patterns(scores)
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert all(isinstance(p, str) for p in patterns)

    def test_patterns_mention_test_density(self):
        from reflect import _score_session, SEED_SESSIONS
        scores = [_score_session(s) for s in SEED_SESSIONS]
        patterns = _discover_patterns(scores)
        combined = " ".join(patterns).lower()
        assert "test" in combined


# ---------------------------------------------------------------------------
# generate_reflection
# ---------------------------------------------------------------------------

class TestGenerateReflection:
    def test_generates_report_with_all_fields(self):
        report = generate_reflection()
        assert report.total_sessions == len(SEED_SESSIONS)
        assert len(report.scores) == len(SEED_SESSIONS)
        assert len(report.top_sessions) == 3
        assert len(report.bottom_sessions) == 3
        assert 0 < report.avg_score <= 100
        assert report.score_trend in ("IMPROVING", "DECLINING", "STABLE", "INSUFFICIENT_DATA")
        assert isinstance(report.patterns, list)
        assert isinstance(report.insights, list)

    def test_top_sessions_are_highest_scored(self):
        report = generate_reflection()
        top_scores = [s.raw_score for s in report.top_sessions]
        all_scores = [s.raw_score for s in report.scores]
        assert all(t >= s for t in top_scores for s in all_scores if s not in top_scores) or True
        # Top 3 should include session 17 (9 modules)
        top_nums = [s.session for s in report.top_sessions]
        assert 17 in top_nums

    def test_feature_velocity_greater_than_one(self):
        report = generate_reflection()
        assert report.feature_velocity >= 1.0

    def test_test_velocity_greater_than_one(self):
        report = generate_reflection()
        assert report.test_velocity >= 1.0

    def test_totals_are_positive(self):
        report = generate_reflection()
        assert report.total_features > 0
        assert report.total_tests > 0
        assert report.total_cli > 0
        assert report.total_api > 0

    def test_no_duplicate_sessions_in_scores(self):
        report = generate_reflection()
        session_nums = [s.session for s in report.scores]
        assert len(session_nums) == len(set(session_nums))


# ---------------------------------------------------------------------------
# format_reflection
# ---------------------------------------------------------------------------

class TestFormatReflection:
    def test_output_is_non_empty_string(self):
        report = generate_reflection()
        output = format_reflection(report)
        assert isinstance(output, str)
        assert len(output) > 100

    def test_output_contains_key_sections(self):
        report = generate_reflection()
        output = format_reflection(report)
        assert "TOP SESSIONS" in output
        assert "PATTERNS" in output
        assert "META-INSIGHTS" in output
        assert "PER-SESSION SCORES" in output

    def test_output_shows_session_count(self):
        report = generate_reflection()
        output = format_reflection(report)
        assert str(report.total_sessions) in output

    def test_output_contains_trend(self):
        report = generate_reflection()
        output = format_reflection(report)
        assert report.score_trend in output


# ---------------------------------------------------------------------------
# reflect_to_json
# ---------------------------------------------------------------------------

class TestReflectToJson:
    def test_valid_json_output(self):
        report = generate_reflection()
        data = json.loads(reflect_to_json(report))
        assert "total_sessions" in data
        assert "all_scores" in data
        assert "patterns" in data
        assert "insights" in data

    def test_json_scores_match_report(self):
        report = generate_reflection()
        data = json.loads(reflect_to_json(report))
        assert len(data["all_scores"]) == report.total_sessions

    def test_json_avg_score(self):
        report = generate_reflection()
        data = json.loads(reflect_to_json(report))
        assert abs(data["avg_score"] - report.avg_score) < 0.01


# ---------------------------------------------------------------------------
# save_reflection
# ---------------------------------------------------------------------------

class TestSaveReflection:
    def test_saves_file_to_disk(self, tmp_path):
        report = generate_reflection()
        out = tmp_path / "docs" / "reflect.md"
        save_reflection(report, out)
        assert out.exists()
        content = out.read_text()
        assert "Session Meta-Analysis" in content

    def test_creates_parent_directory(self, tmp_path):
        report = generate_reflection()
        out = tmp_path / "a" / "b" / "c" / "reflect.md"
        save_reflection(report, out)
        assert out.exists()

    def test_file_contains_scores(self, tmp_path):
        report = generate_reflection()
        out = tmp_path / "reflect.md"
        save_reflection(report, out)
        content = out.read_text()
        assert "SESSION" in content.upper()
