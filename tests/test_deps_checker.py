"""Tests for src/deps_checker.py — Dependency Freshness Checker."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.deps_checker import (
    check_freshness,
    render_freshness_report,
    FreshnessReport,
    PackageStatus,
    discover_packages,
    _parse_pyproject_toml,
    _parse_requirements_txt,
    _version_is_outdated,
)


# ---------------------------------------------------------------------------
# _version_is_outdated
# ---------------------------------------------------------------------------

class TestVersionIsOutdated:
    def test_older_version_is_outdated(self):
        assert _version_is_outdated("1.0.0", "2.0.0") is True

    def test_same_version_not_outdated(self):
        assert _version_is_outdated("2.0.0", "2.0.0") is False

    def test_newer_current_not_outdated(self):
        assert _version_is_outdated("3.0.0", "2.0.0") is False

    def test_none_current_not_outdated(self):
        assert _version_is_outdated(None, "2.0.0") is False

    def test_none_latest_not_outdated(self):
        assert _version_is_outdated("1.0.0", None) is False

    def test_with_operator_prefix(self):
        assert _version_is_outdated(">=1.0.0", "2.0.0") is True

    def test_with_tilde_operator(self):
        assert _version_is_outdated("~=1.0", "1.5.0") is True

    def test_minor_update_is_outdated(self):
        assert _version_is_outdated("1.0.0", "1.1.0") is True

    def test_patch_update_is_outdated(self):
        assert _version_is_outdated("1.0.0", "1.0.1") is True

    def test_both_none(self):
        assert _version_is_outdated(None, None) is False


# ---------------------------------------------------------------------------
# PackageStatus
# ---------------------------------------------------------------------------

class TestPackageStatus:
    def test_up_to_date_icon(self):
        p = PackageStatus("requests", "2.28.0", "2.28.0", "2023-01-01")
        assert p.status_icon == "✓"

    def test_outdated_icon(self):
        p = PackageStatus("requests", "2.27.0", "2.28.0", "2023-01-01", is_outdated=True)
        assert p.status_icon == "↑"

    def test_error_icon(self):
        p = PackageStatus("requests", None, None, None, error="timeout")
        assert p.status_icon == "?"

    def test_missing_icon(self):
        p = PackageStatus("requests", None, "2.28.0", "2023-01-01", is_missing=True)
        assert p.status_icon == "·"

    def test_to_dict(self):
        p = PackageStatus("requests", "2.28.0", "2.28.0", "2023-01-01")
        d = p.to_dict()
        assert isinstance(d, dict)
        assert d["name"] == "requests"
        assert "is_outdated" in d
        assert "status_icon" in d

    def test_to_dict_json_serializable(self):
        p = PackageStatus("requests", "2.28.0", "2.28.0", "2023-01-01")
        serialized = json.dumps(p.to_dict())
        assert isinstance(serialized, str)


# ---------------------------------------------------------------------------
# FreshnessReport
# ---------------------------------------------------------------------------

class TestFreshnessReport:
    def test_outdated_count(self):
        report = FreshnessReport(packages=[
            PackageStatus("a", "1.0", "2.0", None, is_outdated=True),
            PackageStatus("b", "2.0", "2.0", None),
        ])
        assert report.outdated_count == 1

    def test_up_to_date_count(self):
        report = FreshnessReport(packages=[
            PackageStatus("a", "1.0", "2.0", None, is_outdated=True),
            PackageStatus("b", "2.0", "2.0", None),
        ])
        assert report.up_to_date_count == 1

    def test_error_count(self):
        report = FreshnessReport(packages=[
            PackageStatus("a", None, None, None, error="timeout"),
            PackageStatus("b", "2.0", "2.0", None),
        ])
        assert report.error_count == 1

    def test_to_dict(self):
        report = FreshnessReport()
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "packages" in d
        assert "checked_at" in d

    def test_to_json(self):
        report = FreshnessReport()
        j = report.to_json()
        assert isinstance(j, str)
        parsed = json.loads(j)
        assert "packages" in parsed

    def test_to_markdown(self):
        report = FreshnessReport()
        md = report.to_markdown()
        assert isinstance(md, str)

    def test_empty_packages(self):
        report = FreshnessReport()
        assert report.outdated_count == 0
        assert report.up_to_date_count == 0

    def test_checked_at_is_set(self):
        report = FreshnessReport()
        assert report.checked_at is not None
        assert "UTC" in report.checked_at


# ---------------------------------------------------------------------------
# _parse_pyproject_toml
# ---------------------------------------------------------------------------

class TestParsePyprojectToml:
    def test_empty_file(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text("[project]\nname = \"foo\"\n")
        result = _parse_pyproject_toml(p)
        assert isinstance(result, list)

    def test_parses_dependencies(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text(
            '[project]\nname = "foo"\ndependencies = [\n  "requests>=2.25",\n  "click~=8.0",\n]\n'
        )
        result = _parse_pyproject_toml(p)
        names = [r[0] for r in result]
        assert "requests" in names
        assert "click" in names

    def test_returns_list_of_tuples(self, tmp_path):
        p = tmp_path / "pyproject.toml"
        p.write_text('[project]\ndependencies = [\n  "pytest>=7.0",\n]\n')
        result = _parse_pyproject_toml(p)
        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], tuple)
            assert len(result[0]) == 2


# ---------------------------------------------------------------------------
# _parse_requirements_txt
# ---------------------------------------------------------------------------

class TestParseRequirementsTxt:
    def test_basic_requirements(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("requests>=2.25\nclick~=8.0\n")
        result = _parse_requirements_txt(p)
        names = [r[0] for r in result]
        assert "requests" in names
        assert "click" in names

    def test_ignores_comments(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("# This is a comment\nrequests>=2.25\n")
        result = _parse_requirements_txt(p)
        assert len(result) == 1

    def test_ignores_empty_lines(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("\n\nrequests>=2.25\n\n")
        result = _parse_requirements_txt(p)
        assert len(result) == 1

    def test_ignores_dash_options(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("-r base.txt\nrequests>=2.25\n")
        result = _parse_requirements_txt(p)
        assert len(result) == 1

    def test_no_version_spec(self, tmp_path):
        p = tmp_path / "requirements.txt"
        p.write_text("requests\n")
        result = _parse_requirements_txt(p)
        assert result[0][0] == "requests"
        assert result[0][1] is None


# ---------------------------------------------------------------------------
# discover_packages
# ---------------------------------------------------------------------------

class TestDiscoverPackages:
    def test_finds_pyproject(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = [\n  "requests>=2.25",\n]\n'
        )
        packages, source = discover_packages(tmp_path)
        assert "pyproject.toml" in source

    def test_falls_back_to_requirements(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests>=2.25\n")
        packages, source = discover_packages(tmp_path)
        assert "requirements" in source

    def test_returns_empty_when_no_files(self, tmp_path):
        packages, source = discover_packages(tmp_path)
        assert packages == []
        assert "no dependency" in source.lower()

    def test_prefers_pyproject_over_requirements(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = [\n  "click>=8.0",\n]\n'
        )
        (tmp_path / "requirements.txt").write_text("requests>=2.25\n")
        packages, source = discover_packages(tmp_path)
        assert "pyproject.toml" in source


# ---------------------------------------------------------------------------
# check_freshness (offline mode)
# ---------------------------------------------------------------------------

class TestCheckFreshnessOffline:
    def test_offline_mode_skips_pypi(self, tmp_path):
        packages = [("requests", ">=2.25"), ("click", "~=8.0")]
        report = check_freshness(
            repo_path=tmp_path,
            offline=True,
            packages=packages,
            source="test",
        )
        assert isinstance(report, FreshnessReport)
        assert len(report.packages) == 2

    def test_offline_sets_error_message(self, tmp_path):
        packages = [("requests", ">=2.25")]
        report = check_freshness(
            repo_path=tmp_path,
            offline=True,
            packages=packages,
            source="test",
        )
        assert report.packages[0].error is not None
        assert "offline" in report.packages[0].error.lower()

    def test_empty_packages_offline(self, tmp_path):
        report = check_freshness(
            repo_path=tmp_path,
            offline=True,
            packages=[],
            source="test",
        )
        assert len(report.packages) == 0

    def test_source_file_set(self, tmp_path):
        report = check_freshness(
            repo_path=tmp_path,
            offline=True,
            packages=[("requests", "1.0")],
            source="requirements.txt",
        )
        assert report.source_file == "requirements.txt"

    def test_no_packages_file_returns_empty_report(self, tmp_path):
        report = check_freshness(repo_path=tmp_path)
        assert isinstance(report, FreshnessReport)
        assert len(report.packages) == 0


# ---------------------------------------------------------------------------
# render_freshness_report
# ---------------------------------------------------------------------------

class TestRenderFreshnessReport:
    def test_returns_string(self):
        report = FreshnessReport()
        md = render_freshness_report(report)
        assert isinstance(md, str)

    def test_contains_heading(self):
        report = FreshnessReport()
        md = render_freshness_report(report)
        assert "# Dependency Freshness Report" in md

    def test_contains_summary_section(self):
        report = FreshnessReport()
        md = render_freshness_report(report)
        assert "## Summary" in md

    def test_contains_packages_section_when_packages_present(self):
        report = FreshnessReport(packages=[
            PackageStatus("requests", "2.28", "2.28", "2023-01-01")
        ])
        md = render_freshness_report(report)
        assert "## Packages" in md

    def test_outdated_highlighted(self):
        report = FreshnessReport(packages=[
            PackageStatus("requests", "2.27", "2.28", "2023-01-01", is_outdated=True)
        ])
        md = render_freshness_report(report)
        assert "outdated" in md.lower() or "↑" in md

    def test_no_packages_message(self):
        report = FreshnessReport(packages=[])
        md = render_freshness_report(report)
        assert "No packages found" in md or "0" in md

    def test_contains_checked_at(self):
        report = FreshnessReport()
        md = render_freshness_report(report)
        assert "UTC" in md

    def test_to_markdown_delegates(self):
        report = FreshnessReport()
        assert report.to_markdown() == render_freshness_report(report)
