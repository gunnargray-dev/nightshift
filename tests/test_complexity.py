"""Tests for src/complexity.py — Cyclomatic Complexity Tracker."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from src.complexity import (
    FunctionComplexity,
    ModuleComplexity,
    ComplexityReport,
    ComplexitySnapshot,
    ComplexityHistory,
    analyze_complexity,
    load_complexity_history,
    save_complexity_report,
    save_complexity_history,
    render_complexity_report,
    _analyze_module,
    _rate_complexity,
    _spark_char,
)


# ---------------------------------------------------------------------------
# Fixtures — Python source with known complexity
# ---------------------------------------------------------------------------

SIMPLE_MODULE = textwrap.dedent("""\
    \"\"\"Simple module — all functions have CC=1.\"\"\"

    def add(a, b):
        return a + b

    def greet(name):
        return f"Hello, {name}"
""")

MODERATE_MODULE = textwrap.dedent("""\
    \"\"\"Module with moderate complexity.\"\"\"

    def process(items):
        result = []
        for item in items:
            if item > 0:
                result.append(item * 2)
            elif item == 0:
                result.append(0)
            else:
                result.append(-item)
        return result
""")

COMPLEX_MODULE = textwrap.dedent("""\
    \"\"\"Module with a highly complex function.\"\"\"

    def classify(value, mode, options):
        if not options:
            return None
        if mode == "strict":
            if value > 100:
                if options.get("cap"):
                    return "capped"
                elif options.get("warn"):
                    return "warned"
                else:
                    return "overflow"
            elif value > 50:
                for key in options:
                    if key.startswith("x"):
                        return "x_match"
                return "mid"
            elif value > 0:
                return "low"
        elif mode == "loose":
            try:
                result = value / options.get("divisor", 1)
                if result > 10:
                    return "high_loose"
                return "low_loose"
            except ZeroDivisionError:
                return "zero"
        return "unknown"
""")

BOOLEAN_OPS_MODULE = textwrap.dedent("""\
    def check(a, b, c, d):
        if a and b and c and d:
            return True
        return False
