"""Tests for src/dashboard.py — Nightshift Terminal Dashboard."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.dashboard import (
    build_dashboard,
    render_dashboard,
    Dashboard,
    DashboardSection,
    _top_border,
    _bottom_border,
    _mid_border,
    _row,
    _bar_h,
    _sparkline,
    _parse_log_sessions,
    _BOX_LIGHT,
    _BOX_HEAVY,
)


# ---------------------------------------------------------------------------
# Box-drawing helpers
# ---------------------------------------------------------------------------

class TestTopBorder:
    def test_correct_width(self):
        border = _top_border(40)
        assert len(border) == 40

    def test_with_title(self):
        border = _top_border(40, title="TEST")
        assert "TEST" in border
        assert len(border) == 40

    def test_uses_corners(self):
        border = _top_border(10, style=_BOX_LIGHT)
        assert border[0] == _BOX_LIGHT["tl"]
        assert border[-1] == _BOX_LIGHT["tr"]


class TestBottomBorder:
    def test_correct_width(self):
        border = _bottom_border(40)
        assert len(border) == 40

    def test_uses_corners(self):
        border = _bottom_border(10, style=_BOX_LIGHT)
        assert border[0] == _BOX_LIGHT["bl"]
        assert border[-1] == _BOX_LIGHT["br"]


class TestMidBorder:
    def test_correct_width(self):
        border = _mid_border(40)
        assert len(border) == 40

    def test_uses_connectors(self):
        border = _mid_border(10, style=_BOX_LIGHT)
        assert border[0] == _BOX_LIGHT["ml"]
        assert border[-1] == _BOX_LIGHT["mr"]


class TestRow:
    def test_correct_width(self):
        row = _row("hello", 20)
        assert len(row) == 20

    def test_content_padded(self):
        row = _row("hi", 20)
        assert "hi" in row

    def test_truncated_if_too_long(self):
        row = _row("x" * 100, 20)
        assert len(row) == 20
        assert "…" in row

    def test_uses_vertical_bars(self):
        row = _row("content", 20, style=_BOX_LIGHT)
        assert row[0] == _BOX_LIGHT["v"]
        assert row[-1] == _BOX_LIGHT["v"]


class TestBarH:
    def test_full_bar(self):
        bar = _bar_h(100, 100, width=10)
        assert "█" * 10 in bar

    def test_empty_bar(self):
        bar = _bar_h(0, 100, width=10)
        assert "░" * 10 in bar

    def test_label_in_output(self):
        bar = _bar_h(50, 100, width=10, label="test label")
        assert "test label" in bar

    def test_percentage_shown(self):
        bar = _bar_h(50, 100, width=10)
        assert "50%" in bar

    def test_zero_max_no_error(self):
        bar = _bar_h(5, 0, width=10)
        assert isinstance(bar, str)


class TestSparkline:
    def test_empty_input(self):
        assert _sparkline([]) == ""

    def test_single_value(self):
        result = _sparkline([5])
        assert len(result) == 1

    def test_length_matches_input(self):
        values = [1, 2, 3, 4, 5]
        assert len(_sparkline(values)) == len(values)

    def test_returns_string(self):
        assert isinstance(_sparkline([1, 2, 3]), str)

    def test_uniform_no_error(self):
        assert isinstance(_sparkline([5, 5, 5, 5]), str)


# ---------------------------------------------------------------------------
# _parse_log_sessions
# ---------------------------------------------------------------------------

class TestParseLogSessions:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "NIGHTSHIFT_LOG.md"
        p.write_text("")
        assert _parse_log_sessions(p) == []

    def test_missing_file(self, tmp_path):
        p = tmp_path / "NIGHTSHIFT_LOG.md"
        assert _parse_log_sessions(p) == []

    def test_parses_session_with_prs(self, tmp_path):
        p = tmp_path / "NIGHTSHIFT_LOG.md"
        p.write_text(
            "## Session 1 — February 27, 2026\n"
            "\n"
            "some content here\n"
            "\n"
            "- Total PRs: 5\n"
        )
        sessions = _parse_log_sessions(p)
        assert len(sessions) == 1
        assert sessions[0]["number"] == 1
        assert sessions[0]["total_prs"] == 5

    def test_parses_multiple_sessions(self, tmp_path):
        p = tmp_path / "NIGHTSHIFT_LOG.md"
        p.write_text(
            "## Session 1 — Feb 1\ncontent\n- Total PRs: 3\n\n---\n\n"
            "## Session 2 — Feb 2\ncontent\n- Total PRs: 7\n"
        )
        sessions = _parse_log_sessions(p)
        assert len(sessions) == 2
        assert sessions[-1]["number"] == 2
        assert sessions[-1]["total_prs"] == 7


# ---------------------------------------------------------------------------
# Dashboard dataclass
# ---------------------------------------------------------------------------

class TestDashboard:
    def test_defaults(self):
        dash = Dashboard()
        assert dash.nights_active == 0
        assert dash.total_prs == 0
        assert dash.health_score is None
        assert dash.recent_sessions == []

    def test_to_dict(self):
        dash = Dashboard(nights_active=5, total_prs=10)
        d = dash.to_dict()
        assert isinstance(d, dict)
        assert d["nights_active"] == 5
        assert d["total_prs"] == 10

    def test_to_dict_json_serializable(self):
        dash = Dashboard(health_score=85.0, avg_complexity=3.5)
        serialized = json.dumps(dash.to_dict())
        assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# build_dashboard
# ---------------------------------------------------------------------------

class TestBuildDashboard:
    def test_returns_dashboard(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "src" / "foo.py").write_text('"""Docstring."""\ndef bar(): pass\n')
        (tmp_path / "src" / "__init__.py").write_text("")
        dash = build_dashboard(tmp_path)
        assert isinstance(dash, Dashboard)

    def test_src_files_count(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.py").write_text("")
        (src / "bar.py").write_text("")
        (src / "__init__.py").write_text("")
        dash = build_dashboard(tmp_path)
        assert dash.src_files == 2

    def test_test_files_count(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_foo.py").write_text("")
        (tests / "test_bar.py").write_text("")
        dash = build_dashboard(tmp_path)
        assert dash.test_files == 2

    def test_test_count_from_functions(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_foo.py").write_text(
            "def test_a(): pass\ndef test_b(): pass\n"
        )
        dash = build_dashboard(tmp_path)
        assert dash.total_tests == 2

    def test_repo_name(self, tmp_path):
        dash = build_dashboard(tmp_path)
        assert dash.repo_name == tmp_path.name

    def test_reads_log_sessions(self, tmp_path):
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
            "## Session 5 — Feb 1\ncontent\n- Total PRs: 10\n"
        )
        dash = build_dashboard(tmp_path)
        assert dash.nights_active == 1
        assert dash.total_prs == 10

    def test_recent_sessions_limited_to_5(self, tmp_path):
        log_text = ""
        for i in range(1, 10):
            log_text += f"## Session {i} — Feb 1\ncontent\n- Total PRs: {i * 2}\n\n---\n\n"
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(log_text)
        dash = build_dashboard(tmp_path)
        assert len(dash.recent_sessions) <= 5


# ---------------------------------------------------------------------------
# render_dashboard
# ---------------------------------------------------------------------------

class TestRenderDashboard:
    def test_returns_string(self):
        dash = Dashboard()
        result = render_dashboard(dash)
        assert isinstance(result, str)

    def test_contains_nightshift(self):
        dash = Dashboard()
        result = render_dashboard(dash)
        assert "NIGHTSHIFT" in result

    def test_contains_stat_labels(self):
        dash = Dashboard(nights_active=7, total_prs=20)
        result = render_dashboard(dash)
        assert "7" in result
        assert "20" in result

    def test_contains_source_section(self):
        dash = Dashboard(src_files=15, src_lines=5000)
        result = render_dashboard(dash)
        assert "SOURCE" in result

    def test_contains_metrics_section(self):
        dash = Dashboard(health_score=80.0)
        result = render_dashboard(dash)
        assert "METRICS" in result

    def test_contains_sessions_section(self):
        dash = Dashboard(recent_sessions=[{"number": 1, "total_prs": 3}])
        result = render_dashboard(dash)
        assert "RECENT SESSIONS" in result

    def test_uses_box_chars(self):
        dash = Dashboard()
        result = render_dashboard(dash)
        assert any(c in result for c in "┏┓┗┛━┃┣┫")

    def test_to_markdown_delegates(self):
        dash = Dashboard()
        assert dash.to_markdown() == render_dashboard(dash)

    def test_multiple_lines(self):
        dash = Dashboard()
        result = render_dashboard(dash)
        assert result.count("\n") > 5

    def test_health_trend_sparkline(self):
        dash = Dashboard(health_score=80.0, health_trend=[70, 75, 78, 80])
        result = render_dashboard(dash)
        assert "Health" in result

    def test_complexity_rendered_if_present(self):
        dash = Dashboard(avg_complexity=3.5)
        result = render_dashboard(dash)
        assert "Complexity" in result

    def test_instability_rendered_if_present(self):
        dash = Dashboard(avg_instability=0.45)
        result = render_dashboard(dash)
        assert "Coupling" in result
