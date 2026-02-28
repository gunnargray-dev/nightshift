"""Tests for src/diff_sessions.py — Session comparison."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.diff_sessions import (
    SessionSnapshot,
    MetricDelta,
    SessionDiffReport,
    compare_sessions,
    _parse_sessions_from_log,
    _build_delta,
    _enrich_snapshot,
)


# ---------------------------------------------------------------------------
# _build_delta
# ---------------------------------------------------------------------------


def test_build_delta_positive():
    d = _build_delta("Tests", 100, 150)
    assert d.delta == 50
    assert d.direction == "up"
    assert d.pct_change == 50.0


def test_build_delta_negative():
    d = _build_delta("Dead code", 20, 10, higher_is_better=False)
    assert d.delta == -10
    assert d.direction == "up"  # lower is better, so decrease = up


def test_build_delta_neutral():
    d = _build_delta("PRs", 5, 5)
    assert d.delta == 0
    assert d.direction == "neutral"


def test_build_delta_non_numeric():
    d = _build_delta("Version", "v1.0", "v2.0")
    assert d.delta is None
    assert d.direction == "neutral"


def test_build_delta_format_string():
    d = _build_delta("Tests", 100, 200)
    formatted = d.format()
    assert "100" in formatted
    assert "200" in formatted
    assert "▲" in formatted or "+100" in formatted


# ---------------------------------------------------------------------------
# MetricDelta
# ---------------------------------------------------------------------------


def test_metric_delta_to_dict():
    d = MetricDelta(name="Tests", session_a=100, session_b=200, delta=100,
                    pct_change=100.0, direction="up")
    dd = d.to_dict()
    assert dd["name"] == "Tests"
    assert dd["delta"] == 100


# ---------------------------------------------------------------------------
# SessionSnapshot
# ---------------------------------------------------------------------------


def test_session_snapshot_to_dict():
    snap = SessionSnapshot(session=5, date="January 2025", prs=3, tests=100)
    d = snap.to_dict()
    assert d["session"] == 5
    assert d["prs"] == 3


def test_enrich_snapshot_fills_zeros():
    snap = SessionSnapshot(session=1)  # known seed session
    enriched = _enrich_snapshot(snap, 1)
    assert enriched.prs > 0
    assert enriched.tests > 0


def test_enrich_snapshot_preserves_nonzero():
    snap = SessionSnapshot(session=1, prs=999)
    enriched = _enrich_snapshot(snap, 1)
    assert enriched.prs == 999  # should not overwrite


def test_enrich_snapshot_interpolates_middle():
    snap = SessionSnapshot(session=8)  # between seed sessions
    enriched = _enrich_snapshot(snap, 8)
    assert enriched.prs > 0


# ---------------------------------------------------------------------------
# _parse_sessions_from_log
# ---------------------------------------------------------------------------


def test_parse_sessions_empty_log(tmp_path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    log.write_text("# Nightshift Log\n\n")
    result = _parse_sessions_from_log(log)
    assert result == {}


def test_parse_sessions_missing_log(tmp_path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    result = _parse_sessions_from_log(log)
    assert result == {}


def test_parse_sessions_basic(tmp_path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    log.write_text("""
## Session 1 — January 10, 2025

**Operator:** Computer (autonomous)

**Tasks completed:**

- ✅ **Init repo** → PR #1 — Set up the project

---

## Session 2 — January 15, 2025

**Tasks completed:**

- ✅ **Add health check** → PR #2 — Health module
- ✅ **Write tests** → PR #3 — Test suite

---
""")
    result = _parse_sessions_from_log(log)
    assert 1 in result
    assert 2 in result
    assert result[1].date == "January 10, 2025"
    assert result[2].tasks_completed == 2


def test_parse_sessions_extracts_decisions(tmp_path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    log.write_text("""
## Session 5 — March 1, 2025

**Decisions & rationale:**

- Used AST analysis instead of regex for accuracy
- Kept zero-dependency philosophy

---
""")
    result = _parse_sessions_from_log(log)
    assert 5 in result
    decisions = result[5].decisions
    assert len(decisions) >= 1
    assert any("AST" in d for d in decisions)


# ---------------------------------------------------------------------------
# compare_sessions
# ---------------------------------------------------------------------------


def test_compare_sessions_returns_report(tmp_path):
    # No log file — should still return a report using seed data
    report = compare_sessions(tmp_path, 1, 16)
    assert isinstance(report, SessionDiffReport)
    assert report.session_a == 1
    assert report.session_b == 16


def test_compare_sessions_deltas_populated(tmp_path):
    report = compare_sessions(tmp_path, 1, 16)
    assert len(report.deltas) > 0


def test_compare_sessions_to_markdown(tmp_path):
    report = compare_sessions(tmp_path, 1, 16)
    md = report.to_markdown()
    assert "Session 1" in md
    assert "Session 16" in md


def test_compare_sessions_to_rich_table(tmp_path):
    report = compare_sessions(tmp_path, 1, 16)
    table = report.to_rich_table()
    assert "1 → 16" in table


def test_compare_sessions_prs_increase(tmp_path):
    report = compare_sessions(tmp_path, 1, 16)
    pr_delta = next((d for d in report.deltas if d.name == "PRs opened"), None)
    assert pr_delta is not None
    assert pr_delta.delta is not None and float(pr_delta.delta) > 0


def test_compare_sessions_to_dict(tmp_path):
    report = compare_sessions(tmp_path, 1, 16)
    d = report.to_dict()
    assert d["session_a"] == 1
    assert d["session_b"] == 16
    assert "deltas" in d


def test_compare_same_session(tmp_path):
    """Comparing a session to itself should produce zero deltas."""
    report = compare_sessions(tmp_path, 5, 5)
    for d in report.deltas:
        if isinstance(d.delta, (int, float)):
            assert d.delta == 0, f"Expected 0 delta for {d.name}"


def test_compare_sessions_with_log(tmp_path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    log.write_text("""
## Session 1 — January 2025

**Tasks completed:**

- ✅ **Init** → PR #1 — Initial setup

---

## Session 3 — February 2025

**Tasks completed:**

- ✅ **Health module** → PR #5 — Add health checking
- ✅ **Tests** → PR #6 — Test suite

---
""")
    report = compare_sessions(tmp_path, 1, 3)
    assert report.session_a == 1
    assert report.session_b == 3
    assert len(report.deltas) > 0
