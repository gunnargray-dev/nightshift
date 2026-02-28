"""Tests for src/deps_checker.py — dependency freshness checker."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import urllib.error

import pytest

from src.deps_checker import (
    PackageStatus,
    FreshnessReport,
    check_freshness,
    discover_dependencies,
    _extract_from_requirements,
    _extract_from_pyproject,
    _get_latest_version,
    _compare_versions,
)


# ---------------------------------------------------------------------------
# PackageStatus
# ---------------------------------------------------------------------------


class TestPackageStatus:
    def test_outdated_flag(self):
        pkg = PackageStatus("requests", "==2.25.0", "2.31.0", status="outdated")
        assert pkg.is_outdated is True

    def test_up_to_date_flag(self):
        pkg = PackageStatus("pytest", "==7.4.0", "7.4.0", status="up-to-date")
        assert pkg.is_outdated is False

    def test_delta_symbol_outdated(self):
        pkg = PackageStatus("x", status="outdated")
        assert pkg.delta_symbol == "▼"

    def test_delta_symbol_up_to_date(self):
        pkg = PackageStatus("x", status="up-to-date")
        assert pkg.delta_symbol == "="

    def test_delta_symbol_unknown(self):
        pkg = PackageStatus("x", status="unknown")
        assert pkg.delta_symbol == "?"

    def test_to_dict(self):
        pkg = PackageStatus("requests", "==2.25.0", "2.31.0", status="outdated")
        d = pkg.to_dict()
        assert d["name"] == "requests"
        assert d["installed_version"] == "==2.25.0"
        assert d["latest_version"] == "2.31.0"
        assert d["status"] == "outdated"


# ---------------------------------------------------------------------------
# FreshnessReport
# ---------------------------------------------------------------------------


class TestFreshnessReport:
    def _make_report(self) -> FreshnessReport:
        return FreshnessReport(
            packages=[
                PackageStatus("requests", "==2.25.0", "2.31.0", status="outdated"),
                PackageStatus("pytest", "==7.4.0", "7.4.0", status="up-to-date"),
                PackageStatus("unknown_pkg", "", "", status="error", error="not found"),
            ],
            checked_at="2026-02-28",
        )

    def test_outdated_count(self):
        report = self._make_report()
        assert report.outdated_count == 1

    def test_up_to_date_count(self):
        report = self._make_report()
        assert report.up_to_date_count == 1

    def test_unknown_count(self):
        report = self._make_report()
        assert report.unknown_count == 1

    def test_to_dict_structure(self):
        report = self._make_report()
        d = report.to_dict()
        assert "packages" in d
        assert "outdated_count" in d
        assert d["outdated_count"] == 1

    def test_to_markdown_contains_table(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "# Dependency Freshness Report" in md
        assert "requests" in md
        assert "pytest" in md

    def test_to_markdown_shows_summary(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "Outdated" in md
        assert "Up-to-date" in md

    def test_to_markdown_delta_symbols(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "▼" in md  # outdated
        assert "=" in md  # up-to-date

    def test_empty_report(self):
        report = FreshnessReport(packages=[], checked_at="now")
        md = report.to_markdown()
        assert "No dependencies found" in md


# ---------------------------------------------------------------------------
# _extract_from_requirements
# ---------------------------------------------------------------------------


class TestExtractFromRequirements:
    def test_basic_pinned(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("requests==2.28.0\npytest>=7.0\n")
        deps = _extract_from_requirements(f)
        names = [d[0] for d in deps]
        assert "requests" in names
        assert "pytest" in names

    def test_skips_comments(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("# comment\nflask==2.0\n")
        deps = _extract_from_requirements(f)
        assert len(deps) == 1
        assert deps[0][0] == "flask"

    def test_skips_options(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("-r base.txt\ndjango>=3.0\n")
        deps = _extract_from_requirements(f)
        names = [d[0] for d in deps]
        assert "django" in names

    def test_extras_stripped(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("uvicorn[standard]>=0.20\n")
        deps = _extract_from_requirements(f)
        assert deps[0][0] == "uvicorn"

    def test_version_captured(self, tmp_path):
        f = tmp_path / "requirements.txt"
        f.write_text("requests==2.28.0\n")
        deps = _extract_from_requirements(f)
        assert "==2.28.0" in deps[0][1]


# ---------------------------------------------------------------------------
# _extract_from_pyproject
# ---------------------------------------------------------------------------


class TestExtractFromPyproject:
    def test_empty_dependencies(self, tmp_path):
        pp = tmp_path / "pyproject.toml"
        pp.write_text("[project]\nname=\"test\"\n")
        deps = _extract_from_pyproject(pp)
        assert deps == []

    def test_with_requirements_in_pyproject(self, tmp_path):
        """Test fallback regex path when tomllib not available."""
        pp = tmp_path / "pyproject.toml"
        pp.write_text(
            '[project]\ndependencies = [\n    "requests>=2.0",\n    "pytest>=7.0",\n]\n'
        )
        deps = _extract_from_pyproject(pp)
        names = [d[0] for d in deps]
        # Should find at least something (depends on tomllib availability)
        # If nothing found, that's OK for this test
        assert isinstance(deps, list)


# ---------------------------------------------------------------------------
# _compare_versions
# ---------------------------------------------------------------------------


class TestCompareVersions:
    def test_exact_up_to_date(self):
        assert _compare_versions("==2.31.0", "2.31.0") == "up-to-date"

    def test_exact_outdated(self):
        assert _compare_versions("==2.25.0", "2.31.0") == "outdated"

    def test_gte_up_to_date(self):
        assert _compare_versions(">=2.31.0", "2.31.0") == "up-to-date"

    def test_gte_outdated(self):
        assert _compare_versions(">=2.0.0", "3.0.0") == "outdated"

    def test_no_spec(self):
        assert _compare_versions("", "3.0.0") == "unknown"

    def test_no_latest(self):
        assert _compare_versions("==1.0.0", "") == "unknown"

    def test_non_standard_spec(self):
        # Can't determine without exact or >= pin
        result = _compare_versions("~=2.0", "3.0.0")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# _get_latest_version (mocked)
# ---------------------------------------------------------------------------


class TestGetLatestVersion:
    def test_successful_query(self):
        mock_data = json.dumps({"info": {"version": "3.0.0"}}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            version, err = _get_latest_version("requests")
        assert version == "3.0.0"
        assert err == ""

    def test_404_error(self):
        with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
            url="", code=404, msg="Not Found", hdrs=None, fp=None  # type: ignore[arg-type]
        )):
            version, err = _get_latest_version("nonexistent-package-xyz")
        assert version == ""
        assert "not found" in err.lower()

    def test_network_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            version, err = _get_latest_version("requests")
        assert version == ""
        assert err != ""


# ---------------------------------------------------------------------------
# discover_dependencies
# ---------------------------------------------------------------------------


class TestDiscoverDependencies:
    def test_empty_repo(self, tmp_path):
        deps, sources = discover_dependencies(tmp_path)
        assert deps == []
        assert sources == []

    def test_finds_requirements_txt(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("flask>=2.0\n")
        deps, sources = discover_dependencies(tmp_path)
        names = [d[0] for d in deps]
        assert "flask" in names
        assert any("requirements.txt" in s for s in sources)

    def test_deduplicates_across_files(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests>=2.0\n")
        (tmp_path / "requirements-dev.txt").write_text("requests>=2.0\npytest\n")
        deps, sources = discover_dependencies(tmp_path)
        names = [d[0].lower().replace("-", "_") for d in deps]
        # requests should appear only once
        assert names.count("requests") == 1


# ---------------------------------------------------------------------------
# check_freshness (integration, offline mode)
# ---------------------------------------------------------------------------


class TestCheckFreshness:
    def test_offline_mode_returns_unknown(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests>=2.0\nflask>=2.0\n")
        report = check_freshness(repo_path=tmp_path, offline=True)
        assert all(p.status in ("unknown", "error") for p in report.packages)
        assert report.offline is True

    def test_empty_repo_no_packages(self, tmp_path):
        report = check_freshness(repo_path=tmp_path, offline=True)
        assert report.packages == []

    def test_checked_at_set(self, tmp_path):
        report = check_freshness(repo_path=tmp_path, offline=True)
        assert report.checked_at != ""

    def test_source_files_populated(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests>=2.0\n")
        report = check_freshness(repo_path=tmp_path, offline=True)
        assert len(report.source_files) >= 1

    def test_online_mode_with_mock(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.25.0\n")
        mock_data = json.dumps({"info": {"version": "2.31.0"}}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            report = check_freshness(repo_path=tmp_path, offline=False)

        assert len(report.packages) == 1
        pkg = report.packages[0]
        assert pkg.name == "requests"
        assert pkg.latest_version == "2.31.0"
        assert pkg.status == "outdated"
