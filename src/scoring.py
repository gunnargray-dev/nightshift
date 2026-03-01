"""Shared scoring abstraction for Awake.

Provides a unified Grade/Score system used across analysis modules so that
letter grades, tier labels, colour coding, and serialisation are handled in
one place rather than being duplicated in every module.

Usage
-----
    from src.scoring import score_to_grade, grade_colour, score_colour, ScoreResult

    grade = score_to_grade(82.5)          # "B+"
    colour = grade_colour("B+")           # "green"
    result = ScoreResult.from_score(82.5) # ScoreResult(score=82.5, grade="B+", …)
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Letter grade boundaries
# ---------------------------------------------------------------------------

#: Mapping of (min_score, grade) pairs, ordered highest-first.
_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (95.0, "A+"),
    (90.0, "A"),
    (85.0, "A-"),
    (80.0, "B+"),
    (75.0, "B"),
    (70.0, "B-"),
    (65.0, "C+"),
    (60.0, "C"),
    (55.0, "C-"),
    (50.0, "D+"),
    (45.0, "D"),
    (40.0, "D-"),
]

#: Simple 5-letter grade thresholds (A/B/C/D/F — no +/- variants).
_SIMPLE_GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (90.0, "A"),
    (75.0, "B"),
    (60.0, "C"),
    (45.0, "D"),
]


def score_to_grade(score: Optional[float], simple: bool = False) -> str:
    """Convert a 0–100 numeric score to a letter grade.

    Parameters
    ----------
    score:
        Numeric score in the range 0–100.  ``None`` returns ``""``.
    simple:
        If *True* return only A/B/C/D/F (no +/- suffixes).

    Returns
    -------
    str
        Letter grade string, e.g. ``"B+"`` or ``"F"``.
    """
    if score is None:
        return ""
    thresholds = _SIMPLE_GRADE_THRESHOLDS if simple else _GRADE_THRESHOLDS
    for threshold, letter in thresholds:
        if score >= threshold:
            return letter
    return "F"


def grade_to_score(grade: str) -> float:
    """Convert a letter grade back to a representative numeric score.

    Parameters
    ----------
    grade:
        Letter grade string such as ``"A"``, ``"B+"``, ``"C-"``.

    Returns
    -------
    float
        Midpoint score for the grade band, e.g. ``82.5`` for ``"B+"``.
    """
    mapping: dict[str, float] = {
        "A+": 97.5, "A": 92.5, "A-": 87.5,
        "B+": 82.5, "B": 77.5, "B-": 72.5,
        "C+": 67.5, "C": 62.5, "C-": 57.5,
        "D+": 52.5, "D": 47.5, "D-": 42.5,
        "F": 20.0,
    }
    return mapping.get(grade.strip().upper(), 50.0)


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

#: Hex colours for each letter grade (dark-mode friendly).
_GRADE_COLOURS: dict[str, str] = {
    "A+": "#00c853", "A": "#00c853", "A-": "#00e676",
    "B+": "#76ff03", "B": "#76ff03", "B-": "#c6ff00",
    "C+": "#ffea00", "C": "#ffea00", "C-": "#ffd600",
    "D+": "#ff9100", "D": "#ff9100", "D-": "#ff6d00",
    "F":  "#ff1744",
}

#: shields.io colour names for each letter grade (used in badge URLs).
_GRADE_SHIELD_COLOURS: dict[str, str] = {
    "A": "brightgreen",
    "B": "green",
    "C": "yellow",
    "D": "orange",
    "F": "red",
}


def grade_colour(grade: str, shields: bool = False) -> str:
    """Return a colour string for *grade*.

    Parameters
    ----------
    grade:
        Letter grade string (e.g. ``"B+"``).
    shields:
        If *True*, return a shields.io colour name; otherwise return a hex
        colour suitable for CSS.

    Returns
    -------
    str
        Colour string.
    """
    if shields:
        first = grade.strip().upper()[:1]
        return _GRADE_SHIELD_COLOURS.get(first, "lightgrey")
    return _GRADE_COLOURS.get(grade.strip().upper(), "#78909c")


def score_colour(score: float, shields: bool = False) -> str:
    """Return a colour string representing a numeric 0–100 *score*.

    Parameters
    ----------
    score:
        Numeric score in 0–100.
    shields:
        If *True*, return a shields.io colour name; otherwise return a hex
        colour suitable for CSS.

    Returns
    -------
    str
        Colour string.
    """
    if shields:
        if score >= 80:
            return "brightgreen"
        if score >= 65:
            return "green"
        if score >= 50:
            return "yellow"
        if score >= 35:
            return "orange"
        return "red"
    # Hex colours
    if score >= 90:
        return "#00c853"
    if score >= 75:
        return "#76ff03"
    if score >= 60:
        return "#ffea00"
    if score >= 40:
        return "#ff9100"
    return "#ff1744"


# ---------------------------------------------------------------------------
# Tier labels
# ---------------------------------------------------------------------------

#: Human-readable tier labels and their emoji.
_TIER_LABELS: list[tuple[float, str, str]] = [
    (85.0, "Elite",    "\U0001f3c6"),
    (70.0, "Mature",   "\u2705"),
    (50.0, "Growing",  "\U0001f331"),
    (30.0, "Nascent",  "\u26a0\ufe0f"),
    (0.0,  "Critical", "\U0001f534"),
]


def score_to_tier(score: float) -> str:
    """Return a human-readable tier label for *score*.

    Returns one of ``"Elite"``, ``"Mature"``, ``"Growing"``,
    ``"Nascent"``, or ``"Critical"``.
    """
    for threshold, label, _ in _TIER_LABELS:
        if score >= threshold:
            return label
    return "Critical"


def score_to_tier_emoji(score: float) -> str:
    """Return the emoji associated with the tier for *score*."""
    for threshold, _, emoji in _TIER_LABELS:
        if score >= threshold:
            return emoji
    return "\U0001f534"


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------


def score_to_status(
    score: float,
    warn_threshold: float = 70.0,
    fail_threshold: float = 50.0,
) -> str:
    """Convert a numeric score to a pass/warn/fail status string.

    Parameters
    ----------
    score:
        Numeric score 0–100.
    warn_threshold:
        Scores below this value are ``"warn"`` (unless also below
        *fail_threshold*).
    fail_threshold:
        Scores below this value are ``"fail"``.

    Returns
    -------
    str
        One of ``"pass"``, ``"warn"``, ``"fail"``.
    """
    if score >= warn_threshold:
        return "pass"
    if score >= fail_threshold:
        return "warn"
    return "fail"


def score_to_overall_status(score: float) -> str:
    """Return ``"healthy"``, ``"needs-attention"``, or ``"critical"`` for *score*."""
    if score >= 75:
        return "healthy"
    if score >= 50:
        return "needs-attention"
    return "critical"


# ---------------------------------------------------------------------------
# ScoreResult dataclass — portable score bundle
# ---------------------------------------------------------------------------


@dataclass
class ScoreResult:
    """A self-contained score bundle: numeric value, letter grade, and metadata.

    Attributes
    ----------
    score:
        Numeric score in 0–100.
    grade:
        Letter grade string (e.g. ``"B+"``).
    simple_grade:
        Single-letter grade without +/- (e.g. ``"B"``).
    tier:
        Human-readable tier label (``"Elite"`` … ``"Critical"``).
    tier_emoji:
        Emoji for the tier.
    colour:
        CSS hex colour for dark-mode UIs.
    status:
        ``"pass"``, ``"warn"``, or ``"fail"``.
    """

    score: float
    grade: str
    simple_grade: str
    tier: str
    tier_emoji: str
    colour: str
    status: str

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_score(
        cls,
        score: float,
        warn_threshold: float = 70.0,
        fail_threshold: float = 50.0,
    ) -> "ScoreResult":
        """Build a :class:`ScoreResult` from a raw 0–100 *score*.

        Parameters
        ----------
        score:
            Numeric score in 0–100.
        warn_threshold:
            Passed to :func:`score_to_status`.
        fail_threshold:
            Passed to :func:`score_to_status`.
        """
        grade = score_to_grade(score)
        simple = score_to_grade(score, simple=True)
        return cls(
            score=round(score, 2),
            grade=grade,
            simple_grade=simple,
            tier=score_to_tier(score),
            tier_emoji=score_to_tier_emoji(score),
            colour=score_colour(score),
            status=score_to_status(score, warn_threshold, fail_threshold),
        )

    @classmethod
    def from_grade(cls, grade: str) -> "ScoreResult":
        """Build a :class:`ScoreResult` from a letter *grade* string.

        The numeric score is set to the midpoint of the grade band.
        """
        return cls.from_score(grade_to_score(grade))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a plain-dict representation for JSON serialisation."""
        return asdict(self)

    def __str__(self) -> str:
        return f"{self.grade} ({self.score:.1f}/100)"
