"""Tests for src/dashboard.py — terminal dashboard module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.dashboard import (
    DashboardPanel,
    DashboardData,
    build_dashboard,
    render_dashboard,
    _box,
    _bar,
)


# ---------------------------------------------------------------------------
# _box and _bar helpers
# ---------------------------------------------------------------------------


class TestBoxHelper:
    def test_box_contains_title(self):
        result = _box("Health", ["score: 95"], width=40)
        assert "Health" in result

    def test_box_has_top_left_corner(self):
        result = _box("Test", ["line1"], width=30)
        assert "┌" in result
        assert "┐" in result

    def test_box_has_bottom_corners(self):
        result = _box("Test", [], width=30)
        assert "└" in result
        assert "┘" in result

    def test_box_body_lines_enclosed(self):
        result = _box("Test", ["hello"], width=20)
        lines = result.splitlines()
        # Every body line (not header/footer) should start and end with │
        body_lines = lines[1:-1]
        for line in body_lines:
            assert line.startswith("│")
            assert line.endswith("│")

    def test_box_truncates_long_lines(self):
        long_line = "x" * 200
        result = _box("Test", [long_line], width=30)
        # Should not crash and output width should be bounded
        lines = result.splitlines()
        for line in lines:
            assert len(line) <= 35  # some slack for box chars


class TestBarHelper:
    def test_bar_full(self):
        b = _bar(100, 100, width=10)
        assert "██████████" in b

    def test_bar_empty(self):
        b = _bar(0, 100, width=10)
        assert "░░░░░░░░░░" in b

    def test_bar_half(self):
        b = _bar(50, 100, width=10)
        assert "█████" in b
        assert "░░░░░" in b

    def test_bar_shows_value(self):
        b = _bar(75, 100, width=5)
        assert "75" in b

    def test_bar_clamps_above_max(self):
        b = _bar(150, 100, width=5)
        assert "100" in b

    def test_bar_clamps_below_zero(self):
        b = _bar(-10, 100, width=5)
        assert "0" in b


# ---------------------------------------------------------------------------
# DashboardPanel
# ---------------------------------------------------------------------------


class TestDashboardPanel:
    def test_to_dict(self):
        panel = DashboardPanel(title="Test", items=[("key", "value")])
        d = panel.to_dict()
        assert d["title"] == "Test"
        assert d["items"]["key"] == "value"

    def test_empty_panel(self):
        panel = DashboardPanel(title="Empty")
        d = panel.to_dict()
        assert d["items"] == {}


# ---------------------------------------------------------------------------
# DashboardData
# ---------------------------------------------------------------------------


class TestDashboardData:
    def test_to_dict_structure(self):
        dash = DashboardData(generated_at="2026-01-01", repo_path="/tmp")
        d = dash.to_dict()
        assert "generated_at" in d
        assert "repo_path" in d
        assert "panels" in d

    def test_panels_serialised(self):
        dash = DashboardData()
        dash.panels.append(DashboardPanel("Health", [("Score", "95/100")]))
        d = dash.to_dict()
        assert len(d["panels"]) == 1
        assert d["panels"][0]["title"] == "Health"


# ---------------------------------------------------------------------------
# build_dashboard (with mock modules)
# ---------------------------------------------------------------------------


class TestBuildDashboard:
    def test_returns_dashboard_data(self, tmp_path):
        """build_dashboard should return DashboardData even if all modules fail."""
        dash = build_dashboard(tmp_path)
        assert isinstance(dash, DashboardData)

    def test_generated_at_is_set(self, tmp_path):
        dash = build_dashboard(tmp_path)
        assert dash.generated_at != ""

    def test_repo_path_is_set(self, tmp_path):
        dash = build_dashboard(tmp_path)
        assert str(tmp_path) in dash.repo_path

    def test_panels_populated(self, tmp_path):
        """Even with missing modules, we should get some panels."""
        dash = build_dashboard(tmp_path)
        assert len(dash.panels) >= 1

    def test_panel_titles_present(self, tmp_path):
        dash = build_dashboard(tmp_path)
        titles = [p.title for p in dash.panels]
        # At minimum these should be attempted
        assert any(t in titles for t in ("Code Health", "Repository Stats", "Configuration", "Session Summary"))

    def test_handles_import_errors_gracefully(self, tmp_path):
        """Dashboard should not crash even if a sub-module isn't available."""
        import importlib
        import sys
        # Temporarily hide src.health
        original = sys.modules.get("src.health")
        sys.modules["src.health"] = None  # type: ignore[assignment]
        try:
            dash = build_dashboard(tmp_path)
            assert isinstance(dash, DashboardData)
        finally:
            if original is None:
                sys.modules.pop("src.health", None)
            else:
                sys.modules["src.health"] = original


# ---------------------------------------------------------------------------
# render_dashboard
# ---------------------------------------------------------------------------


class TestRenderDashboard:
    def _make_dash(self) -> DashboardData:
        dash = DashboardData(generated_at="2026-02-28 06:00 UTC", repo_path="/tmp/repo")
        dash.panels = [
            DashboardPanel("Code Health", [("Score", "87/100"), ("Files analysed", "20")]),
            DashboardPanel("Repository Stats", [("Nights active", "12"), ("Total PRs", "45")]),
        ]
        return dash

    def test_render_returns_string(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        assert isinstance(result, str)

    def test_render_contains_title(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        assert "NIGHTSHIFT DASHBOARD" in result

    def test_render_contains_panel_titles(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        assert "Code Health" in result
        assert "Repository Stats" in result

    def test_render_contains_metric_values(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        assert "20" in result  # Files analysed
        assert "45" in result  # Total PRs

    def test_render_contains_generated_at(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        assert "2026-02-28" in result

    def test_render_contains_box_drawing_chars(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        assert "╔" in result or "┌" in result

    def test_render_score_shows_bar(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        # Score row should trigger bar rendering
        assert "█" in result or "░" in result

    def test_render_contains_repo_path(self):
        dash = self._make_dash()
        result = render_dashboard(dash)
        assert "/tmp/repo" in result

    def test_render_empty_dashboard(self):
        dash = DashboardData(generated_at="now", repo_path="/tmp")
        result = render_dashboard(dash)
        assert isinstance(result, str)
        assert len(result) > 0
