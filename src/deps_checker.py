"""Nightshift Dependency Freshness Checker.

Checks whether the Python packages declared in pyproject.toml (or
requirements*.txt) are up to date by querying PyPI's JSON API.

Public API
----------
check_freshness(repo_path) -> FreshnessReport
render_freshness_report(report) -> str  (Markdown)
"""

from __future__ import annotations

import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PackageStatus:
    name: str
    current_version: Optional[str]   # version declared / installed (may be None)
    latest_version: Optional[str]    # latest on PyPI
    latest_release_date: Optional[str]  # ISO date string
    is_outdated: bool = False
    is_missing: bool = False
    error: Optional[str] = None

    @property
    def status_icon(self) -> str:
        if self.error:
            return "?"
        if self.is_missing:
            return "·"
        if self.is_outdated:
            return "↑"
        return "✓"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "latest_release_date": self.latest_release_date,
            "is_outdated": self.is_outdated,
            "is_missing": self.is_missing,
            "status_icon": self.status_icon,
        }


@dataclass
class FreshnessReport:
    packages: list[PackageStatus] = field(default_factory=list)
    source_file: Optional[str] = None
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    )

    @property
    def outdated_count(self) -> int:
        return sum(1 for p in self.packages if p.is_outdated)

    @property
    def up_to_date_count(self) -> int:
        return sum(1 for p in self.packages if not p.is_outdated and not p.is_missing and not p.error)

    @property
    def error_count(self) -> int:
        return sum(1 for p in self.packages if p.error)

    def to_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "checked_at": self.checked_at,
            "outdated_count": self.outdated_count,
            "up_to_date_count": self.up_to_date_count,
            "packages": [p.to_dict() for p in self.packages],
        }

    def to_markdown(self) -> str:
        return render_freshness_report(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Package discovery
# ---------------------------------------------------------------------------

def _parse_pyproject_toml(path: Path) -> list[tuple[str, Optional[str]]]:
    """Extract (package_name, version_spec) pairs from pyproject.toml."""
    text = path.read_text(encoding="utf-8")
    results: list[tuple[str, Optional[str]]] = []

    # Find [project] dependencies = [ ... ]
    in_deps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                in_deps = False
                continue
            dep = stripped.strip('",').strip()
            if dep:
                m = re.match(r"^([A-Za-z0-9_\-\.]+)\s*([><=~!].+)?$", dep)
                if m:
                    results.append((m.group(1), m.group(2)))

    # Also look for [tool.poetry.dependencies] style
    if not results:
        in_poetry_deps = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "[tool.poetry.dependencies]":
                in_poetry_deps = True
                continue
            if in_poetry_deps and stripped.startswith("["):
                in_poetry_deps = False
                continue
            if in_poetry_deps and "=" in stripped and not stripped.startswith("#"):
                key, _, val = stripped.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key not in ("python", "Python"):
                    results.append((key, val))

    return results


def _parse_requirements_txt(path: Path) -> list[tuple[str, Optional[str]]]:
    """Extract (package_name, version_spec) pairs from requirements.txt."""
    results: list[tuple[str, Optional[str]]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = re.match(r"^([A-Za-z0-9_\-\.]+)\s*([><=~!].+)?", line)
        if m:
            results.append((m.group(1), m.group(2)))
    return results


def discover_packages(repo_path: Path) -> tuple[list[tuple[str, Optional[str]]], str]:
    """Discover packages and return (package_list, source_description)."""
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        pkgs = _parse_pyproject_toml(pyproject)
        if pkgs:
            return pkgs, "pyproject.toml"

    for fname in ("requirements.txt", "requirements-dev.txt", "requirements/base.txt"):
        req = repo_path / fname
        if req.exists():
            pkgs = _parse_requirements_txt(req)
            if pkgs:
                return pkgs, fname

    return [], "no dependency file found"


# ---------------------------------------------------------------------------
# PyPI query
# ---------------------------------------------------------------------------

def _query_pypi(package_name: str, timeout: int = 8) -> Optional[dict]:
    """Fetch latest package info from PyPI JSON API."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nightshift/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _extract_latest_version(pypi_data: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (latest_version, release_date_iso) from PyPI JSON."""
    info = pypi_data.get("info", {})
    latest = info.get("version")
    releases = pypi_data.get("releases", {})
    date_str = None
    if latest and latest in releases:
        files = releases[latest]
        if files:
            upload_time = files[0].get("upload_time")
            if upload_time:
                try:
                    dt = datetime.fromisoformat(upload_time)
                    date_str = dt.strftime("%Y-%m-%d")
                except ValueError:
                    date_str = upload_time[:10]
    return latest, date_str


def _version_is_outdated(current: Optional[str], latest: Optional[str]) -> bool:
    """Simple version comparison — True if latest > current."""
    if not current or not latest:
        return False
    current_clean = re.sub(r"[><=~!^]", "", current).strip().split(",")[0].strip()
    try:
        c_parts = tuple(int(x) for x in current_clean.split(".")[:3])
        l_parts = tuple(int(x) for x in latest.split(".")[:3])
        return l_parts > c_parts
    except ValueError:
        return latest != current_clean


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_freshness(
    repo_path: Path,
    offline: bool = False,
    packages: Optional[list[tuple[str, Optional[str]]]] = None,
    source: str = "",
) -> FreshnessReport:
    """Check dependency freshness for packages in repo_path.

    Parameters
    ----------
    repo_path:
        Repository root — scanned for pyproject.toml / requirements.txt.
    offline:
        If True, skip PyPI queries and return status based on declared versions only.
    packages:
        Override package list (for testing). If None, auto-discovers from repo.
    source:
        Override source label (for testing).

    Returns
    -------
    FreshnessReport with per-package freshness status.
    """
    if packages is None:
        packages, source = discover_packages(repo_path)

    statuses: list[PackageStatus] = []

    for pkg_name, version_spec in packages:
        if offline:
            statuses.append(PackageStatus(
                name=pkg_name,
                current_version=version_spec,
                latest_version=None,
                latest_release_date=None,
                error="offline mode — PyPI not queried",
            ))
            continue

        pypi_data = _query_pypi(pkg_name)
        if pypi_data is None:
            statuses.append(PackageStatus(
                name=pkg_name,
                current_version=version_spec,
                latest_version=None,
                latest_release_date=None,
                error="PyPI query failed",
            ))
            continue

        latest, release_date = _extract_latest_version(pypi_data)
        outdated = _version_is_outdated(version_spec, latest)
        missing = version_spec is None

        statuses.append(PackageStatus(
            name=pkg_name,
            current_version=version_spec,
            latest_version=latest,
            latest_release_date=release_date,
            is_outdated=outdated,
            is_missing=missing,
        ))

    return FreshnessReport(packages=statuses, source_file=source)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_freshness_report(report: FreshnessReport) -> str:
    """Render a FreshnessReport as Markdown."""
    lines: list[str] = [
        "# Dependency Freshness Report",
        "",
        f"*Source: `{report.source_file}`  ·  Checked: {report.checked_at}*",
        "",
    ]

    lines += [
        "## Summary",
        "",
        f"| Metric | Count |",
        f"| --- | --- |",
        f"| Total packages | {len(report.packages)} |",
        f"| Up to date | {report.up_to_date_count} |",
        f"| Outdated | {report.outdated_count} |",
        f"| Errors | {report.error_count} |",
        "",
    ]

    if not report.packages:
        lines.append("_No packages found. Add dependencies to pyproject.toml._")
        return "\n".join(lines)

    lines += [
        "## Packages",
        "",
        "| Status | Package | Current | Latest | Released |",
        "| --- | --- | --- | --- | --- |",
    ]

    for p in sorted(report.packages, key=lambda x: (0 if x.is_outdated else 1, x.name)):
        current = p.current_version or "—"
        latest = p.latest_version or "—"
        released = p.latest_release_date or "—"
        error = f" _(error: {p.error})_" if p.error else ""
        lines.append(
            f"| {p.status_icon} | `{p.name}` | `{current}` | `{latest}` | {released}{error} |"
        )

    lines.append("")

    if report.outdated_count > 0:
        lines.append(f"**{report.outdated_count} package(s) have newer versions available.**")
        for p in report.packages:
            if p.is_outdated:
                lines.append(f"  · `{p.name}` {p.current_version} → {p.latest_version}")
        lines.append("")

    return "\n".join(lines)
