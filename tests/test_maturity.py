"""Tests for src/maturity.py — Module Maturity Scorer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.maturity import (
    ModuleMaturity,
    MaturityReport,
    score_module_maturity,
    assess_maturity,
    save_maturity_report,
    _score_tests,
    _score_docs,
    _score_complexity,
    _score_age,
    _score_coupling,
    _count_tests_in_file,
    _analyze_src_file,
    _estimate_session_age,
    _estimate_instability,
    _has_module_docstring,
    _score_to_tier,
    _stars,
    TIER_SEED,
    TIER_SPROUT,
    TIER_GROWING,
    TIER_MATURE,
    TIER_VETERAN,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_SRC = '''\
"""A simple module for testing.

Does helpful things.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MyReport:
    """A report dataclass."""
    score: float = 0.0

    def to_dict(self):
        """Convert to dict."""
        return {"score": self.score}


def analyze(path):
    """Analyze something.

    Args:
        path: The path.
    """
    return MyReport(score=100.0)


def save_report(report, output_path):
    """Save the report."""
    output_path.write_text(str(report.score))
'''

SAMPLE_TEST = '''\
"""Tests for the sample module."""
import pytest

def test_analyze_returns_report():
    assert True

def test_analyze_score_range():
    assert True

def test_save_report_creates_file():
    assert True

def test_report_to_dict():
    assert True

def test_report_score_default():
    assert True

def not_a_test():
    pass
