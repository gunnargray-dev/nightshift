"""Tests for src/scoring.py — the shared scoring abstraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring import (
    score_to_grade,
    grade_to_score,
    grade_colour,
    score_colour,
    score_to_tier,
    score_to_tier_emoji,
    score_to_status,
    score_to_overall_status,
    ScoreResult,
)


# ===========================================================================
# score_to_grade
# ===========================================================================

class TestScoreToGrade:
    @pytest.mark.parametrize("score,expected", [
        (100, "A+"), (95, "A+"), (94.9, "A"), (90, "A"),
        (89.9, "A-"), (85, "A-"), (84.9, "B+"), (80, "B+"),
        (79.9, "B"), (75, "B"), (74.9, "B-"), (70, "B-"),
        (69.9, "C+"), (65, "C+"), (64.9, "C"), (60, "C"),
        (59.9, "C-"), (55, "C-"), (54.9, "D+"), (50, "D+"),
        (49.9, "D"), (45, "D"), (44.9, "D-"), (40, "D-"),
        (39.9, "F"), (0, "F"),
    ])
    def test_grade_boundaries(self, score, expected):
        assert score_to_grade(score) == expected

    def test_none_returns_empty(self):
        assert score_to_grade(None) == ""

    def test_simple_mode_a(self):
        assert score_to_grade(92, simple=True) == "A"

    def test_simple_mode_b(self):
        assert score_to_grade(78, simple=True) == "B"

    def test_simple_mode_c(self):
        assert score_to_grade(62, simple=True) == "C"

    def test_simple_mode_d(self):
        assert score_to_grade(47, simple=True) == "D"

    def test_simple_mode_f(self):
        assert score_to_grade(20, simple=True) == "F"

    def test_simple_no_plus_minus(self):
        for score in range(0, 101, 5):
            grade = score_to_grade(score, simple=True)
            assert "+" not in grade
            assert "-" not in grade


# ===========================================================================
# grade_to_score
# ===========================================================================

class TestGradeToScore:
    @pytest.mark.parametrize("grade,expected", [
        ("A+", 97.5), ("A", 92.5), ("A-", 87.5),
        ("B+", 82.5), ("B", 77.5), ("B-", 72.5),
        ("C+", 67.5), ("C", 62.5), ("C-", 57.5),
        ("D+", 52.5), ("D", 47.5), ("D-", 42.5),
        ("F", 20.0),
    ])
    def test_known_grades(self, grade, expected):
        assert grade_to_score(grade) == expected

    def test_unknown_grade_returns_50(self):
        assert grade_to_score("Z") == 50.0

    def test_case_insensitive(self):
        assert grade_to_score("a") == grade_to_score("A")
        assert grade_to_score("b+") == grade_to_score("B+")


# ===========================================================================
# grade_colour
# ===========================================================================

class TestGradeColour:
    def test_returns_hex_string(self):
        colour = grade_colour("A")
        assert colour.startswith("#")

    def test_a_grade_is_green(self):
        assert "c853" in grade_colour("A+") or "00c8" in grade_colour("A+")

    def test_f_grade_is_red(self):
        assert "ff" in grade_colour("F").lower()

    def test_shields_mode_returns_name(self):
        assert grade_colour("A", shields=True) == "brightgreen"
        assert grade_colour("B", shields=True) == "green"
        assert grade_colour("C", shields=True) == "yellow"
        assert grade_colour("D", shields=True) == "orange"
        assert grade_colour("F", shields=True) == "red"

    def test_unknown_grade_returns_fallback(self):
        c = grade_colour("Z")
        assert isinstance(c, str)
        assert len(c) > 0


# ===========================================================================
# score_colour
# ===========================================================================

class TestScoreColour:
    def test_returns_hex_by_default(self):
        assert score_colour(90).startswith("#")

    def test_shields_mode_high(self):
        assert score_colour(85, shields=True) == "brightgreen"

    def test_shields_mode_mid(self):
        assert score_colour(68, shields=True) == "green"

    def test_shields_mode_low(self):
        assert score_colour(10, shields=True) == "red"

    @pytest.mark.parametrize("score", [0, 25, 40, 50, 60, 75, 90, 100])
    def test_always_returns_string(self, score):
        assert isinstance(score_colour(score), str)

    def test_hex_boundaries(self):
        # ≥90 → green, ≥75 → yellow-green, ≥60 → yellow, ≥40 → orange, else red
        assert score_colour(90) == score_colour(95)
        assert score_colour(39) == score_colour(10)  # both below 40 → red


# ===========================================================================
# score_to_tier
# ===========================================================================

class TestScoreToTier:
    @pytest.mark.parametrize("score,tier", [
        (90, "Elite"), (85, "Elite"),
        (75, "Mature"), (71, "Mature"),
        (55, "Growing"), (50, "Growing"),
        (35, "Nascent"), (30, "Nascent"),
        (25, "Critical"), (0, "Critical"),
    ])
    def test_tier_labels(self, score, tier):
        assert score_to_tier(score) == tier


# ===========================================================================
# score_to_tier_emoji
# ===========================================================================

class TestScoreToTierEmoji:
    def test_elite_gets_trophy(self):
        emoji = score_to_tier_emoji(90)
        assert emoji == "🏆"

    def test_critical_gets_red_circle(self):
        emoji = score_to_tier_emoji(10)
        assert emoji == "🔴"

    def test_returns_string(self):
        assert isinstance(score_to_tier_emoji(50), str)


# ===========================================================================
# score_to_status
# ===========================================================================

class TestScoreToStatus:
    def test_high_score_is_pass(self):
        assert score_to_status(90) == "pass"

    def test_mid_score_is_warn(self):
        assert score_to_status(60) == "warn"

    def test_low_score_is_fail(self):
        assert score_to_status(30) == "fail"

    def test_exact_warn_boundary(self):
        assert score_to_status(70) == "pass"
        assert score_to_status(69.9) == "warn"

    def test_exact_fail_boundary(self):
        assert score_to_status(50) == "warn"
        assert score_to_status(49.9) == "fail"

    def test_custom_thresholds(self):
        assert score_to_status(60, warn_threshold=80, fail_threshold=60) == "warn"
        assert score_to_status(59, warn_threshold=80, fail_threshold=60) == "fail"


# ===========================================================================
# score_to_overall_status
# ===========================================================================

class TestScoreToOverallStatus:
    def test_healthy(self):
        assert score_to_overall_status(80) == "healthy"

    def test_needs_attention(self):
        assert score_to_overall_status(60) == "needs-attention"

    def test_critical(self):
        assert score_to_overall_status(30) == "critical"

    def test_boundary_75(self):
        assert score_to_overall_status(75) == "healthy"
        assert score_to_overall_status(74.9) == "needs-attention"

    def test_boundary_50(self):
        assert score_to_overall_status(50) == "needs-attention"
        assert score_to_overall_status(49.9) == "critical"


# ===========================================================================
# ScoreResult
# ===========================================================================

class TestScoreResult:
    def test_from_score_returns_instance(self):
        r = ScoreResult.from_score(80.0)
        assert isinstance(r, ScoreResult)

    def test_from_score_grade_matches(self):
        r = ScoreResult.from_score(82.5)
        assert r.grade == "B+"

    def test_from_score_simple_grade_no_plusminus(self):
        r = ScoreResult.from_score(82.5)
        assert r.simple_grade == "B"

    def test_from_score_tier_populated(self):
        r = ScoreResult.from_score(88)
        assert r.tier == "Elite"

    def test_from_score_emoji_populated(self):
        r = ScoreResult.from_score(88)
        assert r.tier_emoji == "🏆"

    def test_from_score_colour_is_hex(self):
        r = ScoreResult.from_score(60)
        assert r.colour.startswith("#")

    def test_from_score_status_pass(self):
        r = ScoreResult.from_score(90)
        assert r.status == "pass"

    def test_from_score_status_warn(self):
        r = ScoreResult.from_score(60)
        assert r.status == "warn"

    def test_from_score_status_fail(self):
        r = ScoreResult.from_score(30)
        assert r.status == "fail"

    def test_from_grade_constructor(self):
        r = ScoreResult.from_grade("A")
        assert r.score == 92.5
        assert r.grade.startswith("A")

    def test_to_dict_has_all_fields(self):
        r = ScoreResult.from_score(70)
        d = r.to_dict()
        for k in ("score", "grade", "simple_grade", "tier", "tier_emoji", "colour", "status"):
            assert k in d

    def test_to_dict_is_json_serialisable(self):
        r = ScoreResult.from_score(55)
        json.dumps(r.to_dict())  # should not raise

    def test_str_representation(self):
        r = ScoreResult.from_score(80)
        s = str(r)
        assert "80" in s

    def test_score_is_rounded(self):
        r = ScoreResult.from_score(72.123456789)
        assert r.score == round(72.123456789, 2)
