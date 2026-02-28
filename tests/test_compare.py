"""Tests for src/compare.py — Session Compare."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
import pytest

from src.compare import (
    compare_sessions,
    render_comparison,
    SessionComparison,
    StatDelta,
    _extract_stat_int,
    _task_labels,
    _module_names,
    _pr_labels,
    _bar,
)
from src.session_replay import SessionReplay


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LOG = textwrap.dedent("""\
    # Nightshift Log

    ## Session 1 — February 27, 2026

    **Operator:** Computer (autonomous)

    **Tasks completed:**

    - ✅ **Self-stats engine** → [PR #1](https://github.com/gunnargray-dev/nightshift/pull/1) — stats.py built
    - ✅ **Session logger** → [PR #1](https://github.com/gunnargray-dev/nightshift/pull/1) — session_logger.py built
    - ✅ **CI pipeline** → [PR #2](https://github.com/gunnargray-dev/nightshift/pull/2) — ci.yml added

    **Pull requests:**

    - [#1](https://github.com/gunnargray-dev/nightshift/pull/1) — stats + logger (`nightshift/session-1-stats`)
    - [#2](https://github.com/gunnargray-dev/nightshift/pull/2) — CI pipeline (`nightshift/session-1-ci`)

    **Decisions & rationale:**

    - Used stdlib only to avoid dependencies.
    - Kept CI minimal for session 1.

    **Stats snapshot:**

    - Nights active: 1
    - Total PRs: 2
    - Total commits: 3
    - Lines changed: ~700

    **Notes:** First session.

    ---

    ## Session 2 — February 27, 2026

    **Operator:** Computer (autonomous)

    **Tasks completed:**

    - ✅ **Code health monitor** → [PR #3](https://github.com/gunnargray-dev/nightshift/pull/3) — health.py built
    - ✅ **Changelog generator** → [PR #4](https://github.com/gunnargray-dev/nightshift/pull/4) — changelog.py built
    - ✅ **Coverage tracker** → [PR #5](https://github.com/gunnargray-dev/nightshift/pull/5) — coverage_tracker.py built

    **Pull requests:**

    - [#3](https://github.com/gunnargray-dev/nightshift/pull/3) — health (`nightshift/session-2-health`)
    - [#4](https://github.com/gunnargray-dev/nightshift/pull/4) — changelog (`nightshift/session-2-changelog`)
    - [#5](https://github.com/gunnargray-dev/nightshift/pull/5) — coverage (`nightshift/session-2-coverage`)

    **Decisions & rationale:**

    - Health scoring is AST-based for robustness.
    - Coverage history stored as JSON.

    **Stats snapshot:**

    - Nights active: 2
    - Total PRs: 5
    - Total commits: 8
    - Lines changed: ~1800

    **Notes:** Session 2 theme: instrumentation.

    ---

    *This log is maintained autonomously by Computer.*
""")


@pytest.fixture()
def log_file(tmp_path) -> Path:
    p = tmp_path / "NIGHTSHIFT_LOG.md"
    p.write_text(SAMPLE_LOG)
    return p


def _make_replay(session_number: int, tasks=None, prs=None, stats=None, decisions=None):
    """Helper to create a SessionReplay for unit testing."""
    return SessionReplay(
        session_number=session_number,
        date="February 27, 2026",
        operator="Computer (autonomous)",
        tasks=tasks or [],
        prs=prs or [],
        decisions=decisions or [],
        stats_snapshot=stats or {},
        notes="",
        raw_section="",
    )


# ---------------------------------------------------------------------------
# StatDelta
# ---------------------------------------------------------------------------

class TestStatDelta:
    def test_delta_positive(self):
        sd = StatDelta("Total PRs", before=5, after=10)
        assert sd.delta == 5
        assert sd.delta_str == "+5"
        assert sd.symbol == "▲"

    def test_delta_negative(self):
        sd = StatDelta("Tests", before=100, after=80)
        assert sd.delta == -20
        assert sd.symbol == "▼"

    def test_delta_zero(self):
        sd = StatDelta("Commits", before=10, after=10)
        assert sd.delta == 0
        assert sd.symbol == "="

    def test_delta_none_when_before_missing(self):
        sd = StatDelta("X", before=None, after=10)
        assert sd.delta is None
        assert sd.delta_str == "?"
        assert sd.symbol == "·"

    def test_delta_none_when_after_missing(self):
        sd = StatDelta("X", before=5, after=None)
        assert sd.delta is None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestExtractStatInt:
    def test_extracts_nights(self):
        r = _make_replay(1, stats={"nights_active": "3", "total_prs": "7"})
        assert _extract_stat_int(r, "Nights active") == 3

    def test_extracts_prs(self):
        r = _make_replay(1, stats={"total_prs": "17"})
        assert _extract_stat_int(r, "Total PRs") == 17

    def test_returns_none_for_missing(self):
        r = _make_replay(1, stats={"nights_active": "3"})
        assert _extract_stat_int(r, "Total Commits") is None

    def test_returns_none_for_none_replay(self):
        assert _extract_stat_int(None, "Total PRs") is None

    def test_handles_tilde_prefix(self):
        r = _make_replay(1, stats={"lines_changed": "~700"})
        assert _extract_stat_int(r, "Lines Changed") == 700


class TestTaskLabels:
    def test_returns_lowercased(self):
        from src.session_replay import ReplayedTask
        tasks = [
            ReplayedTask(name="Self-Stats Engine", description="", status="completed", pr_number=1, pr_url=""),
            ReplayedTask(name="CI Pipeline", description="", status="completed", pr_number=2, pr_url=""),
        ]
        r = _make_replay(1, tasks=tasks)
        labels = _task_labels(r)
        assert "self-stats engine" in labels
        assert "ci pipeline" in labels

    def test_returns_empty_for_none(self):
        assert _task_labels(None) == []

    def test_returns_empty_for_empty_tasks(self):
        r = _make_replay(1, tasks=[])
        assert _task_labels(r) == []


class TestModuleNames:
    def test_returns_lowercased(self):
        from src.session_replay import ReplayedTask
        tasks = [
            ReplayedTask(name="Health", description="Built `src/health.py` for analysis", status="completed", pr_number=1, pr_url=""),
        ]
        r = _make_replay(1, tasks=tasks)
        names = _module_names(r)
        assert isinstance(names, list)

    def test_returns_empty_for_none(self):
        assert _module_names(None) == []


class TestPrLabels:
    def test_returns_pr_strings(self):
        from src.session_replay import ReplayedPR
        prs = [ReplayedPR(number=1, title="feat: stats", url="https://github.com/x/y/pull/1", branch="nightshift/session-1")]
        r = _make_replay(1, prs=prs)
        labels = _pr_labels(r)
        assert "#1: feat: stats" in labels

    def test_returns_empty_for_none(self):
        assert _pr_labels(None) == []


# ---------------------------------------------------------------------------
# _bar helper
# ---------------------------------------------------------------------------

class TestBar:
    def test_full_bar(self):
        bar = _bar(100, 100, width=10)
        assert bar == "█" * 10

    def test_empty_bar(self):
        bar = _bar(0, 100, width=10)
        assert bar == "░" * 10

    def test_half_bar(self):
        bar = _bar(50, 100, width=10)
        assert bar.count("█") == 5
        assert bar.count("░") == 5

    def test_none_value(self):
        bar = _bar(None, 100)
        assert "░" in bar

    def test_zero_max(self):
        bar = _bar(50, 0)
        assert isinstance(bar, str)


# ---------------------------------------------------------------------------
# compare_sessions (integration with real log)
# ---------------------------------------------------------------------------

class TestCompareSessions:
    def test_returns_comparison(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        assert isinstance(cmp, SessionComparison)

    def test_session_numbers(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        assert cmp.session_a == 1
        assert cmp.session_b == 2

    def test_stat_deltas_populated(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        assert len(cmp.stat_deltas) > 0

    def test_nights_delta_is_positive(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        nights_delta = next(
            (sd for sd in cmp.stat_deltas if "nights" in sd.label.lower()), None
        )
        assert nights_delta is not None
        assert nights_delta.after == 2
        assert nights_delta.before == 1
        assert nights_delta.delta == 1

    def test_tasks_added_different_sessions(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        assert isinstance(cmp.tasks_added, list)

    def test_missing_session_returns_none_replays(self, log_file):
        cmp = compare_sessions(log_file, 1, 99)
        assert cmp.replay_b is None

    def test_comparison_both_missing(self, log_file):
        cmp = compare_sessions(log_file, 98, 99)
        assert cmp.replay_a is None
        assert cmp.replay_b is None


# ---------------------------------------------------------------------------
# render_comparison
# ---------------------------------------------------------------------------

class TestRenderComparison:
    def test_returns_string(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        md = render_comparison(cmp)
        assert isinstance(md, str)

    def test_contains_heading(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        md = render_comparison(cmp)
        assert "Session Comparison" in md
        assert "Session 1" in md
        assert "Session 2" in md

    def test_contains_stats_delta_section(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        md = render_comparison(cmp)
        assert "Stats Delta" in md

    def test_contains_task_diff_section(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        md = render_comparison(cmp)
        assert "Task Diff" in md

    def test_to_markdown_method(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        assert cmp.to_markdown() == render_comparison(cmp)


# ---------------------------------------------------------------------------
# SessionComparison.to_dict()
# ---------------------------------------------------------------------------

class TestSessionComparisonToDict:
    def test_returns_dict(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        d = cmp.to_dict()
        assert isinstance(d, dict)

    def test_contains_session_numbers(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        d = cmp.to_dict()
        assert d["session_a"] == 1
        assert d["session_b"] == 2

    def test_json_serializable(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        serialized = json.dumps(cmp.to_dict())
        assert isinstance(serialized, str)

    def test_stat_deltas_in_dict(self, log_file):
        cmp = compare_sessions(log_file, 1, 2)
        d = cmp.to_dict()
        assert "stat_deltas" in d
        assert isinstance(d["stat_deltas"], list)
