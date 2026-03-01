"""Test coverage heat map for Awake.

Cross-references every ``src/X.py`` module against ``tests/test_X.py``
using AST to count:
- Public functions and classes defined in the source module
- Test functions (``test_*``) in the corresponding test file

From these two numbers we compute a *coverage proxy score* for each
module and rank them by coverage weakness, so sessions can prioritise
test improvements.

No subprocess, no pytest-cov — pure AST counting.  This is deliberately
a structural coverage estimate, not statement-level coverage.

Public API
----------
- ``ModuleCoverageEntry``  — coverage data for one module
- ``CoverageMapReport``    — full cross-module report
- ``build_coverage_map(repo_path)`` → ``CoverageMapReport``
- ``save_coverage_map(report, out_path)``

CLI
---
    awake coveragemap [--write] [--json]
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModuleCoverageEntry:
    """Structural coverage data for one src/ module."""

    module: str          # bare name, e.g. "health"
    src_file: str        # relative path to src/X.py
    test_file: str       # relative path to tests/test_X.py  (may be "—")
    public_symbols: int  # public functions + public classes in src
    test_count: int      # test_* functions in the test file
    has_test_file: bool  # True if tests/test_X.py exists

    # ---------------------------------------------------------------------------
    # Derived metrics
    # ---------------------------------------------------------------------------

    @property
    def ratio(self) -> float:
        """Tests-per-public-symbol ratio (higher is better).

        A ratio ≥ 1.0 indicates at least one test per public symbol.
        Missing test files score 0.
        """
        if not self.has_test_file or self.public_symbols == 0:
            return 0.0
        return round(self.test_count / self.public_symbols, 2)

    @property
    def coverage_score(self) -> int:
        """0–100 coverage score based on tests-per-symbol ratio.

        - No test file          → 0
        - ratio = 0             → 0
        - ratio ≥ 3.0           → 100 (≥ 3 tests per symbol is excellent)
        - ratio 1.0–3.0         → 33–100 (linearly scaled)
        - ratio 0–1.0           → 0–33  (linearly scaled)
        """
        if not self.has_test_file or self.public_symbols == 0:
            return 0
        ratio = self.ratio
        if ratio >= 3.0:
            return 100
        return round(ratio / 3.0 * 100)

    @property
    def heat(self) -> str:
        """Emoji heat indicator for quick visual scan."""
        s = self.coverage_score
        if s >= 80:
            return "🟢"
        if s >= 50:
            return "🟡"
        if s >= 20:
            return "🟠"
        return "🔴"

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "module": self.module,
            "src_file": self.src_file,
            "test_file": self.test_file,
            "has_test_file": self.has_test_file,
            "public_symbols": self.public_symbols,
            "test_count": self.test_count,
            "ratio": self.ratio,
            "coverage_score": self.coverage_score,
            "heat": self.heat,
        }


@dataclass
class CoverageMapReport:
    """Test coverage heat map for the full Awake src/ tree."""

    entries: list[ModuleCoverageEntry] = field(default_factory=list)
    repo_path: str = ""

    # ---------------------------------------------------------------------------
    # Derived helpers
    # ---------------------------------------------------------------------------

    @property
    def modules_without_tests(self) -> list[ModuleCoverageEntry]:
        """Modules that have no corresponding test file."""
        return [e for e in self.entries if not e.has_test_file]

    @property
    def weakest(self) -> list[ModuleCoverageEntry]:
        """Bottom 5 modules by coverage score (weakest first)."""
        return sorted(self.entries, key=lambda e: e.coverage_score)[:5]

    @property
    def avg_score(self) -> float:
        """Average coverage score across all modules."""
        if not self.entries:
            return 0.0
        return round(sum(e.coverage_score for e in self.entries) / len(self.entries), 1)

    @property
    def total_tests(self) -> int:
        """Sum of all test functions across all test files."""
        return sum(e.test_count for e in self.entries)

    @property
    def total_symbols(self) -> int:
        """Sum of all public symbols across all src files."""
        return sum(e.public_symbols for e in self.entries)

    # ---------------------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------------------

    def _bar(self, score: int, width: int = 10) -> str:
        """Render a compact ASCII bar for a 0–100 score."""
        filled = round(score / 100 * width)
        return "█" * filled + "░" * (width - filled)

    def to_markdown(self) -> str:
        """Render the heat map as a Markdown string."""
        lines: list[str] = []
        lines.append("# Test Coverage Heat Map\n")
        lines.append(f"**Repo:** `{self.repo_path}`\n")
        lines.append("## Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Modules analysed | {len(self.entries)} |")
        lines.append(f"| Missing test files | {len(self.modules_without_tests)} |")
        lines.append(f"| Total public symbols | {self.total_symbols} |")
        lines.append(f"| Total test functions | {self.total_tests} |")
        lines.append(f"| Average coverage score | {self.avg_score}/100 |")
        lines.append("")

        if not self.entries:
            lines.append("_No modules found._\n")
            return "\n".join(lines)

        lines.append("## Heat Map\n")
        lines.append("| Heat | Module | Symbols | Tests | Ratio | Score | Bar |")
        lines.append("|------|--------|---------|-------|-------|-------|-----|")
        for e in sorted(self.entries, key=lambda x: x.coverage_score):
            bar = self._bar(e.coverage_score)
            lines.append(
                f"| {e.heat} | `{e.module}` | {e.public_symbols} "
                f"| {e.test_count} | {e.ratio:.2f} | {e.coverage_score} "
                f"| `{bar}` |"
            )
        lines.append("")

        if self.modules_without_tests:
            lines.append("## Modules Missing Test Files\n")
            for e in self.modules_without_tests:
                lines.append(f"- `{e.src_file}` — no `tests/test_{e.module}.py` found")
            lines.append("")

        lines.append("## Priority: Weakest Coverage\n")
        for i, e in enumerate(self.weakest, start=1):
            lines.append(
                f"{i}. `{e.module}` — score {e.coverage_score}/100 "
                f"({e.test_count} tests / {e.public_symbols} symbols)"
            )
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict."""
        return {
            "repo_path": self.repo_path,
            "modules_count": len(self.entries),
            "missing_test_files": len(self.modules_without_tests),
            "total_symbols": self.total_symbols,
            "total_tests": self.total_tests,
            "avg_score": self.avg_score,
            "entries": [e.to_dict() for e in self.entries],
        }

    def to_json(self) -> str:
        """Serialise to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _count_public_symbols(tree: ast.Module) -> int:
    """Count top-level public functions + classes in *tree*."""
    count = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                count += 1
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                count += 1
    return count


def _count_test_functions(tree: ast.Module) -> int:
    """Count test_* functions (any nesting depth) in *tree*."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                count += 1
    return count


