"""Tests for src/benchmark.py — Performance Benchmark Suite."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.benchmark import (
    BenchmarkResult,
    BenchmarkReport,
    run_benchmarks,
    save_benchmark_report,
    _load_baseline,
    _save_history,
    _time_module,
)


class TestBenchmarkResult:
    def test_basic_construction(self):
        r = BenchmarkResult(module="health", elapsed_ms=123.4, status="ok")
        assert r.module == "health"
        assert r.elapsed_ms == 123.4
        assert r.status == "ok"
        assert r.error is None
        assert r.baseline_ms is None

    def test_regression_no_baseline(self):
        r = BenchmarkResult(module="health", elapsed_ms=100.0, status="ok")
        assert r.regression is None
        assert r.regression_label == "—"

    def test_regression_positive(self):
        r = BenchmarkResult(module="health", elapsed_ms=150.0, status="ok", baseline_ms=100.0)
        assert r.regression == pytest.approx(50.0)
        assert "▲" in r.regression_label
        assert "⚠" in r.regression_label

    def test_regression_negative(self):
        r = BenchmarkResult(module="health", elapsed_ms=80.0, status="ok", baseline_ms=100.0)
        assert r.regression == pytest.approx(-20.0)
        assert "▼" in r.regression_label

    def test_regression_small(self):
        r = BenchmarkResult(module="health", elapsed_ms=105.0, status="ok", baseline_ms=100.0)
        reg = r.regression
        assert reg is not None
        assert abs(reg) < 20

    def test_regression_zero_baseline(self):
        r = BenchmarkResult(module="health", elapsed_ms=100.0, status="ok", baseline_ms=0.0)
        assert r.regression is None

    def test_to_dict_keys(self):
        r = BenchmarkResult(module="security", elapsed_ms=50.0, status="ok", baseline_ms=40.0)
        d = r.to_dict()
        assert "module" in d
        assert "elapsed_ms" in d
        assert "status" in d
        assert "regression" in d
        assert "regression_label" in d

    def test_error_result(self):
        r = BenchmarkResult(module="blame", elapsed_ms=5.0, status="error", error="git not found")
        assert r.status == "error"
        assert r.error == "git not found"


class TestBenchmarkReport:
    def _make_report(self) -> BenchmarkReport:
        results = [
            BenchmarkResult(module="health", elapsed_ms=100.0, status="ok"),
            BenchmarkResult(module="security", elapsed_ms=50.0, status="ok"),
            BenchmarkResult(module="dead_code", elapsed_ms=200.0, status="ok"),
            BenchmarkResult(module="blame", elapsed_ms=5.0, status="error", error="no git"),
        ]
        return BenchmarkReport(results=results, total_ms=355.0, session=15, timestamp="2026-02-28")

    def test_regressions_empty_when_no_baselines(self):
        report = self._make_report()
        assert report.regressions == []

    def test_regressions_detected(self):
        results = [
            BenchmarkResult(module="health", elapsed_ms=200.0, status="ok", baseline_ms=100.0),
            BenchmarkResult(module="security", elapsed_ms=50.0, status="ok", baseline_ms=100.0),
        ]
        report = BenchmarkReport(results=results, total_ms=250.0)
        assert len(report.regressions) == 1
        assert report.regressions[0].module == "health"

    def test_fastest(self):
        report = self._make_report()
        ok_results = [r for r in report.results if r.status == "ok"]
        assert report.fastest is not None
        assert report.fastest.elapsed_ms == min(r.elapsed_ms for r in ok_results)

    def test_slowest(self):
        report = self._make_report()
        ok_results = [r for r in report.results if r.status == "ok"]
        assert report.slowest is not None
        assert report.slowest.elapsed_ms == max(r.elapsed_ms for r in ok_results)

    def test_to_dict_structure(self):
        report = self._make_report()
        d = report.to_dict()
        assert "results" in d
        assert "total_ms" in d
        assert "session" in d
        assert "regressions" in d
        assert isinstance(d["results"], list)

    def test_to_json_valid(self):
        report = self._make_report()
        data = json.loads(report.to_json())
        assert data["session"] == 15
        assert len(data["results"]) == 4

    def test_to_markdown_contains_modules(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "health" in md
        assert "security" in md
        assert "dead_code" in md

    def test_to_markdown_contains_total(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "Total wall time" in md

    def test_to_markdown_regression_warning(self):
        results = [
            BenchmarkResult(module="health", elapsed_ms=250.0, status="ok", baseline_ms=100.0),
        ]
        report = BenchmarkReport(results=results, total_ms=250.0)
        md = report.to_markdown()
        assert "regression" in md.lower()

    def test_to_markdown_empty_report(self):
        report = BenchmarkReport()
        md = report.to_markdown()
        assert "Benchmark" in md

    def test_fastest_none_when_empty(self):
        report = BenchmarkReport()
        assert report.fastest is None

    def test_slowest_none_when_empty(self):
        report = BenchmarkReport()
        assert report.slowest is None


class TestTimeModule:
    def test_successful_timing(self):
        result = _time_module("test_mod", lambda: time.sleep(0.01))
        assert result.status == "ok"
        assert result.module == "test_mod"
        assert result.elapsed_ms >= 0

    def test_error_timing(self):
        def boom():
            raise RuntimeError("intentional error")
        result = _time_module("boom_mod", boom)
        assert result.status == "error"
        assert result.error is not None
        assert "intentional error" in result.error

    def test_elapsed_is_positive(self):
        result = _time_module("noop", lambda: None)
        assert result.elapsed_ms >= 0


class TestBaselinePersistence:
    def test_load_baseline_missing_file(self, tmp_path):
        baseline = _load_baseline(tmp_path / "nonexistent.json")
        assert baseline == {}

    def test_load_baseline_empty_list(self, tmp_path):
        p = tmp_path / "history.json"
        p.write_text("[]")
        baseline = _load_baseline(p)
        assert baseline == {}

    def test_load_baseline_valid(self, tmp_path):
        p = tmp_path / "history.json"
        data = [{"results": [{"module": "health", "elapsed_ms": 100.0}]}]
        p.write_text(json.dumps(data))
        baseline = _load_baseline(p)
        assert baseline["health"] == 100.0

    def test_load_baseline_invalid_json(self, tmp_path):
        p = tmp_path / "history.json"
        p.write_text("not json!!!")
        baseline = _load_baseline(p)
        assert baseline == {}

    def test_save_history_creates_file(self, tmp_path):
        p = tmp_path / "history.json"
        report = BenchmarkReport(
            results=[BenchmarkResult(module="health", elapsed_ms=100.0, status="ok")],
            total_ms=100.0, session=15,
        )
        _save_history(report, p)
        assert p.exists()
        data = json.loads(p.read_text())
        assert isinstance(data, list)
        assert len(data) == 1

    def test_save_history_appends(self, tmp_path):
        p = tmp_path / "history.json"
        r1 = BenchmarkReport(results=[], total_ms=0.0, session=1)
        r2 = BenchmarkReport(results=[], total_ms=0.0, session=2)
        _save_history(r1, p)
        _save_history(r2, p)
        data = json.loads(p.read_text())
        assert len(data) == 2

    def test_save_history_caps_at_20(self, tmp_path):
        p = tmp_path / "history.json"
        for i in range(25):
            r = BenchmarkReport(results=[], total_ms=0.0, session=i)
            _save_history(r, p)
        data = json.loads(p.read_text())
        assert len(data) <= 20


class TestRunBenchmarks:
    def test_returns_report(self, tmp_path):
        report = run_benchmarks(repo_path=tmp_path, session=15, persist=False)
        assert isinstance(report, BenchmarkReport)
        assert report.session == 15

    def test_total_ms_nonnegative(self, tmp_path):
        report = run_benchmarks(repo_path=tmp_path, session=15, persist=False)
        assert report.total_ms >= 0

    def test_persist_creates_history(self, tmp_path):
        (tmp_path / "docs").mkdir(exist_ok=True)
        run_benchmarks(repo_path=tmp_path, session=15, persist=True)
        assert (tmp_path / "docs" / "benchmark_history.json").exists()

    def test_no_persist_skips_file(self, tmp_path):
        run_benchmarks(repo_path=tmp_path, session=15, persist=False)
        assert not (tmp_path / "docs" / "benchmark_history.json").exists()


class TestSaveBenchmarkReport:
    def test_creates_md_and_json(self, tmp_path):
        report = BenchmarkReport(
            results=[BenchmarkResult(module="health", elapsed_ms=100.0, status="ok")],
            total_ms=100.0,
        )
        out = tmp_path / "benchmark_report.md"
        save_benchmark_report(report, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_markdown_content(self, tmp_path):
        report = BenchmarkReport(
            results=[BenchmarkResult(module="health", elapsed_ms=42.0, status="ok")],
            total_ms=42.0,
        )
        out = tmp_path / "benchmark_report.md"
        save_benchmark_report(report, out)
        text = out.read_text()
        assert "health" in text
        assert "42" in text

    def test_json_valid(self, tmp_path):
        report = BenchmarkReport(results=[], total_ms=0.0, session=15)
        out = tmp_path / "benchmark_report.md"
        save_benchmark_report(report, out)
        data = json.loads(out.with_suffix(".json").read_text())
        assert data["session"] == 15