'''

SAMPLE_LOG = """\
# Nightshift Log

---

## Session 1 — February 27, 2026

- src/sample.py introduced

---

## Session 2 — February 27, 2026

- src/other.py introduced

---

## Session 3 — February 28, 2026

Nothing new.

---
"""


@pytest.fixture()
def src_dir(tmp_path: Path) -> Path:
    d = tmp_path / "src"
    d.mkdir()
    (d / "__init__.py").write_text("")
    (d / "sample.py").write_text(SAMPLE_SRC)
    return d


@pytest.fixture()
def tests_dir(tmp_path: Path) -> Path:
    d = tmp_path / "tests"
    d.mkdir()
    (d / "test_sample.py").write_text(SAMPLE_TEST)
    return d


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "NIGHTSHIFT_LOG.md"
    p.write_text(SAMPLE_LOG)
    return p


@pytest.fixture()
def repo(tmp_path: Path, src_dir: Path, tests_dir: Path, log_file: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# _score_to_tier
# ---------------------------------------------------------------------------


def test_tier_veteran():
    assert _score_to_tier(85) == TIER_VETERAN


def test_tier_mature():
    assert _score_to_tier(65) == TIER_MATURE


def test_tier_growing():
    assert _score_to_tier(50) == TIER_GROWING


def test_tier_sprout():
    assert _score_to_tier(25) == TIER_SPROUT


def test_tier_seed():
    assert _score_to_tier(10) == TIER_SEED


def test_tier_boundary_80():
    assert _score_to_tier(80) == TIER_VETERAN


def test_tier_boundary_60():
    assert _score_to_tier(60) == TIER_MATURE


def test_tier_boundary_40():
    assert _score_to_tier(40) == TIER_GROWING


def test_tier_boundary_20():
    assert _score_to_tier(20) == TIER_SPROUT


def test_tier_boundary_0():
    assert _score_to_tier(0) == TIER_SEED


# ---------------------------------------------------------------------------
# _stars
# ---------------------------------------------------------------------------


def test_stars_full():
    assert _stars(25, 25) == "★★★★★"


def test_stars_empty():
    assert _stars(0, 25) == "☆☆☆☆☆"


def test_stars_half():
    result = _stars(12.5, 25)
    assert "★" in result and "☆" in result


def test_stars_3_out_of_5():
    result = _stars(15, 25)
    assert result.count("★") == 3


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------


def test_score_tests_no_file():
    assert _score_tests(0, False) == 0.0


def test_score_tests_file_empty():
    score = _score_tests(0, True)
    assert score == 2.0


def test_score_tests_35_tests():
    score = _score_tests(35, True)
    assert score == 25.0


def test_score_tests_partial():
    score = _score_tests(17, True)
    assert 0 < score < 25.0


def test_score_tests_over_target():
    # Over target should still max at 25
    score = _score_tests(100, True)
    assert score == 25.0


def test_score_docs_full_coverage():
    score = _score_docs(5, 1.0, True)
    assert score == 25.0


def test_score_docs_zero_coverage_no_docstring():
    score = _score_docs(5, 0.0, False)
    assert score == 0.0


def test_score_docs_module_docstring_bonus():
    score_with = _score_docs(5, 0.8, True)
    score_without = _score_docs(5, 0.8, False)
    assert score_with > score_without


def test_score_complexity_low():
    assert _score_complexity(1.0) == 20.0


def test_score_complexity_high():
    assert _score_complexity(15.0) < 5.0


def test_score_complexity_very_high():
    assert _score_complexity(30.0) == 0.0


def test_score_complexity_moderate():
    score = _score_complexity(5.0)
    assert 0 < score < 20.0


def test_score_age_zero():
    assert _score_age(0, 13) == 0.0


def test_score_age_full():
    assert _score_age(13, 13) == 15.0


def test_score_age_half():
    score = _score_age(6, 12)
    assert score == pytest.approx(7.5, abs=0.5)


def test_score_age_zero_max_sessions():
    score = _score_age(5, 0)
    assert 0 <= score <= 15.0


def test_score_coupling_stable():
    assert _score_coupling(0.0) == 15.0


def test_score_coupling_unstable():
    assert _score_coupling(1.0) == 0.0


def test_score_coupling_neutral():
    assert _score_coupling(0.5) == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# _count_tests_in_file
# ---------------------------------------------------------------------------


def test_count_tests_correct(tmp_path: Path):
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(SAMPLE_TEST)
    count = _count_tests_in_file(test_file)
    assert count == 5  # 5 test_ functions


def test_count_tests_empty_file(tmp_path: Path):
    f = tmp_path / "test_empty.py"
    f.write_text("")
    assert _count_tests_in_file(f) == 0


def test_count_tests_nonexistent(tmp_path: Path):
    f = tmp_path / "nonexistent.py"
    assert _count_tests_in_file(f) == 0


def test_count_tests_invalid_syntax(tmp_path: Path):
    f = tmp_path / "test_bad.py"
    f.write_text("def test_broken(: pass")
    assert _count_tests_in_file(f) == 0


# ---------------------------------------------------------------------------
# _analyze_src_file
# ---------------------------------------------------------------------------


def test_analyze_src_file_counts(tmp_path: Path):
    src = tmp_path / "sample.py"
    src.write_text(SAMPLE_SRC)
    pub_funcs, doc_cov, avg_cc = _analyze_src_file(src)
    assert pub_funcs >= 2
    assert 0.0 <= doc_cov <= 1.0
    assert avg_cc >= 1.0


def test_analyze_src_file_high_docstring_coverage(tmp_path: Path):
    src = tmp_path / "sample.py"
    src.write_text(SAMPLE_SRC)
    _, doc_cov, _ = _analyze_src_file(src)
    assert doc_cov >= 0.5  # both public functions have docstrings


def test_analyze_src_file_bad_syntax(tmp_path: Path):
    src = tmp_path / "bad.py"
    src.write_text("def broken(: pass")
    pub_funcs, doc_cov, avg_cc = _analyze_src_file(src)
    assert pub_funcs == 0


def test_analyze_src_file_empty(tmp_path: Path):
    src = tmp_path / "empty.py"
    src.write_text("")
    pub_funcs, doc_cov, avg_cc = _analyze_src_file(src)
    assert pub_funcs == 0


# ---------------------------------------------------------------------------
# _has_module_docstring
# ---------------------------------------------------------------------------


def test_has_module_docstring_yes(tmp_path: Path):
    src = tmp_path / "sample.py"
    src.write_text(SAMPLE_SRC)
    assert _has_module_docstring(src) is True


def test_has_module_docstring_no(tmp_path: Path):
    src = tmp_path / "nodoc.py"
    src.write_text("x = 1\n")
    assert _has_module_docstring(src) is False


def test_has_module_docstring_bad_syntax(tmp_path: Path):
    src = tmp_path / "bad.py"
    src.write_text("def broken(: pass")
    assert _has_module_docstring(src) is False


# ---------------------------------------------------------------------------
# _estimate_session_age
# ---------------------------------------------------------------------------


def test_estimate_session_age_found(tmp_path: Path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    log.write_text(SAMPLE_LOG)
    # 'sample' is mentioned in session 1, last session is 3 → age = 3
    age = _estimate_session_age("sample", log)
    assert age >= 1


def test_estimate_session_age_no_log(tmp_path: Path):
    fake = tmp_path / "missing.md"
    assert _estimate_session_age("sample", fake) == 0


def test_estimate_session_age_not_found(tmp_path: Path):
    log = tmp_path / "NIGHTSHIFT_LOG.md"
    log.write_text(SAMPLE_LOG)
    age = _estimate_session_age("nonexistent_module_xyz", log)
    assert age >= 0


# ---------------------------------------------------------------------------
# _estimate_instability
# ---------------------------------------------------------------------------


def test_estimate_instability_no_imports(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "standalone.py").write_text("x = 1\n")
    instability = _estimate_instability("standalone", d)
    assert 0.0 <= instability <= 1.0


def test_estimate_instability_range(src_dir: Path):
    instability = _estimate_instability("sample", src_dir)
    assert 0.0 <= instability <= 1.0


# ---------------------------------------------------------------------------
# score_module_maturity
# ---------------------------------------------------------------------------


def test_score_module_maturity_returns_object(repo: Path):
    m = score_module_maturity(
        "sample",
        repo / "src",
        repo / "tests",
        repo / "NIGHTSHIFT_LOG.md",
        max_sessions=3,
    )
    assert isinstance(m, ModuleMaturity)
    assert m.name == "sample"


def test_score_module_maturity_total_score_range(repo: Path):
    m = score_module_maturity(
        "sample",
        repo / "src",
        repo / "tests",
        repo / "NIGHTSHIFT_LOG.md",
    )
    assert 0.0 <= m.total_score <= 100.0


def test_score_module_maturity_has_test_file(repo: Path):
    m = score_module_maturity(
        "sample",
        repo / "src",
        repo / "tests",
        repo / "NIGHTSHIFT_LOG.md",
    )
    assert m.test_path is not None
    assert m.test_count == 5


def test_score_module_maturity_no_test_file(repo: Path):
    m = score_module_maturity(
        "sample",
        repo / "src",
        repo / "tests" / "nonexistent",
        repo / "NIGHTSHIFT_LOG.md",
    )
    assert m.test_score == 0.0
    assert m.test_path is None


def test_score_module_maturity_tier_attribute(repo: Path):
    m = score_module_maturity(
        "sample",
        repo / "src",
        repo / "tests",
        repo / "NIGHTSHIFT_LOG.md",
    )
    assert m.tier in (TIER_SEED, TIER_SPROUT, TIER_GROWING, TIER_MATURE, TIER_VETERAN)


def test_score_module_maturity_dimension_scores_non_negative(repo: Path):
    m = score_module_maturity(
        "sample",
        repo / "src",
        repo / "tests",
        repo / "NIGHTSHIFT_LOG.md",
    )
    assert m.test_score >= 0
    assert m.docs_score >= 0
    assert m.complexity_score >= 0
    assert m.age_score >= 0
    assert m.coupling_score >= 0


# ---------------------------------------------------------------------------
# ModuleMaturity
# ---------------------------------------------------------------------------


def test_module_maturity_summary_row():
    m = ModuleMaturity(
        name="sample",
        src_path="src/sample.py",
        test_path="tests/test_sample.py",
        test_score=20.0,
        docs_score=22.0,
        complexity_score=15.0,
        age_score=10.0,
        coupling_score=12.0,
        test_count=35,
        public_functions=5,
        docstring_coverage=0.9,
    )
    row = m.summary_row()
    assert "sample" in row
    assert "★" in row


def test_module_maturity_total_score():
    m = ModuleMaturity(
        name="x",
        src_path="src/x.py",
        test_path=None,
        test_score=10.0,
        docs_score=10.0,
        complexity_score=10.0,
        age_score=5.0,
        coupling_score=5.0,
    )
    assert m.total_score == 40.0


def test_module_maturity_to_dict():
    m = ModuleMaturity(
        name="sample",
        src_path="src/sample.py",
        test_path="tests/test_sample.py",
    )
    d = m.to_dict()
    assert "name" in d
    assert "total_score" in d
    assert "tier" in d


# ---------------------------------------------------------------------------
# assess_maturity
# ---------------------------------------------------------------------------


def test_assess_maturity_returns_report(repo: Path):
    report = assess_maturity(repo)
    assert isinstance(report, MaturityReport)


def test_assess_maturity_module_count(repo: Path):
    report = assess_maturity(repo)
    # Should include 'sample' (non-underscore)
    names = [m.name for m in report.modules]
    assert "sample" in names


def test_assess_maturity_avg_score_range(repo: Path):
    report = assess_maturity(repo)
    if report.modules:
        assert 0.0 <= report.avg_score <= 100.0


def test_assess_maturity_no_src(tmp_path: Path):
    # Repo without src/ should not crash
    report = assess_maturity(tmp_path)
    assert report.modules == []


def test_assess_maturity_skips_init(repo: Path):
    names = [m.name for m in assess_maturity(repo).modules]
    assert "__init__" not in names


# ---------------------------------------------------------------------------
# MaturityReport
# ---------------------------------------------------------------------------


def test_maturity_report_to_markdown(repo: Path):
    report = assess_maturity(repo)
    md = report.to_markdown()
    assert "# Module Maturity Report" in md
    assert "VETERAN" in md or "MATURE" in md or "GROWING" in md or "SPROUT" in md or "SEED" in md


def test_maturity_report_markdown_has_table(repo: Path):
    report = assess_maturity(repo)
    md = report.to_markdown()
    assert "| Module |" in md


def test_maturity_report_to_json(repo: Path):
    report = assess_maturity(repo)
    data = json.loads(report.to_json())
    assert "modules" in data
    assert "avg_score" in data


def test_maturity_report_veterans_and_seeds(repo: Path):
    report = assess_maturity(repo)
    # These should be lists (may be empty)
    assert isinstance(report.veterans, list)
    assert isinstance(report.seeds, list)


# ---------------------------------------------------------------------------
# save_maturity_report
# ---------------------------------------------------------------------------


def test_save_maturity_report_writes_md(tmp_path: Path, repo: Path):
    report = assess_maturity(repo)
    out = tmp_path / "docs" / "maturity.md"
    save_maturity_report(report, out)
    assert out.exists()
    assert "Maturity" in out.read_text()


def test_save_maturity_report_writes_json(tmp_path: Path, repo: Path):
    report = assess_maturity(repo)
    out = tmp_path / "docs" / "maturity.md"
    save_maturity_report(report, out)
    json_out = out.with_suffix(".json")
    assert json_out.exists()
    json.loads(json_out.read_text())


def test_save_maturity_creates_parent(tmp_path: Path, repo: Path):
    report = assess_maturity(repo)
    out = tmp_path / "new" / "nested" / "maturity.md"
    save_maturity_report(report, out)
    assert out.exists()
