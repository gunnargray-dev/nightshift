"""Tests for src/trend_data.py — Historical trend data."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.trend_data import (
    SessionMetrics,
    TrendData,
    generate_trend_data,
    _parse_log,
    _interpolate_cumulative,
    _SEED_DATA,
)


# ---------------------------------------------------------------------------
# SessionMetrics
# ---------------------------------------------------------------------------


def test_session_metrics_to_dict():
    sm = SessionMetrics(session=5, date="Jan 2025", prs=10, tests=100)
    d = sm.to_dict()
    assert d["session"] == 5
    assert d["prs"] == 10


# ---------------------------------------------------------------------------
# TrendData
# ---------------------------------------------------------------------------


def test_trend_data_series_labels():
    sm1 = SessionMetrics(session=1, prs=1, tests=10)
    sm2 = SessionMetrics(session=2, prs=3, tests=20)
    td = TrendData(sessions=[sm1, sm2], total_sessions=2, latest_session=2)
    d = td.to_dict()
    assert d["series"]["labels"] == ["S1", "S2"]
    assert d["series"]["prs"] == [1, 3]
    assert d["series"]["tests"] == [10, 20]


def test_trend_data_to_markdown():
    sm1 = SessionMetrics(session=1, date="Jan 2025", prs=1, tests=10,
                         modules=3, health_score=62.0)
    td = TrendData(sessions=[sm1], total_sessions=1, latest_session=1)
    md = td.to_markdown()
    assert "Historical Trend Data" in md
    assert "Jan 2025" in md
    assert "62" in md


# ---------------------------------------------------------------------------
# _parse_log
# ---------------------------------------------------------------------------


def test_parse_log_missing(tmp_path):
    result = _parse_log(tmp_path / "missing.md")
    assert result == []


def test_parse_log_empty(tmp_path):
    log = tmp_path / "log.md"
    log.write_text("# Awake Log\n\n")
    result = _parse_log(log)
    assert result == []


def test_parse_log_basic(tmp_path):
    log = tmp_path / "log.md"
    log.write_text("""
## Session 3 — February 15, 2025

**Stats snapshot:**

- Tests: 150
- Modules: 20
- Health: 72

---
""")
    result = _parse_log(log)
    assert len(result) == 1
    sm = result[0]
    assert sm.session == 3
    assert sm.date == "February 15, 2025"
    assert sm.tests == 150
    assert sm.modules == 20
    assert sm.health_score == 72.0


def test_parse_log_multiple_sessions(tmp_path):
    log = tmp_path / "log.md"
    log.write_text("""
## Session 1 — January 2025

---

## Session 2 — February 2025

---

## Session 3 — March 2025

---
""")
    result = _parse_log(log)
    assert len(result) == 3
    sessions = [r.session for r in result]
    assert 1 in sessions
    assert 2 in sessions
    assert 3 in sessions


# ---------------------------------------------------------------------------
# _interpolate_cumulative
# ---------------------------------------------------------------------------


def test_interpolate_fills_zeros():
    sm1 = SessionMetrics(session=1, tests=100)
    sm2 = SessionMetrics(session=2, tests=0)  # missing
    sm3 = SessionMetrics(session=3, tests=200)
    metrics = [sm1, sm2, sm3]
    _interpolate_cumulative(metrics)
    assert sm2.tests == 100  # propagated from sm1


def test_interpolate_does_not_overwrite_nonzero():
    sm1 = SessionMetrics(session=1, tests=100)
    sm2 = SessionMetrics(session=2, tests=150)
    metrics = [sm1, sm2]
    _interpolate_cumulative(metrics)
    assert sm2.tests == 150


# ---------------------------------------------------------------------------
# generate_trend_data
# ---------------------------------------------------------------------------


def test_generate_trend_data_no_log(tmp_path):
    td = generate_trend_data(tmp_path)
    assert isinstance(td, TrendData)
    # Should use seed data
    assert td.total_sessions >= len(_SEED_DATA)


def test_generate_trend_data_sessions_sorted(tmp_path):
    td = generate_trend_data(tmp_path)
    sessions = [s.session for s in td.sessions]
    assert sessions == sorted(sessions)


def test_generate_trend_data_seed_coverage():
    # All seed sessions should appear
    for sd in _SEED_DATA:
        assert "session" in sd
        assert "prs" in sd
        assert "tests" in sd
        assert "modules" in sd


def test_generate_trend_data_with_log(tmp_path):
    log = tmp_path / "AWAKE_LOG.md"
    log.write_text("""
## Session 17 — February 28, 2026

**Stats snapshot:**

- Tests: 1900
- Modules: 48

---
""")
    td = generate_trend_data(tmp_path)
    session_17 = next((s for s in td.sessions if s.session == 17), None)
    assert session_17 is not None
    assert session_17.tests == 1900
    assert session_17.modules == 48


def test_generate_trend_data_to_dict(tmp_path):
    td = generate_trend_data(tmp_path)
    d = td.to_dict()
    assert "sessions" in d
    assert "series" in d
    assert "labels" in d["series"]
    assert len(d["series"]["labels"]) == len(d["sessions"])


def test_generate_trend_data_series_not_empty(tmp_path):
    td = generate_trend_data(tmp_path)
    d = td.to_dict()
    assert len(d["series"]["prs"]) > 0
    assert len(d["series"]["tests"]) > 0


def test_seed_data_is_monotonically_increasing():
    """PRs and tests should increase session over session in seed data."""
    prev_tests = -1
    for sd in _SEED_DATA:
        assert sd["tests"] >= prev_tests, f"Session {sd['session']} tests decreased"
        prev_tests = sd["tests"]
