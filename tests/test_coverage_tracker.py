"""Tests for the Awake coverage tracker (src/coverage_tracker.py)."""

from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.coverage_tracker import (
    CoverageSnapshot,
    CoverageHistory,
    TOTAL_PATTERN,
    FILE_PATTERN,
    run_coverage,
    parse_coverage_output,
    load_coverage_history,
    save_coverage_history,
    record_coverage,
)


# ---------------------------------------------------------------------------
# CoverageSnapshot
# ---------------------------------------------------------------------------


class TestCoverageSnapshot:
    def _make(self, **kwargs) -> CoverageSnapshot:
        defaults = {
            "session": 1,
            "timestamp": "2026-02-28T00:00:00Z",
            "total_coverage": 95.0,
            "lines_covered": 190,
            "lines_total": 200,
            "missing_lines": 10,
        }
        defaults.update(kwargs)
        return CoverageSnapshot(**defaults)

    def test_defaults(self):
        s = CoverageSnapshot(
            session=1, timestamp="2026-02-28", total_coverage=95.0
        )
        assert s.files == {}
        assert s.lines_covered == 0

    def test_to_dict(self):
        s = self._make()
        d = s.to_dict()
        assert d["session"] == 1
        assert d["total_coverage"] == 95.0

    def test_from_dict_roundtrip(self):
        s = self._make(files={"src/stats.py": 98.0})
        d = s.to_dict()
        s2 = CoverageSnapshot.from_dict(d)
        assert s2.session == s.session
        assert s2.total_coverage == s.total_coverage
        assert s2.files == s.files

    def test_coverage_badge_green(self):
        s = self._make(total_coverage=95.0)
        assert "🟢" in s.coverage_badge
        assert "95.0%" in s.coverage_badge

    def test_coverage_badge_yellow(self):
        s = self._make(total_coverage=75.0)
        assert "🟡" in s.coverage_badge

    def test_coverage_badge_red(self):
        s = self._make(total_coverage=55.0)
        assert "🔴" in s.coverage_badge

    def test_coverage_badge_exactly_90(self):
        s = self._make(total_coverage=90.0)
        assert "🟢" in s.coverage_badge

    def test_coverage_badge_exactly_70(self):
        s = self._make(total_coverage=70.0)
        assert "🟡" in s.coverage_badge


# ---------------------------------------------------------------------------
# CoverageHistory
# ---------------------------------------------------------------------------


class TestCoverageHistory:
    def _make_snapshot(self, session: int, coverage: float) -> CoverageSnapshot:
        return CoverageSnapshot(
            session=session,
            timestamp=f"2026-02-{session:02d}T00:00:00Z",
            total_coverage=coverage,
            lines_covered=int(coverage),
            lines_total=100,
            missing_lines=100 - int(coverage),
        )

    def test_empty_history(self):
        h = CoverageHistory()
        assert h.latest() is None
        assert h.trend() == []

    def test_append_single(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 90.0))
        assert len(h.snapshots) == 1

    def test_append_replaces_same_session(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 90.0))
        h.append(self._make_snapshot(1, 95.0))
        assert len(h.snapshots) == 1
        assert h.snapshots[0].total_coverage == 95.0

    def test_append_sorted_by_session(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(3, 80.0))
        h.append(self._make_snapshot(1, 70.0))
        h.append(self._make_snapshot(2, 75.0))
        sessions = [s.session for s in h.snapshots]
        assert sessions == [1, 2, 3]

    def test_latest_returns_highest_session(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 70.0))
        h.append(self._make_snapshot(3, 90.0))
        h.append(self._make_snapshot(2, 80.0))
        assert h.latest().session == 3

    def test_trend(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 70.0))
        h.append(self._make_snapshot(2, 80.0))
        trend = h.trend()
        assert trend == [(1, 70.0), (2, 80.0)]

    def test_to_dict_roundtrip(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 90.0))
        d = h.to_dict()
        h2 = CoverageHistory.from_dict(d)
        assert len(h2.snapshots) == 1
        assert h2.snapshots[0].total_coverage == 90.0

    def test_to_markdown_empty(self):
        h = CoverageHistory()
        md = h.to_markdown()
        assert "No coverage data" in md

    def test_to_markdown_has_table(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 90.0))
        md = h.to_markdown()
        assert "| Session |" in md
        assert "| 1 |" in md

    def test_to_markdown_trend_arrows(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 70.0))
        h.append(self._make_snapshot(2, 80.0))
        md = h.to_markdown()
        assert "↑" in md

    def test_to_markdown_first_session_no_trend(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 90.0))
        md = h.to_markdown()
        assert "—" in md

    def test_to_markdown_decreasing_coverage(self):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 90.0))
        h.append(self._make_snapshot(2, 80.0))
        md = h.to_markdown()
        assert "↓" in md