""")


@pytest.fixture
def simple_src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "simple.py").write_text(SIMPLE_MODULE)
    return tmp_path


@pytest.fixture
def complex_src(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "simple.py").write_text(SIMPLE_MODULE)
    (src / "moderate.py").write_text(MODERATE_MODULE)
    (src / "complex_mod.py").write_text(COMPLEX_MODULE)
    return tmp_path


@pytest.fixture
def empty_src(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# _rate_complexity
# ---------------------------------------------------------------------------

class TestRateComplexity:
    def test_simple(self):
        assert _rate_complexity(1) == "simple"
        assert _rate_complexity(5) == "simple"

    def test_moderate(self):
        assert _rate_complexity(6) == "moderate"
        assert _rate_complexity(10) == "moderate"

    def test_complex(self):
        assert _rate_complexity(11) == "complex"
        assert _rate_complexity(20) == "complex"

    def test_critical(self):
        assert _rate_complexity(21) == "critical"
        assert _rate_complexity(100) == "critical"


# ---------------------------------------------------------------------------
# _spark_char
# ---------------------------------------------------------------------------

class TestSparkChar:
    def test_min_value(self):
        c = _spark_char(0.0, 10.0)
        assert c in "▁▂▃▄▅▆▇█"

    def test_max_value(self):
        c = _spark_char(10.0, 10.0)
        assert c == "█"

    def test_zero_max(self):
        c = _spark_char(5.0, 0.0)
        assert c == "▁"

    def test_mid_value(self):
        c = _spark_char(5.0, 10.0)
        assert c in "▁▂▃▄▅▆▇█"


# ---------------------------------------------------------------------------
# _analyze_module
# ---------------------------------------------------------------------------

class TestAnalyzeModule:
    def test_simple_functions_low_complexity(self, simple_src: Path):
        path = simple_src / "src" / "simple.py"
        mc = _analyze_module("simple", path)
        assert mc is not None
        for f in mc.functions:
            assert f.complexity <= 5

    def test_complex_function_high_complexity(self, complex_src: Path):
        path = complex_src / "src" / "complex_mod.py"
        mc = _analyze_module("complex_mod", path)
        assert mc is not None
        max_cc = max(f.complexity for f in mc.functions)
        assert max_cc > 10

    def test_function_count(self, simple_src: Path):
        path = simple_src / "src" / "simple.py"
        mc = _analyze_module("simple", path)
        assert mc is not None
        assert mc.total_functions == 2

    def test_returns_none_on_syntax_error(self, tmp_path: Path):
        bad = tmp_path / "bad.py"
        bad.write_text("def broken( \n  # syntax error\n", encoding="utf-8")
        mc = _analyze_module("bad", bad)
        assert mc is None

    def test_nonexistent_returns_none(self, tmp_path: Path):
        mc = _analyze_module("ghost", tmp_path / "ghost.py")
        assert mc is None

    def test_boolean_ops_add_complexity(self, tmp_path: Path):
        path = tmp_path / "bool_ops.py"
        path.write_text(BOOLEAN_OPS_MODULE, encoding="utf-8")
        mc = _analyze_module("bool_ops", path)
        assert mc is not None
        assert mc.max_complexity >= 4

    def test_hot_spots_populated(self, complex_src: Path):
        path = complex_src / "src" / "complex_mod.py"
        mc = _analyze_module("complex_mod", path)
        assert mc is not None
        assert len(mc.hot_spots) >= 1


# ---------------------------------------------------------------------------
# FunctionComplexity
# ---------------------------------------------------------------------------

class TestFunctionComplexity:
    def test_to_dict(self):
        fc = FunctionComplexity(
            module="test",
            name="foo",
            qualname="foo",
            complexity=5,
            lineno=1,
            rating="simple",
        )
        d = fc.to_dict()
        assert d["name"] == "foo"
        assert d["complexity"] == 5


# ---------------------------------------------------------------------------
# analyze_complexity
# ---------------------------------------------------------------------------

class TestAnalyzeComplexity:
    def test_returns_report(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        assert isinstance(report, ComplexityReport)

    def test_session_number(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=7)
        assert report.session_number == 7

    def test_total_functions(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        assert report.total_functions == 2

    def test_global_avg_positive(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        assert report.global_avg > 0

    def test_global_max_correct(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        assert report.global_max >= 1

    def test_complex_module_detected(self, complex_src: Path):
        report = analyze_complexity(repo_path=complex_src, session_number=1)
        assert report.global_max > 10

    def test_hot_spots(self, complex_src: Path):
        report = analyze_complexity(repo_path=complex_src, session_number=1)
        assert len(report.hot_spots) >= 1

    def test_distribution_counts_sum_to_total(self, complex_src: Path):
        report = analyze_complexity(repo_path=complex_src, session_number=1)
        total_counted = (
            report.simple_count
            + report.moderate_count
            + report.complex_count
            + report.critical_count
        )
        assert total_counted == report.total_functions

    def test_empty_src(self, empty_src: Path):
        report = analyze_complexity(repo_path=empty_src, session_number=1)
        assert report.total_functions == 0
        assert report.global_avg == 0.0

    def test_missing_src(self, tmp_path: Path):
        report = analyze_complexity(repo_path=tmp_path, session_number=1)
        assert report.total_functions == 0


# ---------------------------------------------------------------------------
# ComplexityHistory
# ---------------------------------------------------------------------------

class TestComplexityHistory:
    def test_add_snapshot(self, simple_src: Path):
        history = ComplexityHistory()
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        history.add(report)
        assert len(history.snapshots) == 1

    def test_add_replaces_existing_session(self, simple_src: Path):
        history = ComplexityHistory()
        r1 = analyze_complexity(repo_path=simple_src, session_number=1)
        r2 = analyze_complexity(repo_path=simple_src, session_number=1)
        history.add(r1)
        history.add(r2)
        assert len(history.snapshots) == 1

    def test_add_multiple_sessions(self, simple_src: Path):
        history = ComplexityHistory()
        for i in range(1, 5):
            r = analyze_complexity(repo_path=simple_src, session_number=i)
            history.add(r)
        assert len(history.snapshots) == 4

    def test_snapshots_sorted(self, simple_src: Path):
        history = ComplexityHistory()
        for i in [3, 1, 2]:
            r = analyze_complexity(repo_path=simple_src, session_number=i)
            history.add(r)
        nums = [s.session_number for s in history.snapshots]
        assert nums == sorted(nums)

    def test_to_dict(self, simple_src: Path):
        history = ComplexityHistory()
        r = analyze_complexity(repo_path=simple_src, session_number=1)
        history.add(r)
        d = history.to_dict()
        assert "snapshots" in d

    def test_from_dict_roundtrip(self, simple_src: Path):
        history = ComplexityHistory()
        r = analyze_complexity(repo_path=simple_src, session_number=1)
        history.add(r)
        restored = ComplexityHistory.from_dict(history.to_dict())
        assert len(restored.snapshots) == 1
        assert restored.snapshots[0].session_number == 1

    def test_markdown_no_snapshots(self):
        history = ComplexityHistory()
        md = history.to_markdown()
        assert "No complexity history" in md

    def test_markdown_with_snapshots(self, simple_src: Path):
        history = ComplexityHistory()
        r = analyze_complexity(repo_path=simple_src, session_number=1)
        history.add(r)
        md = history.to_markdown()
        assert "Session" in md
        assert "|" in md


# ---------------------------------------------------------------------------
# load / save
# ---------------------------------------------------------------------------

class TestLoadSaveComplexityHistory:
    def test_load_nonexistent_returns_empty(self, tmp_path: Path):
        history = load_complexity_history(tmp_path / "nonexistent.json")
        assert history.snapshots == []

    def test_save_and_load_roundtrip(self, simple_src: Path, tmp_path: Path):
        history = ComplexityHistory()
        r = analyze_complexity(repo_path=simple_src, session_number=1)
        history.add(r)
        path = tmp_path / "history.json"
        save_complexity_history(history, path)
        loaded = load_complexity_history(path)
        assert len(loaded.snapshots) == 1
        assert loaded.snapshots[0].session_number == 1

    def test_load_corrupted_json(self, tmp_path: Path):
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{broken json", encoding="utf-8")
        history = load_complexity_history(bad_path)
        assert history.snapshots == []


class TestSaveComplexityReport:
    def test_creates_md_and_json(self, simple_src: Path, tmp_path: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        out = tmp_path / "complexity.md"
        save_complexity_report(report, out)
        assert out.exists()
        json_path = tmp_path / "complexity.json"
        assert json_path.exists()

    def test_creates_parent_dirs(self, simple_src: Path, tmp_path: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        out = tmp_path / "nested" / "complexity.md"
        save_complexity_report(report, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# render_complexity_report
# ---------------------------------------------------------------------------

class TestRenderComplexityReport:
    def test_returns_string(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        md = render_complexity_report(report)
        assert isinstance(md, str)

    def test_contains_header(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        md = render_complexity_report(report)
        assert "Cyclomatic Complexity" in md

    def test_contains_distribution(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        md = render_complexity_report(report)
        assert "Distribution" in md

    def test_contains_per_module_summary(self, simple_src: Path):
        report = analyze_complexity(repo_path=simple_src, session_number=1)
        md = render_complexity_report(report)
        assert "simple" in md

    def test_hot_spots_section_shown(self, complex_src: Path):
        report = analyze_complexity(repo_path=complex_src, session_number=1)
        md = render_complexity_report(report)
        assert "Hot Spots" in md


# ---------------------------------------------------------------------------
# Integration: real repo
# ---------------------------------------------------------------------------

class TestRealRepo:
    def test_real_src(self):
        repo = Path(__file__).resolve().parent.parent
        if not (repo / "src").exists():
            pytest.skip("src/ not found")
        report = analyze_complexity(repo_path=repo, session_number=11)
        assert report.total_functions >= 50
        assert report.global_avg >= 1.0
        md = report.to_markdown()
        assert "Cyclomatic" in md