def _parse_or_none(path: Path) -> Optional[ast.Module]:
    """Parse *path* as Python, returning None on any error."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        return ast.parse(src, filename=str(path))
    except (SyntaxError, OSError):
        return None


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def build_coverage_map(repo_path: Optional[Path] = None) -> CoverageMapReport:
    """Build a structural test coverage heat map for *repo_path*/src/.

    For each ``src/X.py`` (excluding ``__init__.py`` and ``cli.py``) we
    look for ``tests/test_X.py`` and compare:
    - public symbols in source
    - test functions in test file

    Parameters
    ----------
    repo_path:
        Root of the Awake repo.  Defaults to the grandparent of this
        file when installed normally.
    """
    if repo_path is None:
        repo_path = Path(__file__).resolve().parent.parent
    repo_path = Path(repo_path)

    src_dir = repo_path / "src"
    tests_dir = repo_path / "tests"
    report = CoverageMapReport(repo_path=str(repo_path))

    if not src_dir.exists():
        return report

    for src_file in sorted(src_dir.glob("*.py")):
        if src_file.name.startswith("_"):
            continue

        module = src_file.stem
        rel_src = str(src_file.relative_to(repo_path))

        # Count public symbols in source
        tree = _parse_or_none(src_file)
        public_symbols = _count_public_symbols(tree) if tree else 0

        # Look for the canonical test file
        test_file = tests_dir / f"test_{module}.py"
        has_test = test_file.exists()
        rel_test = str(test_file.relative_to(repo_path)) if has_test else "—"

        test_count = 0
        if has_test:
            test_tree = _parse_or_none(test_file)
            if test_tree:
                test_count = _count_test_functions(test_tree)

        report.entries.append(ModuleCoverageEntry(
            module=module,
            src_file=rel_src,
            test_file=rel_test,
            public_symbols=public_symbols,
            test_count=test_count,
            has_test_file=has_test,
        ))

    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_coverage_map(report: CoverageMapReport, out_path: Path) -> None:
    """Write the coverage heat map as Markdown + JSON sidecar to *out_path*."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")