# ---------------------------------------------------------------------------
# parse_coverage_output
# ---------------------------------------------------------------------------


class TestParseCoverageOutput:
    SAMPLE_OUTPUT = textwrap.dedent("""\
        ============================= test session starts ==============================
        collected 94 items

        ...

        ---------- coverage: platform linux, python 3.12.12-final-0 -----------
        Name                       Stmts   Miss  Cover
        --------------------------------------------------
        src/health.py                120      6    95%
        src/session_logger.py         90      3    97%
        src/stats.py                 100      2    98%
        --------------------------------------------------
        TOTAL                        310     11    96%

        ============================== 94 passed in 0.22s =============================
    """)

    def test_parses_total_coverage(self):
        result = parse_coverage_output(self.SAMPLE_OUTPUT)
        assert result["total_coverage"] == 96.0

    def test_parses_total_lines(self):
        result = parse_coverage_output(self.SAMPLE_OUTPUT)
        assert result["lines_total"] == 310

    def test_parses_missing_lines(self):
        result = parse_coverage_output(self.SAMPLE_OUTPUT)
        assert result["missing_lines"] == 11

    def test_parses_lines_covered(self):
        result = parse_coverage_output(self.SAMPLE_OUTPUT)
        assert result["lines_covered"] == 299  # 310 - 11

    def test_parses_per_file_coverage(self):
        result = parse_coverage_output(self.SAMPLE_OUTPUT)
        assert "src/health.py" in result["files"]
        assert result["files"]["src/health.py"] == 95.0
        assert result["files"]["src/stats.py"] == 98.0

    def test_empty_output_returns_zeros(self):
        result = parse_coverage_output("")
        assert result["total_coverage"] == 0.0
        assert result["lines_total"] == 0
        assert result["files"] == {}

    def test_handles_100_percent(self):
        output = "TOTAL   100    0   100%"
        result = parse_coverage_output(output)
        assert result["total_coverage"] == 100.0
        assert result["missing_lines"] == 0

    def test_handles_missing_file_lines(self):
        output = "TOTAL   200   40   80%"
        result = parse_coverage_output(output)
        assert result["lines_total"] == 200
        assert result["missing_lines"] == 40
        assert result["lines_covered"] == 160


# ---------------------------------------------------------------------------
# load / save coverage history
# ---------------------------------------------------------------------------


