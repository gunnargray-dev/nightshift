"""Tests for src/doctor.py — 37 tests."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.doctor import (
    Check,
    DiagnosticReport,
    diagnose,
    render_report,
    save_report,
    STATUS_OK, STATUS_WARN, STATUS_FAIL,
    _check_src_exists,
    _check_tests_exist,
    _check_test_coverage,
    _check_syntax,
    _check_ci_workflow,
    _check_readme,
    _check_roadmap,
    _check_todos,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def healthy_repo(tmp_path) -> Path:
    """A minimal but complete repo structure that should pass most checks."""
    src = tmp_path / "src"
    src.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    ci = tmp_path / ".github" / "workflows"
    ci.mkdir(parents=True)

    (src / "__init__.py").write_text("__version__ = '0.1.0'\n")
    (src / "health.py").write_text(
        "from __future__ import annotations\n\ndef analyze(path):\n    \"\"\"Analyze.\"\"\"\n    return {}\n"
    )
    (tests / "test_health.py").write_text("def test_placeholder(): pass\n")
    (ci / "ci.yml").write_text(
        "jobs:\n  test:\n    strategy:\n      matrix:\n        python-version: ['3.10', '3.11', '3.12']\n"
    )
    (tmp_path / "README.md").write_text("# Nightshift\n\nA self-improving system.\n" * 10)
    (tmp_path / "ROADMAP.md").write_text("## Backlog\n\n- [ ] Item 1\n- [ ] Item 2\n")
    (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
        "# Nightshift Log\n\n## Session 1 — Feb 2026\n**Operator:** Computer\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'nightshift'\nrequires-python = '>=3.10'\n"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Check dataclass
# ---------------------------------------------------------------------------

class TestCheck:
    def test_ok_icon(self):
        c = Check(STATUS_OK, "test", "all good")
        assert c.icon == "✅"

    def test_warn_icon(self):
        c = Check(STATUS_WARN, "test", "watch out")
        assert c.icon == "⚠️"

    def test_fail_icon(self):
        c = Check(STATUS_FAIL, "test", "broken")
        assert c.icon == "❌"

    def test_to_dict_has_all_keys(self):
        c = Check(STATUS_OK, "syntax check", "all good", "no errors")
        d = c.to_dict()
        assert "name" in d
        assert "status" in d
        assert "message" in d
        assert "detail" in d


# ---------------------------------------------------------------------------
# DiagnosticReport
# ---------------------------------------------------------------------------

class TestDiagnosticReport:
    @pytest.fixture
    def report(self):
        return DiagnosticReport(checks=[
            Check(STATUS_OK, "a", "ok"),
            Check(STATUS_WARN, "b", "warn"),
            Check(STATUS_FAIL, "c", "fail"),
        ])

    def test_ok_count(self, report):
        assert report.ok_count == 1

    def test_warn_count(self, report):
        assert report.warn_count == 1

    def test_fail_count(self, report):
        assert report.fail_count == 1

    def test_grade_all_ok(self):
        r = DiagnosticReport(checks=[Check(STATUS_OK, "a", "ok")] * 5)
        assert r.grade == "A"

    def test_grade_all_fail(self):
        r = DiagnosticReport(checks=[Check(STATUS_FAIL, "a", "fail")] * 5)
        assert r.grade == "F"

    def test_grade_empty(self):
        r = DiagnosticReport(checks=[])
        assert r.grade == "N/A"

    def test_to_dict_has_keys(self, report):
        d = report.to_dict()
        assert "grade" in d
        assert "ok_count" in d
        assert "warn_count" in d
        assert "fail_count" in d
        assert "checks" in d


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

class TestIndividualChecks:
    def test_src_exists_ok(self, healthy_repo):
        c = _check_src_exists(healthy_repo)
        assert c.status == STATUS_OK

    def test_src_missing_fails(self, tmp_path):
        c = _check_src_exists(tmp_path)
        assert c.status == STATUS_FAIL

    def test_tests_exist_ok(self, healthy_repo):
        c = _check_tests_exist(healthy_repo)
        assert c.status == STATUS_OK

    def test_tests_missing_fails(self, tmp_path):
        (tmp_path / "src").mkdir()
        c = _check_tests_exist(tmp_path)
        assert c.status == STATUS_FAIL

    def test_test_coverage_ok(self, healthy_repo):
        c = _check_test_coverage(healthy_repo)
        assert c.status == STATUS_OK

    def test_test_coverage_warn_when_missing(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        tests = tmp_path / "tests"
        tests.mkdir()
        (src / "orphan.py").write_text("def f(): pass\n")
        # No matching test_orphan.py
        c = _check_test_coverage(tmp_path)
        assert c.status in (STATUS_WARN, STATUS_FAIL)

    def test_syntax_ok(self, healthy_repo):
        c = _check_syntax(healthy_repo)
        assert c.status == STATUS_OK

    def test_syntax_fails_on_bad_code(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "broken.py").write_text("def f(:\n    pass\n")
        c = _check_syntax(tmp_path)
        assert c.status == STATUS_FAIL

    def test_ci_workflow_ok(self, healthy_repo):
        c = _check_ci_workflow(healthy_repo)
        assert c.status == STATUS_OK

    def test_ci_workflow_missing(self, tmp_path):
        c = _check_ci_workflow(tmp_path)
        assert c.status == STATUS_FAIL

    def test_readme_ok(self, healthy_repo):
        c = _check_readme(healthy_repo)
        assert c.status == STATUS_OK

    def test_readme_missing(self, tmp_path):
        c = _check_readme(tmp_path)
        assert c.status == STATUS_FAIL

    def test_roadmap_ok(self, healthy_repo):
        c = _check_roadmap(healthy_repo)
        assert c.status == STATUS_OK

    def test_todos_clean(self, healthy_repo):
        c = _check_todos(healthy_repo)
        assert c.status == STATUS_OK

    def test_todos_warns_when_found(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "messy.py").write_text("# TODO: fix this\n# FIXME: broken\ndef f(): pass\n")
        c = _check_todos(tmp_path)
        assert c.status in (STATUS_WARN, STATUS_FAIL)


# ---------------------------------------------------------------------------
# diagnose() and render_report()
# ---------------------------------------------------------------------------

class TestDiagnose:
    def test_returns_report(self, healthy_repo):
        report = diagnose(healthy_repo)
        assert isinstance(report, DiagnosticReport)

    def test_has_checks(self, healthy_repo):
        report = diagnose(healthy_repo)
        assert len(report.checks) > 0

    def test_healthy_repo_gets_good_grade(self, healthy_repo):
        report = diagnose(healthy_repo)
        assert report.grade in ("A", "B", "C")


class TestRenderReport:
    def test_returns_string(self, healthy_repo):
        report = diagnose(healthy_repo)
        result = render_report(report)
        assert isinstance(result, str)

    def test_has_title(self, healthy_repo):
        report = diagnose(healthy_repo)
        result = render_report(report)
        assert "# Nightshift Doctor Report" in result

    def test_has_grade(self, healthy_repo):
        report = diagnose(healthy_repo)
        result = render_report(report)
        assert "Overall Grade" in result

    def test_has_summary_table(self, healthy_repo):
        report = diagnose(healthy_repo)
        result = render_report(report)
        assert "Passing" in result
        assert "Warnings" in result

    def test_has_check_results(self, healthy_repo):
        report = diagnose(healthy_repo)
        result = render_report(report)
        assert "## Check Results" in result


# ---------------------------------------------------------------------------
# save_report()
# ---------------------------------------------------------------------------

class TestSaveReport:
    def test_creates_markdown_file(self, healthy_repo, tmp_path):
        report = diagnose(healthy_repo)
        out = tmp_path / "doctor.md"
        save_report(report, out)
        assert out.exists()
        assert "Nightshift Doctor" in out.read_text()

    def test_creates_json_sidecar(self, healthy_repo, tmp_path):
        report = diagnose(healthy_repo)
        out = tmp_path / "doctor.md"
        save_report(report, out)
        json_file = tmp_path / "doctor.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert "grade" in data

    def test_creates_parent_dirs(self, healthy_repo, tmp_path):
        report = diagnose(healthy_repo)
        out = tmp_path / "x" / "y" / "doctor.md"
        save_report(report, out)
        assert out.exists()
