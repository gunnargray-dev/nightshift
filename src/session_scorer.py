"""
session_scorer.py — Session quality scoring system.

Rates each Awake session across 5 dimensions:
  1. Features shipped (new source modules)
  2. Test coverage delta (tests added, density)
  3. Code health delta (health score improvement)
  4. CLI commands added
  5. API endpoints added

Produces a 0-100 score and A+/A/B+/B/C/D/F grade for any session.

CLI: awake session-score [--session N] [--json] [--all]
API: GET /api/session-score
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from src.scoring import score_to_grade as _grade


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    """Represent a single scored dimension with raw value, weight, and evidence"""

    name: str
    raw: float
    weight: float
    weighted: float
    evidence: str


@dataclass
class SessionQualityScore:
    """Hold the aggregate quality score and grade for a single session"""

    session: int
    dimensions: list
    total: float
    grade: str
    verdict: str
    strengths: list
    weaknesses: list
    recommendation: str


# ---------------------------------------------------------------------------
# Scoring rubrics
# ---------------------------------------------------------------------------

FEATURE_RUBRIC = [
    (0, 0.0), (1, 0.3), (2, 0.55), (3, 0.70),
    (4, 0.85), (6, 0.95), (9, 1.00),
]

TEST_RUBRIC = [
    (0, 0.0), (30, 0.2), (60, 0.4), (100, 0.6),
    (140, 0.75), (180, 0.88), (250, 1.0),
]

CLI_RUBRIC = [
    (0, 0.0), (1, 0.3), (2, 0.55), (4, 0.75), (6, 0.88), (8, 1.0),
]

API_RUBRIC = [
    (0, 0.0), (1, 0.25), (3, 0.5), (6, 0.75), (8, 0.88), (11, 1.0),
]

HEALTH_RUBRIC = [
    (0.0, 0.0), (1.0, 0.25), (2.0, 0.50),
    (3.5, 0.70), (5.0, 0.88), (7.0, 1.00),
]


def _interpolate(value, rubric):
    """Linear interpolation over a rubric table."""
    if value <= rubric[0][0]:
        return rubric[0][1]
    if value >= rubric[-1][0]:
        return rubric[-1][1]
    for i in range(len(rubric) - 1):
        x0, y0 = rubric[i]
        x1, y1 = rubric[i + 1]
        if x0 <= value <= x1:
            if x1 == x0:
                return y0
            t = (value - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return rubric[-1][1]


# ---------------------------------------------------------------------------
# Grade table
# ---------------------------------------------------------------------------

# _grade imported from src.scoring above


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------

WEIGHTS = {
    "Features Shipped":    0.30,
    "Tests Added":         0.28,
    "CLI Commands Added":  0.14,
    "API Endpoints Added": 0.14,
    "Code Health Delta":   0.14,
}


def score_session(
    session,
    features_shipped,
    tests_added,
    cli_commands_added,
    api_endpoints_added,
    health_delta,
    architectural_note="",
):
    """
    Score a session on five quality dimensions.

    Returns:
        SessionQualityScore with per-dimension breakdown and total grade.
    """
    dims = []

    feat_raw = _interpolate(features_shipped, FEATURE_RUBRIC)
    feat_w   = WEIGHTS["Features Shipped"]
    dims.append(DimensionScore(
        name="Features Shipped",
        raw=round(feat_raw, 3),
        weight=feat_w,
        weighted=round(feat_raw * feat_w * 100, 1),
        evidence=f"{features_shipped} new source module(s)",
    ))

    test_raw = _interpolate(tests_added, TEST_RUBRIC)
    test_w   = WEIGHTS["Tests Added"]
    dims.append(DimensionScore(
        name="Tests Added",
        raw=round(test_raw, 3),
        weight=test_w,
        weighted=round(test_raw * test_w * 100, 1),
        evidence=f"{tests_added} new tests",
    ))

    cli_raw = _interpolate(cli_commands_added, CLI_RUBRIC)
    cli_w   = WEIGHTS["CLI Commands Added"]
    dims.append(DimensionScore(
        name="CLI Commands Added",
        raw=round(cli_raw, 3),
        weight=cli_w,
        weighted=round(cli_raw * cli_w * 100, 1),
        evidence=f"{cli_commands_added} new subcommand(s)",
    ))

    api_raw = _interpolate(api_endpoints_added, API_RUBRIC)
    api_w   = WEIGHTS["API Endpoints Added"]
    dims.append(DimensionScore(
        name="API Endpoints Added",
        raw=round(api_raw, 3),
        weight=api_w,
        weighted=round(api_raw * api_w * 100, 1),
        evidence=f"{api_endpoints_added} new endpoint(s)",
    ))

    health_raw = _interpolate(health_delta, HEALTH_RUBRIC)
    health_w   = WEIGHTS["Code Health Delta"]
    dims.append(DimensionScore(
        name="Code Health Delta",
        raw=round(health_raw, 3),
        weight=health_w,
        weighted=round(health_raw * health_w * 100, 1),
        evidence=f"{health_delta:+.1f} pts health improvement",
    ))

    total = round(sum(d.weighted for d in dims), 1)
    grade = _grade(total)

    sorted_dims = sorted(dims, key=lambda d: d.raw, reverse=True)
    strengths  = [f"{d.name}: {d.evidence}" for d in sorted_dims[:2] if d.raw >= 0.7]
    weaknesses = [f"{d.name}: below target ({d.evidence})" for d in sorted_dims[-2:] if d.raw < 0.5]

    if total >= 90:
        verdict = "Exceptional session — exceeded expectations on all dimensions"
    elif total >= 80:
        verdict = "Strong session — solid delivery across all dimensions"
    elif total >= 65:
        verdict = "Good session — meaningful progress, some areas below target"
    elif total >= 50:
        verdict = "Adequate session — partial delivery; some dimensions need attention"
    else:
        verdict = "Below expectations — reassess prioritization for next session"

    lowest = min(dims, key=lambda d: d.raw)
    recommendation = f"To improve score, focus on: {lowest.name.lower()} (currently {lowest.evidence})"

    if architectural_note:
        verdict += f". Note: {architectural_note}"

    return SessionQualityScore(
        session=session,
        dimensions=dims,
        total=total,
        grade=grade,
        verdict=verdict,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendation=recommendation,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_session_score(score):
    """Render a SessionQualityScore as a terminal string."""
    lines = []
    lines.append(f"SESSION {score.session} QUALITY SCORE")
    lines.append("=" * 50)
    lines.append(f"  Total:   {score.total:.1f} / 100   ({score.grade})")
    lines.append(f"  Verdict: {score.verdict}")
    lines.append("")
    lines.append("  Dimension Breakdown:")
    lines.append(f"  {'Dimension':<25} {'Weight':>7}  {'Score':>6}  {'Pts':>6}")
    lines.append(f"  {'-'*25} {'-------':>7}  {'------':>6}  {'------':>6}")
    for d in score.dimensions:
        bar = "█" * int(d.raw * 12) + "░" * (12 - int(d.raw * 12))
        lines.append(
            f"  {d.name:<25} {d.weight*100:>6.0f}%  {d.raw*100:>5.1f}%  {d.weighted:>6.1f}"
        )
        lines.append(f"    {bar}  {d.evidence}")
    lines.append("")

    if score.strengths:
        lines.append("  Strengths:")
        for s in score.strengths:
            lines.append(f"    + {s}")
        lines.append("")

    if score.weaknesses:
        lines.append("  Areas to improve:")
        for w in score.weaknesses:
            lines.append(f"    - {w}")
        lines.append("")

    lines.append(f"  Recommendation: {score.recommendation}")
    return "\n".join(lines)


def session_score_to_json(score):
    """Serialize to JSON."""
    data = {
        "session": score.session,
        "total": score.total,
        "grade": score.grade,
        "verdict": score.verdict,
        "strengths": score.strengths,
        "weaknesses": score.weaknesses,
        "recommendation": score.recommendation,
        "dimensions": [
            {"name": d.name, "raw": d.raw, "weight": d.weight,
             "weighted": d.weighted, "evidence": d.evidence}
            for d in score.dimensions
        ],
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------

SESSION_DATA = [
    # (session, features, tests, cli, api, health_delta)
    (1,  2,   12,  3,  0,  0.0),
    (2,  2,   33,  3,  0,  2.0),
    (3,  3,   75,  4,  0,  3.0),
    (4,  3,   90,  4,  0,  3.0),
    (5,  3,  100,  4,  0,  3.0),
    (6,  3,  110,  4,  6,  4.0),
    (7,  3,  110,  2,  3,  2.0),
    (8,  3,  110,  2,  3,  2.0),
    (9,  2,   80,  2,  1,  2.0),
    (10, 2,   80,  1,  0,  2.0),
    (11, 2,  100,  1,  0,  3.0),
    (12, 2,   80,  0,  0,  2.0),
    (13, 2,  120,  1,  0,  3.0),
    (14, 4,  254,  1,  0,  5.0),
    (15, 3,  155,  3, 11,  4.0),
    (16, 4,  140,  4,  3,  4.0),
    (17, 9,  160,  8,  8,  5.0),
    (18, 4,  140,  4,  4,  4.0),
]


def score_all_sessions():
    """Score all historical sessions and return list."""
    return [
        score_session(s, f, t, c, a, h)
        for s, f, t, c, a, h in SESSION_DATA
    ]


if __name__ == "__main__":
    scores = score_all_sessions()
    for s in scores:
        print(format_session_score(s))
        print()
