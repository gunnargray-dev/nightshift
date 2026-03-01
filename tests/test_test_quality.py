"""Tests for src/test_quality.py — Test quality analyzer."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.test_quality import (
    TestFileScore,
    TestQualityReport,
    analyze_test_quality,
    _score_test_file,
    _grade,
    _TestFileVisitor,
)
import ast


# ---------------------------------------------------------------------------
# _grade
# ---------------------------------------------------------------------------


def test_grade_bounds():
    assert _grade(100) == "A+"
    assert _grade(90) == "A"
    assert _grade(80) == "B+"
    assert _grade(70) == "B-"
    assert _grade(60) == "C"
    assert _grade(50) == "D+"
    assert _grade(40) == "D-"
    assert _grade(30) == "F"
    assert _grade(0) == "F"


# ---------------------------------------------------------------------------
# _TestFileVisitor
# ---------------------------------------------------------------------------


def _visit(source: str) -> "_TestFileVisitor":
    tree = ast.parse(source)
    v = _TestFileVisitor()
    v.visit(tree)
    return v


def test_visitor_counts_test_functions():
    source = """
def test_a():
    assert 1 == 1

def test_b():
    assert 2 == 2

def helper():
    pass
"""
    v = _visit(source)
    assert v.test_count == 2


def test_visitor_counts_assert_statements():
    source = """
def test_foo():
    assert x == 1
    assert y is not None
"""
    v = _visit(source)
    assert v.assertion_count == 2


def test_visitor_counts_unittest_asserts():
    source = """
class TestFoo:
    def test_bar(self):
        self.assertEqual(1, 1)
        self.assertIsNone(None)
        self.assertTrue(True)
"""
    v = _visit(source)
    assert v.assertion_count >= 3


def test_visitor_detects_parametrize():
    source = """
import pytest

@pytest.mark.parametrize("x", [1, 2, 3])
def test_values(x):
    assert x > 0
"""
    v = _visit(source)
    assert v.parametrize_count >= 1


def test_visitor_detects_mock_import():
    source = """
from unittest.mock import MagicMock, patch

def test_mocked():
    m = MagicMock()
    assert m is not None
"""
    v = _visit(source)
    assert v._has_mock_import is True


def test_visitor_counts_pytest_raises():
    source = """
import pytest

def test_exception():
    with pytest.raises(ValueError):
        raise ValueError("bad")
"""
    v = _visit(source)
    assert v.assertion_count >= 1


def test_visitor_detects_edge_cases():
    source = """
def test_empty_input():
    assert process("") is None

def test_none_value():
    assert process(None) == 0

def test_negative_number():
    assert process(-1) == -1
"""
    v = _visit(source)
    assert v.test_count == 3
    assert v.edge_case_markers >= 2


# ---------------------------------------------------------------------------
# _score_test_file
# ---------------------------------------------------------------------------


def test_score_test_file_good(tmp_path):
    test_file = tmp_path / "test_health.py"
    test_file.write_text("""
import pytest

@pytest.mark.parametrize("score", [0, 50, 100])
def test_health_score_range(score):
    \"\"\"Test health score is within valid range.\"\"\"
    assert 0 <= score <= 100

def test_health_empty_input():
    with pytest.raises(ValueError):
        pass

def test_health_none_raises():
    assert True

def test_health_negative_score():
    assert -1 < 0

def test_health_large_file():
    assert True

def test_health_unicode_name():
    assert True

def test_health_boundary_value():
    assert True
""")
    score = _score_test_file(test_file, "health")
    assert score.score >= 60
    assert score.test_count >= 5


def test_score_test_file_empty(tmp_path):
    test_file = tmp_path / "test_empty.py"
    test_file.write_text("# No tests here\n")
    score = _score_test_file(test_file, "empty")
    assert score.test_count == 0
    assert "no tests defined" in score.issues


def test_score_test_file_no_assertions(tmp_path):
    test_file = tmp_path / "test_no_asserts.py"
    test_file.write_text("""
def test_something():
    x = 1 + 1
""")
    score = _score_test_file(test_file, "no_asserts")
    assert "no assertions" in score.issues
    assert score.assertion_density == 0.0


def test_score_test_file_high_assertion_density(tmp_path):
    test_file = tmp_path / "test_dense.py"
    test_file.write_text("""
def test_dense():
    assert 1 == 1
    assert 2 == 2
    assert 3 == 3
    assert 4 == 4
    assert 5 == 5
""")
    score = _score_test_file(test_file, "dense")
    assert score.assertion_density == 5.0
    assert score.score >= 50  # decent density, but only 1 test and no edge cases


def test_score_test_file_invalid_syntax(tmp_path):
    test_file = tmp_path / "test_bad.py"
    test_file.write_text("def broken(:\n    pass\n")
    score = _score_test_file(test_file, "bad")
    assert "could not parse" in score.issues


# ---------------------------------------------------------------------------
# TestFileScore
# ---------------------------------------------------------------------------


def test_test_file_score_to_dict():
    fs = TestFileScore(
        file="test_health.py",
        module="health",
        score=82.5,
        grade="B+",
        test_count=10,
        assertion_count=25,
    )
    d = fs.to_dict()
    assert d["file"] == "test_health.py"
    assert d["score"] == 82.5
    assert d["test_count"] == 10


# ---------------------------------------------------------------------------
# analyze_test_quality
# ---------------------------------------------------------------------------


def test_analyze_test_quality_no_tests_dir(tmp_path):
    report = analyze_test_quality(tmp_path)
    assert isinstance(report, TestQualityReport)
    assert report.total_test_files == 0


def test_analyze_test_quality_with_tests(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "health.py").write_text("def run(): pass\n")
    (src / "stats.py").write_text("def compute(): pass\n")
    (src / "config.py").write_text("def load(): pass\n")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_health.py").write_text("""
def test_run():
    assert True

def test_edge_empty():
    assert True
""")
    (tests / "test_stats.py").write_text("""
import pytest

@pytest.mark.parametrize("n", [1, 2, 3])
def test_compute(n):
    assert n > 0

def test_none_input():
    assert True
""")

    report = analyze_test_quality(tmp_path)
    assert report.total_test_files == 2
    assert report.total_tests >= 4
    assert "config" in report.missing_test_files


def test_analyze_test_quality_to_markdown(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text("""
def test_a():
    assert 1 == 1
""")
    report = analyze_test_quality(tmp_path)
    md = report.to_markdown()
    assert "Test Quality Analysis" in md
    assert "test_sample.py" in md


def test_analyze_test_quality_avg_score(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    for i in range(3):
        content = f"""
def test_{i}_a():
    assert True

def test_{i}_b():
    assert True
"""
        (tests / f"test_mod{i}.py").write_text(content)

    report = analyze_test_quality(tmp_path)
    assert report.avg_score >= 0
    assert 0 <= report.avg_score <= 100


def test_analyze_test_quality_identifies_weak_files(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_weak.py").write_text("# empty\n")
    report = analyze_test_quality(tmp_path)
    weak = [f.file for f in report.files if "no tests defined" in f.issues]
    assert "test_weak.py" in weak


def test_report_to_dict():
    report = TestQualityReport(
        repo_path="/repo",
        total_test_files=5,
        total_tests=50,
        avg_score=78.0,
        overall_grade="B",
    )
    d = report.to_dict()
    assert d["total_test_files"] == 5
    assert d["avg_score"] == 78.0
