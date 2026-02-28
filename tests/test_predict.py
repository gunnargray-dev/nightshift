"""Tests for src/predict.py — Session 16."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _import():
    from src import predict
    return predict


# ---------------------------------------------------------------------------
# _parse_session_log
# ---------------------------------------------------------------------------

class TestParseSessionLog:
    def test_missing_log(self, tmp_path):
        p = _import()
        result = p._parse_session_log(tmp_path / "NIGHTSHIFT_LOG.md")
        assert result == []

    def test_parses_sessions(self, tmp_path):
        p = _import()
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text(
            "## Session 1\n\n`src/health.py` `src/stats.py`\n\n"
            "Total PRs: 5\nTest suite: 100 tests\n\n"
            "## Session 2\n\n`src/security.py`\n\nTotal PRs: 7\nTest suite: 150 tests\n",
            encoding="utf-8",
        )
        sessions = p._parse_session_log(log)
        assert len(sessions) == 2
        assert sessions[0]["session"] == 1
        assert "health" in sessions[0]["modules_touched"]

    def test_extracts_module_names(self, tmp_path):
        p = _import()
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text(
            "## Session 3\n\n`src/brain.py` `src/dna.py`\n\nTotal PRs: 10\n",
            encoding="utf-8",
        )
        sessions = p._parse_session_log(log)
        assert "brain" in sessions[0]["modules_touched"]
        assert "dna" in sessions[0]["modules_touched"]

    def test_no_duplicate_modules(self, tmp_path):
        p = _import()
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text(
            "## Session 1\n\n`src/health.py` `src/health.py`\n\nTotal PRs: 1\n",
            encoding="utf-8",
        )
        sessions = p._parse_session_log(log)
        assert sessions[0]["modules_touched"].count("health") == 1


# ---------------------------------------------------------------------------
# _get_all_modules
# ---------------------------------------------------------------------------

class TestGetAllModules:
    def test_finds_modules(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "health.py").write_text("pass")
        (src / "security.py").write_text("pass")
        (src / "__init__.py").write_text("pass")
        modules = p._get_all_modules(tmp_path)
        assert "health" in modules
        assert "security" in modules
        assert "__init__" not in modules

    def test_no_src_returns_empty(self, tmp_path):
        p = _import()
        modules = p._get_all_modules(tmp_path)
        assert modules == []


# ---------------------------------------------------------------------------
# _last_session_touched
# ---------------------------------------------------------------------------

class TestLastSessionTouched:
    def test_returns_correct_session(self):
        p = _import()
        sessions = [
            {"session": 1, "modules_touched": ["health"]},
            {"session": 2, "modules_touched": ["security"]},
            {"session": 3, "modules_touched": ["health"]},
        ]
        assert p._last_session_touched("health", sessions) == 3

    def test_returns_none_for_untouched(self):
        p = _import()
        sessions = [{"session": 1, "modules_touched": ["health"]}]
        assert p._last_session_touched("brain", sessions) is None


# ---------------------------------------------------------------------------
# Signal computation
# ---------------------------------------------------------------------------

class TestSignals:
    def test_age_signal_never_touched(self):
        p = _import()
        sig = p._compute_age_signal("newmodule", [], 5)
        assert sig.score > 0
        assert sig.weight > 0

    def test_age_signal_just_touched(self):
        p = _import()
        sessions = [{"session": 5, "modules_touched": ["health"]}]
        sig = p._compute_age_signal("health", sessions, 5)
        assert sig.score == 0.0

    def test_todo_signal_no_todos(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "clean.py").write_text("def foo():\n    pass\n", encoding="utf-8")
        sig = p._compute_todo_signal("clean", tmp_path)
        assert sig.score == 0.0

    def test_todo_signal_with_todos(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "messy.py").write_text(
            "# TODO: fix this\n# FIXME: and this\ndef foo(): pass\n",
            encoding="utf-8",
        )
        sig = p._compute_todo_signal("messy", tmp_path)
        assert sig.score > 0

    def test_complexity_signal_simple(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "simple.py").write_text(
            "def foo():\n    return 42\n",
            encoding="utf-8",
        )
        sig = p._compute_complexity_signal("simple", tmp_path)
        # Simple function = low complexity = low urgency
        assert sig.score < 50

    def test_complexity_signal_missing_file(self, tmp_path):
        p = _import()
        sig = p._compute_complexity_signal("doesntexist", tmp_path)
        assert sig.score >= 0

    def test_coverage_signal_handles_exception(self, tmp_path):
        p = _import()
        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError("boom")):
            sig = p._compute_coverage_signal("health", tmp_path)
        assert sig.score >= 0

    def test_health_signal_no_mentions(self):
        p = _import()
        sessions = [{"session": 1, "body": "session content here"}]
        sig = p._compute_health_signal("health", sessions)
        assert sig.score == 0.0

    def test_health_signal_with_mentions(self):
        p = _import()
        sessions = [
            {"session": 1, "body": "fix in health.py was needed, refactor health.py done"},
        ]
        sig = p._compute_health_signal("health", sessions)
        assert sig.score > 0


# ---------------------------------------------------------------------------
# predict_next_session
# ---------------------------------------------------------------------------

class TestPredictNextSession:
    def test_returns_report(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "health.py").write_text("def check(): pass\n", encoding="utf-8")
        (src / "security.py").write_text("def audit(): pass\n", encoding="utf-8")
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text(
            "## Session 1\n\n`src/health.py`\n\nTotal PRs: 5\nTest suite: 100\n",
            encoding="utf-8",
        )
        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError):
            report = p.predict_next_session(tmp_path)

        assert report.next_session == 2
        assert len(report.items) >= 1
        assert all(i.rank > 0 for i in report.items)

    def test_items_sorted_by_priority(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        for name in ["health", "security", "brain"]:
            (src / f"{name}.py").write_text("def foo(): pass\n", encoding="utf-8")

        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError):
            report = p.predict_next_session(tmp_path)

        scores = [i.priority_score for i in report.items]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_are_sequential(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "health.py").write_text("def foo(): pass\n", encoding="utf-8")

        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError):
            report = p.predict_next_session(tmp_path)

        for i, item in enumerate(report.items, start=1):
            assert item.rank == i

    def test_to_json_valid(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "health.py").write_text("def foo(): pass\n", encoding="utf-8")

        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError):
            report = p.predict_next_session(tmp_path)

        parsed = json.loads(report.to_json())
        assert "next_session" in parsed
        assert "items" in parsed

    def test_to_markdown_has_recommendations(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "health.py").write_text("def foo(): pass\n", encoding="utf-8")

        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError):
            report = p.predict_next_session(tmp_path)

        md = report.to_markdown()
        assert "Recommendations" in md or "Forecast" in md

    def test_no_src_directory(self, tmp_path):
        p = _import()
        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError):
            report = p.predict_next_session(tmp_path)
        assert report is not None

    def test_save_prediction_report(self, tmp_path):
        p = _import()
        src = tmp_path / "src"
        src.mkdir()
        (src / "health.py").write_text("def foo(): pass\n", encoding="utf-8")

        with patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError):
            report = p.predict_next_session(tmp_path)

        out = tmp_path / "docs" / "predict_report.md"
        p.save_prediction_report(report, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()


# ---------------------------------------------------------------------------
# PredictionReport
# ---------------------------------------------------------------------------

class TestPredictionReport:
    def _make_report(self):
        p = _import()
        items = [
            p.PredictionItem(
                rank=1,
                action="Improve test coverage for security.py",
                target="security",
                priority_score=82.0,
                signals=[
                    p.PredictionSignal("Coverage", 90.0, 0.25, "only 5 tests"),
                ],
                recommendation="High priority, improve coverage",
                suggested_command="nightshift coveragemap",
            ),
            p.PredictionItem(
                rank=2,
                action="Refactor brain.py",
                target="brain",
                priority_score=65.0,
                signals=[
                    p.PredictionSignal("Complexity", 70.0, 0.20, "avg CC 8.2"),
                ],
                recommendation="Medium priority",
                suggested_command="nightshift refactor",
            ),
        ]
        return p.PredictionReport(
            next_session=16,
            items=items,
            signals_used=["Coverage", "Complexity"],
            session_count=15,
            generated_at="2026-02-28T09:00:00",
        )

    def test_top_items_capped_at_5(self):
        r = self._make_report()
        assert len(r.top_items) <= 5

    def test_top_items_are_first_items(self):
        r = self._make_report()
        assert r.top_items[0].rank == 1

    def test_to_dict_keys(self):
        r = self._make_report()
        d = r.to_dict()
        assert "next_session" in d
        assert "items" in d
        assert "signals_used" in d
        assert "session_count" in d

    def test_to_markdown_has_table(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "| Rank |" in md
        assert "security" in md
