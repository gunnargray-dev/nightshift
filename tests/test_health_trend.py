"""Tests for src/health_trend.py — health trend visualization."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.health_trend import (
    sparkline,
    FileHealthSnapshot,
    HealthSnapshot,
    HealthTrendHistory,
    snapshot_from_health_report,
    load_health_history,
    save_health_history,
    record_session_health,
    _SPARK_CHARS,
)


class TestSparkline:
    def test_empty_returns_empty_string(self):
        assert sparkline([]) == ""

    def test_single_value(self):
        result = sparkline([50.0])
        assert len(result) == 1 and result in _SPARK_CHARS

    def test_uniform_values_middle_char(self):
        result = sparkline([80.0, 80.0, 80.0])
        assert all(c == _SPARK_CHARS[4] for c in result)

    def test_ascending_trend(self):
        result = sparkline([10.0, 30.0, 50.0, 70.0, 90.0])
        assert len(result) == 5
        for i in range(1, len(result)):
            assert _SPARK_CHARS.index(result[i]) >= _SPARK_CHARS.index(result[i - 1])

    def test_descending_trend(self):
        result = sparkline([90.0, 70.0, 50.0, 30.0, 10.0])
        for i in range(1, len(result)):
            assert _SPARK_CHARS.index(result[i]) <= _SPARK_CHARS.index(result[i - 1])

    def test_width_clamps_to_last_n(self):
        assert len(sparkline([10, 20, 30, 40, 50], width=3)) == 3

    def test_width_larger_than_values_ok(self):
        assert len(sparkline([10, 20], width=10)) == 2

    def test_full_range_uses_all_chars(self):
        values = [0, 14, 28, 43, 57, 71, 86, 100]
        result = sparkline(values)
        assert result[0] == _SPARK_CHARS[0] and result[-1] == _SPARK_CHARS[-1]


class TestFileHealthSnapshot:
    def test_to_dict_contains_path_and_score(self):
        snap = FileHealthSnapshot(path="src/stats.py", score=88.5, lines=200)
        d = snap.to_dict()
        assert d["path"] == "src/stats.py" and d["score"] == 88.5

    def test_from_dict_roundtrip(self):
        snap = FileHealthSnapshot(path="src/foo.py", score=92.0, lines=100, docstring_coverage=0.8)
        snap2 = FileHealthSnapshot.from_dict(snap.to_dict())
        assert snap2.path == snap.path and snap2.score == snap.score


class TestHealthSnapshot:
    def test_health_badge_green(self):
        snap = HealthSnapshot(session=1, timestamp="2026-02-27", overall_score=95.0)
        assert "🟢" in snap.health_badge and "95.0" in snap.health_badge

    def test_health_badge_yellow(self):
        assert "🟡" in HealthSnapshot(session=1, timestamp="t", overall_score=75.0).health_badge

    def test_health_badge_red(self):
        assert "🔴" in HealthSnapshot(session=1, timestamp="t", overall_score=60.0).health_badge

    def test_to_dict_has_required_keys(self):
        d = HealthSnapshot(session=2, timestamp="t", overall_score=88.0).to_dict()
        assert all(k in d for k in ("session", "timestamp", "overall_score", "files"))

    def test_from_dict_roundtrip(self):
        snap = HealthSnapshot(session=3, timestamp="2026-02-27 22:00 UTC", overall_score=91.5,
                              files=[FileHealthSnapshot(path="src/stats.py", score=95.0)])
        snap2 = HealthSnapshot.from_dict(snap.to_dict())
        assert snap2.session == 3 and snap2.overall_score == 91.5 and len(snap2.files) == 1


class TestHealthTrendHistory:
    def _make(self, scores: list[tuple[int, float]]) -> HealthTrendHistory:
        history = HealthTrendHistory()
        for session, score in scores:
            history.append(HealthSnapshot(session=session, timestamp="t", overall_score=score))
        return history

    def test_append_adds_snapshot(self):
        h = HealthTrendHistory()
        h.append(HealthSnapshot(session=1, timestamp="t", overall_score=88.0))
        assert len(h.snapshots) == 1

    def test_append_replaces_same_session(self):
        h = HealthTrendHistory()
        h.append(HealthSnapshot(session=1, timestamp="t1", overall_score=80.0))
        h.append(HealthSnapshot(session=1, timestamp="t2", overall_score=90.0))
        assert len(h.snapshots) == 1 and h.snapshots[0].overall_score == 90.0

    def test_latest_returns_highest_session(self):
        h = self._make([(1, 80.0), (3, 88.0), (2, 85.0)])
        assert h.latest().session == 3

    def test_latest_empty_returns_none(self):
        assert HealthTrendHistory().latest() is None

    def test_scores_sorted(self):
        h = self._make([(3, 90.0), (1, 80.0), (2, 85.0)])
        sessions = [s for s, _ in h.scores()]
        assert sessions == sorted(sessions)

    def test_to_markdown_empty(self):
        assert "No health trend data" in HealthTrendHistory().to_markdown()

    def test_to_markdown_with_data(self):
        h = self._make([(1, 85.0), (2, 88.0), (3, 91.0)])
        md = h.to_markdown()
        assert "Session" in md and "| 1 |" in md and "| 3 |" in md

    def test_to_markdown_trend_sparkline_present(self):
        h = self._make([(1, 70.0), (2, 80.0), (3, 90.0)])
        md = h.to_markdown()
        assert any(c in md for c in _SPARK_CHARS)

    def test_to_markdown_delta_computed(self):
        h = self._make([(1, 80.0), (2, 90.0)])
        assert "+10.0" in h.to_markdown()

    def test_to_per_file_markdown_empty(self):
        assert "No per-file data" in HealthTrendHistory().to_per_file_markdown()

    def test_to_per_file_markdown_with_data(self):
        h = HealthTrendHistory()
        h.append(HealthSnapshot(session=1, timestamp="t1", overall_score=80.0,
                                files=[FileHealthSnapshot(path="src/stats.py", score=85.0)]))
        h.append(HealthSnapshot(session=2, timestamp="t2", overall_score=90.0,
                                files=[FileHealthSnapshot(path="src/stats.py", score=95.0)]))
        md = h.to_per_file_markdown()
        assert "stats.py" in md and "85" in md and "95" in md

    def test_file_trends_returns_dict(self):
        h = HealthTrendHistory()
        h.append(HealthSnapshot(session=1, timestamp="t1", overall_score=80.0,
                                files=[FileHealthSnapshot(path="src/stats.py", score=85.0)]))
        trends = h.file_trends()
        assert "src/stats.py" in trends and trends["src/stats.py"] == [(1, 85.0)]

    def test_to_dict_from_dict_roundtrip(self):
        h = HealthTrendHistory()
        h.append(HealthSnapshot(session=1, timestamp="t1", overall_score=88.0))
        h.append(HealthSnapshot(session=2, timestamp="t2", overall_score=92.0))
        h2 = HealthTrendHistory.from_dict(h.to_dict())
        assert len(h2.snapshots) == 2 and h2.snapshots[0].overall_score == 88.0


class TestSnapshotFromHealthReport:
    def test_creates_snapshot_from_mock_report(self):
        mock_report = MagicMock()
        mock_report.overall_health_score = 88.5
        mock_file = MagicMock()
        mock_file.path = "src/stats.py"
        mock_file.health_score = 90.0
        mock_file.total_lines = 200
        mock_file.docstring_coverage = 0.9
        mock_file.todo_count = 0
        mock_file.long_lines = 2
        mock_report.files = [mock_file]
        snap = snapshot_from_health_report(session=4, report=mock_report)
        assert snap.session == 4 and snap.overall_score == 88.5
        assert len(snap.files) == 1 and snap.files[0].path == "src/stats.py"

    def test_timestamp_is_set(self):
        mock_report = MagicMock()
        mock_report.overall_health_score = 80.0
        mock_report.files = []
        snap = snapshot_from_health_report(session=1, report=mock_report)
        assert snap.timestamp != "" and "UTC" in snap.timestamp


class TestLoadSaveHistory:
    def test_load_missing_file_returns_empty(self, tmp_path):
        h = load_health_history(tmp_path / "nonexistent.json")
        assert isinstance(h, HealthTrendHistory) and h.snapshots == []

    def test_save_and_load_roundtrip(self, tmp_path):
        path = tmp_path / "history.json"
        h = HealthTrendHistory()
        h.append(HealthSnapshot(session=1, timestamp="2026-02-27", overall_score=88.0))
        save_health_history(h, path)
        loaded = load_health_history(path)
        assert len(loaded.snapshots) == 1 and loaded.snapshots[0].overall_score == 88.0

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "docs" / "health_history.json"
        save_health_history(HealthTrendHistory(), path)
        assert path.exists()

    def test_saved_json_is_valid(self, tmp_path):
        path = tmp_path / "history.json"
        h = HealthTrendHistory()
        h.append(HealthSnapshot(session=1, timestamp="t1", overall_score=85.0))
        save_health_history(h, path)
        data = json.loads(path.read_text())
        assert "snapshots" in data and len(data["snapshots"]) == 1


class TestRecordSessionHealth:
    def test_creates_and_updates_history(self, tmp_path):
        mock_report = MagicMock()
        mock_report.overall_health_score = 91.0
        mock_report.files = []
        with patch("src.health.generate_health_report", return_value=mock_report):
            history = record_session_health(repo_path=tmp_path, session=4)
        assert len(history.snapshots) == 1 and history.snapshots[0].session == 4

    def test_history_file_written(self, tmp_path):
        mock_report = MagicMock()
        mock_report.overall_health_score = 88.0
        mock_report.files = []
        with patch("src.health.generate_health_report", return_value=mock_report):
            record_session_health(repo_path=tmp_path, session=4)
        assert (tmp_path / "docs" / "health_history.json").exists()

    def test_appends_to_existing_history(self, tmp_path):
        mock_report = MagicMock()
        mock_report.overall_health_score = 88.0
        mock_report.files = []
        history_path = tmp_path / "docs" / "health_history.json"
        history_path.parent.mkdir(parents=True)
        existing = HealthTrendHistory()
        existing.append(HealthSnapshot(session=3, timestamp="t", overall_score=85.0))
        save_health_history(existing, history_path)
        with patch("src.health.generate_health_report", return_value=mock_report):
            history = record_session_health(repo_path=tmp_path, session=4, history_path=history_path)
        assert len(history.snapshots) == 2
        sessions = [s.session for s in history.snapshots]
        assert 3 in sessions and 4 in sessions
