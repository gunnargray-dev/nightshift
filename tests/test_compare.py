"""Tests for src/compare.py — session comparison module."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.compare import (
    SessionSnapshot,
    DeltaMetric,
    SessionComparison,
    compare_sessions,
    _extract_session,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SESSION_3_CONTENT = """\
## Session 3 — February 15, 2026

**Operator:** Computer (autonomous)  

**Tasks completed:**

- ✅ **Health analysis** — Generated health report
- ✅ **Stats update** — Updated README stats
- ✅ **Changelog** — Regenerated CHANGELOG.md

**Pull requests:**

- [#42](https://github.com/example/repo/pull/42) — feat: health report (branch-x))
- [#43](https://github.com/example/repo/pull/43) — feat: stats (branch-y))

**Decisions & rationale:**

- Chose markdown output format for readability
- Deferred architecture doc to next session

**Notes:** Good session, no blockers.

---
"""

SESSION_5_CONTENT = """\
## Session 5 — February 25, 2026

**Operator:** Computer (autonomous)  

**Tasks completed:**

- ✅ **Health analysis** — Generated health report
- ✅ **Dependency graph** — Built dep_graph module
- ✅ **Doctor** — Added doctor module

**Pull requests:**

- [#60](https://github.com/example/repo/pull/60) — feat: dep graph (branch-z))

**Decisions & rationale:**

- Used recursive AST visitor for dep graph

---
"""

LOG_CONTENT = SESSION_3_CONTENT + SESSION_5_CONTENT


# ---------------------------------------------------------------------------
# DeltaMetric
# ---------------------------------------------------------------------------


class TestDeltaMetric:
    def test_positive_delta_up_arrow(self):
        m = DeltaMetric("Tasks", 3, 5)
        assert m.delta == 2
        assert m.symbol == "▲"

    def test_negative_delta_down_arrow(self):
        m = DeltaMetric("PRs", 5, 3)
        assert m.delta == -2
        assert m.symbol == "▼"

    def test_zero_delta_equals(self):
        m = DeltaMetric("Commits", 10, 10)
        assert m.delta == 0
        assert m.symbol == "="

    def test_to_dict(self):
        m = DeltaMetric("Tasks", 2, 4)
        d = m.to_dict()
        assert d["name"] == "Tasks"
        assert d["value_a"] == 2
        assert d["value_b"] == 4
        assert d["delta"] == 2
        assert d["symbol"] == "▲"


# ---------------------------------------------------------------------------
# _extract_session
# ---------------------------------------------------------------------------


class TestExtractSession:
    def test_extracts_session_3(self):
        snap = _extract_session(LOG_CONTENT, 3)
        assert snap is not None
        assert snap.session_number == 3
        assert "February 15, 2026" in snap.date
        assert snap.task_count == 3
        assert snap.pr_count == 2

    def test_extracts_session_5(self):
        snap = _extract_session(LOG_CONTENT, 5)
        assert snap is not None
        assert snap.session_number == 5
        assert snap.task_count == 3
        assert snap.pr_count == 1

    def test_returns_none_for_missing_session(self):
        snap = _extract_session(LOG_CONTENT, 99)
        assert snap is None

    def test_extracts_decisions(self):
        snap = _extract_session(LOG_CONTENT, 3)
        assert snap is not None
        assert len(snap.decisions) == 2

    def test_extracts_notes(self):
        snap = _extract_session(LOG_CONTENT, 3)
        assert snap is not None
        assert "Good session" in snap.notes

    def test_empty_log(self):
        snap = _extract_session("", 1)
        assert snap is None


# ---------------------------------------------------------------------------
# compare_sessions
# ---------------------------------------------------------------------------


class TestCompareSessions:
    def test_compare_produces_result(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        assert isinstance(cmp, SessionComparison)

    def test_session_a_and_b_populated(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        assert cmp.session_a.session_number == 3
        assert cmp.session_b.session_number == 5

    def test_metrics_include_tasks_and_prs(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        names = [m.name for m in cmp.metrics]
        assert "Tasks" in names
        assert "PRs" in names

    def test_tasks_added_detected(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        # Session 5 has Dependency graph and Doctor that Session 3 doesn't
        assert len(cmp.tasks_added) >= 1

    def test_tasks_removed_detected(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        # Session 3 has Stats update and Changelog that Session 5 doesn't
        assert len(cmp.tasks_removed) >= 1

    def test_tasks_common_detected(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        # Both sessions have Health analysis
        assert "Health analysis" in cmp.tasks_common

    def test_missing_log_file(self, tmp_path):
        log = tmp_path / "NO_LOG.md"  # does not exist
        cmp = compare_sessions(log, 1, 2)
        assert cmp.session_a.date == "not found"
        assert cmp.session_b.date == "not found"

    def test_to_dict_structure(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        d = cmp.to_dict()
        assert "session_a" in d
        assert "session_b" in d
        assert "metrics" in d
        assert "tasks_added" in d
        assert "tasks_removed" in d

    def test_to_markdown_contains_header(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        md = cmp.to_markdown()
        assert "Session Comparison" in md
        assert "3" in md
        assert "5" in md

    def test_to_markdown_contains_delta_symbols(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        md = cmp.to_markdown()
        # Should have at least one delta symbol in the table
        assert any(sym in md for sym in ("▲", "▼", "="))

    def test_pr_delta_direction(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(LOG_CONTENT)
        cmp = compare_sessions(log, 3, 5)
        pr_metric = next(m for m in cmp.metrics if m.name == "PRs")
        # Session 3 has 2 PRs, Session 5 has 1 PR → delta = -1
        assert pr_metric.delta == -1
        assert pr_metric.symbol == "▼"
