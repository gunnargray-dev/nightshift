"""Dependency freshness checker for Nightshift.

Inspects the project's dependency specification files (pyproject.toml,
requirements.txt, requirements*.txt) and checks each declared dependency
against the PyPI JSON API to determine whether a newer version is available.

CLI usage
---------
    nightshift deps
    nightshift deps --offline      # skip PyPI queries; list deps only
    nightshift deps --json         # raw JSON output

This module is named ``deps_checker.py`` so that the CLI can import it as
``from src.deps_checker import check_freshness``.
"""

from __future__ import annotations

import re
import urllib.request
import urllib.error
import json as _json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PackageStatus:
    """Freshness status for a single package."""

    name: str
    installed_version: str = ""   # declared / installed version (from lock or spec)
    latest_version: str = ""      # latest on PyPI
    status: str = "unknown"       # up-to-date | outdated | unknown | error
    error: str = ""

    @property
    def is_outdated(self) -> bool:
        return self.status == "outdated"

    @property
    def delta_symbol(self) -> str:
        if self.status == "outdated":
            return "▼"
        if self.status == "up-to-date":
            return "="
        return "?"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FreshnessReport:
    """Aggregated freshness report for all declared dependencies."""

    packages: list[PackageStatus] = field(default_factory=list)
    checked_at: str = ""
    offline: bool = False
    source_files: list[str] = field(default_factory=list)

    @property
    def outdated_count(self) -> int:
        return sum(1 for p in self.packages if p.is_outdated)

    @property
    def up_to_date_count(self) -> int:
        return sum(1 for p in self.packages if p.status == "up-to-date")

    @property
    def unknown_count(self) -> int:
        return sum(1 for p in self.packages if p.status in ("unknown", "error"))

    def to_dict(self) -> dict:
        return {
            "packages": [p.to_dict() for p in self.packages],
            "checked_at": self.checked_at,
            "offline": self.offline,
            "source_files": self.source_files,
            "outdated_count": self.outdated_count,
            "up_to_date_count": self.up_to_date_count,
            "unknown_count": self.unknown_count,
        }

    def to_markdown(self) -> str:
        """Render the freshness report as a Markdown table."""
        lines = [
            "# Dependency Freshness Report",
            "",
            f"*Checked: {self.checked_at}*",
            "",
        ]
        if self.source_files:
            lines += [
                "**Sources:**",
                "",
            ]
            for sf in self.source_files:
                lines.append(f"- `{sf}`")
            lines.append("")

        if not self.packages:
            lines += ["No dependencies found.", ""]
            return "\n".join(lines)

        lines += [
            "## Summary",
            "",
            f"| Status | Count |",
            f"|--------|-------|",
            f"| Up-to-date | {self.up_to_date_count} |",
            f"| Outdated | {self.outdated_count} |",
            f"| Unknown | {self.unknown_count} |",
            f"| **Total** | **{len(self.packages)}** |",
            "",
            "## Packages",
            "",
            "| Package | Declared | Latest | Status |",
            "|---------|----------|--------|--------|",
        ]

        for pkg in sorted(self.packages, key=lambda p: (p.status != "outdated", p.name)):
            sym = pkg.delta_symbol
            declared = pkg.installed_version or "—"
            latest = pkg.latest_version or "—"
            status_str = f"{sym} {pkg.status}"
            if pkg.error:
                status_str += f" ({pkg.error[:30]})"
            lines.append(f"| `{pkg.name}` | {declared} | {latest} | {status_str} |")

        lines += ["", "---", ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dependency discovery
# ---------------------------------------------------------------------------


def _extract_from_requirements(path: Path) -> list[tuple[str, str]]:
    """Parse a requirements.txt-style file.

    Returns a list of (package_name, version_spec) tuples.
    Version spec may be empty string if no version pin was found.
    """
    deps: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Strip extras like package[extra]>=1.0
        m = re.match(r"^([A-Za-z0-9_\-]+)(?:\[.*?\])?\s*([><=!~]+\s*[\w.,*]+)?", line)
        if m:
            name = m.group(1).strip()
            spec = (m.group(2) or "").strip()
            deps.append((name, spec))
    return deps


def _extract_from_pyproject(path: Path) -> list[tuple[str, str]]:
    """Parse dependencies from pyproject.toml.

    Reads ``[project] dependencies`` and ``[project.optional-dependencies]``.
    Returns a list of (package_name, version_spec) tuples.
    """
    deps: list[tuple[str, str]] = []

    raw_text = path.read_text(encoding="utf-8")

    # Try tomllib / tomli first
    if tomllib is not None:
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
            all_specs: list[str] = []
            all_specs.extend(data.get("project", {}).get("dependencies", []))
            for group in data.get("project", {}).get("optional-dependencies", {}).values():
                all_specs.extend(group)
            for spec in all_specs:
                m = re.match(r"^([A-Za-z0-9_\-]+)(?:\[.*?\])?\s*([><=!~]+\s*[\w.,*]+)?", spec)
                if m:
                    deps.append((m.group(1).strip(), (m.group(2) or "").strip()))
            return deps
        except Exception:
            pass

    # Fallback: simple regex extraction
    in_deps = False
    for line in raw_text.splitlines():
        stripped = line.strip()
        if re.match(r'^dependencies\s*=\s*\[', stripped):
            in_deps = True
        if in_deps:
            m = re.search(r'"([A-Za-z0-9_\-]+)(?:\[.*?\])?\s*([><=!~]+\s*[\w.,*]+)?"', stripped)
            if m:
                deps.append((m.group(1), (m.group(2) or "").strip()))
            if "]" in stripped:
                in_deps = False
    return deps


def discover_dependencies(repo_path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Find all declared dependencies in the repo.

    Searches for:
    - pyproject.toml  (PEP 621)
    - requirements.txt
    - requirements*.txt

    Returns:
        (list of (name, version_spec), list of source file paths)
    """
    deps: list[tuple[str, str]] = []
    sources: list[str] = []

    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        found = _extract_from_pyproject(pyproject)
        if found:
            deps.extend(found)
            sources.append(str(pyproject.relative_to(repo_path)))

    for req_file in sorted(repo_path.glob("requirements*.txt")):
        found = _extract_from_requirements(req_file)
        if found:
            deps.extend(found)
            sources.append(str(req_file.relative_to(repo_path)))

    # Deduplicate by package name (keep first occurrence)
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for name, spec in deps:
        norm = name.lower().replace("-", "_")
        if norm not in seen:
            seen.add(norm)
            unique.append((name, spec))

    return unique, sources


# ---------------------------------------------------------------------------
# PyPI querying
# ---------------------------------------------------------------------------

PYPI_API = "https://pypi.org/pypi/{package}/json"
_REQUEST_TIMEOUT = 5  # seconds


def _get_latest_version(package_name: str) -> tuple[str, str]:
    """Query PyPI for the latest version of a package.

    Returns:
        (latest_version, error_message)  — error_message is "" on success.
    """
    url = PYPI_API.format(package=package_name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "nightshift-dep-checker/1.0"})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT) as resp:
            data = _json.loads(resp.read())
        version = data["info"]["version"]
        return version, ""
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "", f"not found on PyPI"
        return "", f"HTTP {exc.code}"
    except Exception as exc:
        return "", str(exc)[:60]


def _compare_versions(declared: str, latest: str) -> str:
    """Determine status comparing a declared version spec to the latest.

    Returns "up-to-date", "outdated", or "unknown".
    """
    if not declared or not latest:
        return "unknown"

    # Extract exact version from spec like >=1.0,<2 or ==1.2.3
    exact_match = re.search(r"==(\s*[\d.]+)", declared)
    gte_match = re.search(r">=(\s*[\d.]+)", declared)

    if exact_match:
        pinned = exact_match.group(1).strip()
        return "up-to-date" if pinned == latest else "outdated"
    if gte_match:
        lower = gte_match.group(1).strip()
        try:
            v_lower = tuple(int(x) for x in lower.split("."))
            v_latest = tuple(int(x) for x in latest.split("."))
            return "up-to-date" if v_lower >= v_latest else "outdated"
        except ValueError:
            return "unknown"

    # No pin — can't determine without an installed version
    return "unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_freshness(
    repo_path: Optional[Path] = None,
    offline: bool = False,
) -> FreshnessReport:
    """Check Python dependency freshness for the repo.

    Args:
        repo_path: Repository root. Defaults to CWD.
        offline: If True, skip PyPI queries and just list declared deps.

    Returns:
        FreshnessReport with per-package status.
    """
    from datetime import datetime, timezone

    repo = repo_path or Path.cwd()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    all_deps, sources = discover_dependencies(repo)
    packages: list[PackageStatus] = []

    for name, spec in all_deps:
        pkg = PackageStatus(name=name, installed_version=spec)
        if offline:
            pkg.status = "unknown"
            pkg.error = "offline mode"
        else:
            latest, err = _get_latest_version(name)
            if err:
                pkg.status = "error"
                pkg.error = err
                pkg.latest_version = ""
            else:
                pkg.latest_version = latest
                pkg.status = _compare_versions(spec, latest)
        packages.append(pkg)

    return FreshnessReport(
        packages=packages,
        checked_at=ts,
        offline=offline,
        source_files=sources,
    )
