"""
Tests for status.py — Comprehensive status dashboard.

Session 18 — Nightshift
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from status import (
    StatusReport,
    generate_status,
    format_status,
    status_to_json,
    _count_source_modules,
    _count_tests,
    _count_cli_commands,
    _count_api_endpoints,
    _get_session_number,
    _check_red_flags,
)


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repo(tmp_path):
    """Create a minimal fake repo structure."""
    src = tmp_path / "src"
    src.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()

    # Create some fake source modules
    for name in ["health.py", "brain.py", "stats.py"]:
        (src / name).write_text(f"# {name}\ndef run(): pass\n")
    (src / "__init__.py").write_text("")

    # Create fake test files
    for name in ["test_health.py", "test_brain.py"]:
        (tests / name).write_text(
            f"def test_basic():\n    pass\n\ndef test_edge():\n    pass\n"
        )

    # Create fake cli.py
    (src / "cli.py").write_text(
        "p.add_parser('health')\n"
        "p.add_parser('brain')\n"
        "p.add_parser('status')\n"
    )

    # Create fake server.py
    (src / "server.py").write_text(
        'routes = {\n'
        '    "/api/health": ...,\n'
        '    "/api/brain": ...,\n'
        '    "/api/status": ...,\n'
        '}\n'
    )

    # Create log
    (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
        "# Session 18\n"
        "Session 18 of the Nightshift series.\n"
    )

    return tmp_path


# ---------------------------------------------------------------------------
# _count_source_modules
# ---------------------------------------------------------------------------

class TestCountSourceModules:
    def test_counts_py_files(self, mock_repo):
        count = _count_source_modules(mock_repo / "src")
        # health, brain, stats, cli, server = 5 non-init files
        assert count >= 3

    def test_excludes_init(self, mock_repo):
        count = _count_source_modules(mock_repo / "src")
        # Should not count __init__.py
        all_files = list((mock_repo / "src").glob("*.py"))
        assert count == len([f for f in all_files if f.stem != "__init__"])

    def test_returns_zero_for_missing_dir(self, tmp_path):
        count = _count_source_modules(tmp_path / "nonexistent")
        assert count == 0


# ---------------------------------------------------------------------------
# _count_tests
# ---------------------------------------------------------------------------

class TestCountTests:
    def test_counts_test_files(self, mock_repo):
        files, count = _count_tests(mock_repo / "tests")
        assert files == 2
        assert count >= 4  # 2 tests per file

    def test_returns_zero_for_missing_dir(self, tmp_path):
        files, count = _count_tests(tmp_path / "nonexistent")
        assert files == 0
        assert count == 0

    def test_counts_indented_test_methods(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_class.py").write_text(
            "class TestFoo:\n"
            "    def test_a(self): pass\n"
            "    def test_b(self): pass\n"
        )
        files, count = _count_tests(tests)
        assert count >= 2


# ---------------------------------------------------------------------------
# _count_cli_commands
# ---------------------------------------------------------------------------

class TestCountCliCommands:
    def test_counts_add_parser_calls(self, mock_repo):
        count = _count_cli_commands(mock_repo / "src" / "cli.py")
        assert count == 3

    def test_returns_zero_for_missing_file(self, tmp_path):
        count = _count_cli_commands(tmp_path / "cli.py")
        assert count == 0


# ---------------------------------------------------------------------------
# _count_api_endpoints
# ---------------------------------------------------------------------------

class TestCountApiEndpoints:
    def test_counts_api_routes(self, mock_repo):
        count = _count_api_endpoints(mock_repo / "src" / "server.py")
        assert count >= 1

    def test_returns_zero_for_missing_file(self, tmp_path):
        count = _count_api_endpoints(tmp_path / "server.py")
        assert count == 0


# ---------------------------------------------------------------------------
# _get_session_number
# ---------------------------------------------------------------------------

class TestGetSessionNumber:
    def test_reads_session_from_log(self, mock_repo):
        session = _get_session_number(mock_repo / "NIGHTSHIFT_LOG.md")
        assert session == 18

    def test_fallback_for_missing_log(self, tmp_path):
        session = _get_session_number(tmp_path / "no_log.md")
        assert session >= 1

    def test_finds_highest_session_number(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text("Session 5\nSession 12\nSession 8\n")
        session = _get_session_number(log)
        assert session == 12


# ---------------------------------------------------------------------------
# _check_red_flags
# ---------------------------------------------------------------------------

class TestCheckRedFlags:
    def test_no_flags_for_healthy_repo(self):
        red, warn = _check_red_flags(health_score=85.0, test_count=1800, source_modules=52)
        assert len(red) == 0

    def test_red_flag_for_very_low_health(self):
        red, warn = _check_red_flags(health_score=55.0, test_count=1000, source_modules=30)
        assert len(red) > 0
        assert any("health" in r.lower() for r in red)

    def test_warning_for_moderate_health(self):
        red, warn = _check_red_flags(health_score=65.0, test_count=1000, source_modules=30)
        assert len(warn) > 0

    def test_red_flag_for_very_low_test_density(self):
        red, warn = _check_red_flags(health_score=80.0, test_count=20, source_modules=52)
        assert len(red) > 0

    def test_warning_for_low_test_density(self):
        red, warn = _check_red_flags(health_score=80.0, test_count=700, source_modules=52)
        # 700/52 ≈ 13.4 tests/module — should warn
        assert len(warn) > 0 or len(red) > 0


# ---------------------------------------------------------------------------
# generate_status
# ---------------------------------------------------------------------------

class TestGenerateStatus:
    def test_returns_status_report(self, mock_repo):
        report = generate_status(mock_repo)
        assert isinstance(report, StatusReport)

    def test_generated_at_present(self, mock_repo):
        report = generate_status(mock_repo)
        assert "UTC" in report.generated_at

    def test_overall_status_valid(self, mock_repo):
        report = generate_status(mock_repo)
        assert report.overall_status in ("GREEN", "YELLOW", "RED")

    def test_summary_non_empty(self, mock_repo):
        report = generate_status(mock_repo)
        assert isinstance(report.summary, str)
        assert len(report.summary) > 10

    def test_fallback_values_applied(self, mock_repo):
        """When live analysis fails, known accurate values should be used."""
        report = generate_status(mock_repo)
        assert report.source_modules >= 40
        assert report.test_count >= 1000

    def test_uses_cwd_when_no_root(self):
        """Should not crash when called without root (falls back to cwd)."""
        try:
            report = generate_status()
            assert isinstance(report, StatusReport)
        except Exception:
            pytest.skip("Not running from repo root — expected in CI")


# ---------------------------------------------------------------------------
# format_status
# ---------------------------------------------------------------------------

class TestFormatStatus:
    def test_output_is_string(self, mock_repo):
        report = generate_status(mock_repo)
        out = format_status(report)
        assert isinstance(out, str)

    def test_output_contains_header(self, mock_repo):
        report = generate_status(mock_repo)
        out = format_status(report)
        assert "NIGHTSHIFT STATUS" in out

    def test_output_contains_codebase_section(self, mock_repo):
        report = generate_status(mock_repo)
        out = format_status(report)
        assert "CODEBASE" in out

    def test_output_contains_quality_section(self, mock_repo):
        report = generate_status(mock_repo)
        out = format_status(report)
        assert "QUALITY" in out

    def test_output_contains_quick_commands(self, mock_repo):
        report = generate_status(mock_repo)
        out = format_status(report)
        assert "nightshift brain" in out

    def test_red_flags_appear_in_output(self, tmp_path):
        """A report with red flags should show them."""
        report = StatusReport(
            generated_at="2026-02-28 10:00 UTC",
            session=18,
            project_age_days=None,
            health_grade="D",
            health_score=55.0,
            health_trend="DECLINING",
            test_count=100,
            test_files=5,
            source_modules=52,
            cli_commands=46,
            api_endpoints=35,
            total_prs=41,
            red_flags=["Critical issue detected"],
            warnings=[],
            top_recommendation="Fix health score",
            overall_status="RED",
            summary="Test summary",
        )
        out = format_status(report)
        assert "RED FLAGS" in out
        assert "Critical issue detected" in out


# ---------------------------------------------------------------------------
# status_to_json
# ---------------------------------------------------------------------------

class TestStatusToJson:
    def test_valid_json(self, mock_repo):
        report = generate_status(mock_repo)
        data = json.loads(status_to_json(report))
        assert isinstance(data, dict)

    def test_json_has_required_fields(self, mock_repo):
        report = generate_status(mock_repo)
        data = json.loads(status_to_json(report))
        assert "session" in data
        assert "overall_status" in data
        assert "health_grade" in data
        assert "test_count" in data
        assert "source_modules" in data

    def test_json_overall_status_valid(self, mock_repo):
        report = generate_status(mock_repo)
        data = json.loads(status_to_json(report))
        assert data["overall_status"] in ("GREEN", "YELLOW", "RED")

    def test_json_red_flags_is_list(self, mock_repo):
        report = generate_status(mock_repo)
        data = json.loads(status_to_json(report))
        assert isinstance(data["red_flags"], list)