class TestLoadSaveCoverageHistory:
    def _make_snapshot(self, session: int, coverage: float) -> CoverageSnapshot:
        return CoverageSnapshot(
            session=session,
            timestamp="2026-02-28T00:00:00Z",
            total_coverage=coverage,
            lines_covered=int(coverage),
            lines_total=100,
            missing_lines=100 - int(coverage),
        )

    def test_load_missing_file_returns_empty(self, tmp_path):
        h = load_coverage_history(tmp_path / "nonexistent.json")
        assert isinstance(h, CoverageHistory)
        assert h.snapshots == []

    def test_save_and_load_roundtrip(self, tmp_path):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 90.0))
        h.append(self._make_snapshot(2, 95.0))
        path = tmp_path / "coverage.json"
        save_coverage_history(h, path)
        h2 = load_coverage_history(path)
        assert len(h2.snapshots) == 2
        assert h2.snapshots[0].total_coverage == 90.0

    def test_save_creates_parent_dirs(self, tmp_path):
        h = CoverageHistory()
        path = tmp_path / "docs" / "subdir" / "coverage.json"
        save_coverage_history(h, path)
        assert path.exists()

    def test_load_invalid_json_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json!!!")
        h = load_coverage_history(path)
        assert h.snapshots == []

    def test_saved_file_is_valid_json(self, tmp_path):
        h = CoverageHistory()
        h.append(self._make_snapshot(1, 85.0))
        path = tmp_path / "coverage.json"
        save_coverage_history(h, path)
        data = json.loads(path.read_text())
        assert "snapshots" in data


# ---------------------------------------------------------------------------
# run_coverage
# ---------------------------------------------------------------------------


class TestRunCoverage:
    def test_returns_string(self, tmp_path):
        with patch("src.coverage_tracker.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                stdout="94 passed",
                stderr="TOTAL  100  5  95%",
                returncode=0,
            )
            result = run_coverage(tmp_path)
        assert isinstance(result, str)

    def test_returns_empty_on_file_not_found(self, tmp_path):
        with patch("src.coverage_tracker.subprocess.run", side_effect=FileNotFoundError):
            result = run_coverage(tmp_path)
        assert result == ""

    def test_returns_empty_on_timeout(self, tmp_path):
        with patch(
            "src.coverage_tracker.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pytest", 120),
        ):
            result = run_coverage(tmp_path)
        assert result == ""


# ---------------------------------------------------------------------------
# record_coverage (integration)
# ---------------------------------------------------------------------------


class TestRecordCoverage:
    def _make_mock_output(self, coverage: int = 95) -> str:
        return f"TOTAL   100   {100-coverage}   {coverage}%\nsrc/stats.py   50   2   96%\n"

    def test_returns_snapshot(self, tmp_path):
        with patch("src.coverage_tracker.run_coverage", return_value=self._make_mock_output()):
            snap = record_coverage(
                session=1,
                repo_path=tmp_path,
                history_path=tmp_path / "coverage.json",
                timestamp="2026-02-28T00:00:00Z",
            )
        assert isinstance(snap, CoverageSnapshot)
        assert snap.session == 1
        assert snap.total_coverage == 95.0

    def test_saves_to_history(self, tmp_path):
        hp = tmp_path / "coverage.json"
        with patch("src.coverage_tracker.run_coverage", return_value=self._make_mock_output(90)):
            record_coverage(session=1, repo_path=tmp_path, history_path=hp)
        with patch("src.coverage_tracker.run_coverage", return_value=self._make_mock_output(95)):
            record_coverage(session=2, repo_path=tmp_path, history_path=hp)
        history = load_coverage_history(hp)
        assert len(history.snapshots) == 2

    def test_timestamp_set(self, tmp_path):
        hp = tmp_path / "coverage.json"
        with patch("src.coverage_tracker.run_coverage", return_value=self._make_mock_output()):
            snap = record_coverage(
                session=1,
                repo_path=tmp_path,
                history_path=hp,
                timestamp="2026-02-28T23:59:00Z",
            )
        assert snap.timestamp == "2026-02-28T23:59:00Z"

    def test_replaces_same_session(self, tmp_path):
        hp = tmp_path / "coverage.json"
        with patch("src.coverage_tracker.run_coverage", return_value=self._make_mock_output(80)):
            record_coverage(session=1, repo_path=tmp_path, history_path=hp)
        with patch("src.coverage_tracker.run_coverage", return_value=self._make_mock_output(95)):
            record_coverage(session=1, repo_path=tmp_path, history_path=hp)
        history = load_coverage_history(hp)
        assert len(history.snapshots) == 1
        assert history.snapshots[0].total_coverage == 95.0
