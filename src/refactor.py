"""Self-refactor engine for Awake.

Analyzes source files for common code-quality issues and applies automatic
fixes.  The engine operates in two modes:

``--dry-run`` (default)
    Report issues found but do not modify any files.

``--apply``
    Rewrite files in place after user confirmation (or unconditionally
    when ``--yes`` is passed).

Supported refactors
-------------------
- **trailing whitespace** -- strip trailing spaces/tabs from every line.
- **mixed indentation** -- convert tabs to 4-space indentation.
- **long lines** -- warn about lines exceeding a configurable column limit
  (default 120).  Not auto-fixed because wrapping Python safely requires
  deeper AST knowledge.
- **unused imports** -- detect names imported but never referenced in the
  module body (heuristic, not 100 % accurate).
- **bare except** -- flag ``except:`` clauses with no exception type.

Public API
----------
- ``RefactorIssue``      -- a single detected issue
- ``RefactorReport``     -- all issues for one file
- ``scan_file(path)``    -> ``RefactorReport``
- ``scan_repo(root)``    -> list of ``RefactorReport``
- ``apply_fixes(report)`` -> patched source string

CLI
---
    awake refactor [--apply] [--yes] [--max-line-len N]
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RefactorIssue:
    """A single code-quality issue detected in a source file."""

    kind: str   # e.g. "trailing_whitespace", "unused_import", "bare_except"
    line: int   # 1-based line number
    message: str
    fixable: bool = True  # whether apply_fixes() can resolve it automatically


@dataclass
class RefactorReport:
    """Collection of issues found in a single source file."""

    path: str
    issues: list[RefactorIssue] = field(default_factory=list)

    @property
    def fixable_count(self) -> int:
        """Number of issues that can be automatically fixed."""
        return sum(1 for i in self.issues if i.fixable)


# ---------------------------------------------------------------------------
# Checkers
# ---------------------------------------------------------------------------


def _check_trailing_whitespace(lines: list[str]) -> list[RefactorIssue]:
    """Detect trailing whitespace on each line."""
    issues: list[RefactorIssue] = []
    for i, line in enumerate(lines, start=1):
        stripped = line.rstrip("\n").rstrip("\r")
        if stripped != stripped.rstrip():
            issues.append(
                RefactorIssue(
                    kind="trailing_whitespace",
                    line=i,
                    message="Trailing whitespace",
                    fixable=True,
                )
            )
    return issues


def _check_mixed_indentation(lines: list[str]) -> list[RefactorIssue]:
    """Detect lines that mix tabs and spaces for indentation."""
    issues: list[RefactorIssue] = []
    for i, line in enumerate(lines, start=1):
        indent = line[: len(line) - len(line.lstrip())]
        if "\t" in indent and " " in indent:
            issues.append(
                RefactorIssue(
                    kind="mixed_indentation",
                    line=i,
                    message="Mixed tabs and spaces in indentation",
                    fixable=True,
                )
            )
        elif "\t" in indent:
            issues.append(
                RefactorIssue(
                    kind="tab_indentation",
                    line=i,
                    message="Tab used for indentation (prefer spaces)",
                    fixable=True,
                )
            )
    return issues


def _check_long_lines(lines: list[str], max_len: int = 120) -> list[RefactorIssue]:
    """Flag lines longer than *max_len* characters."""
    issues: list[RefactorIssue] = []
    for i, line in enumerate(lines, start=1):
        if len(line.rstrip("\n")) > max_len:
            issues.append(
                RefactorIssue(
                    kind="long_line",
                    line=i,
                    message=f"Line exceeds {max_len} characters ({len(line.rstrip())} chars)",
                    fixable=False,
                )
            )
    return issues


def _check_bare_except(source: str) -> list[RefactorIssue]:
    """Detect bare ``except:`` clauses using the AST."""
    issues: list[RefactorIssue] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(
                RefactorIssue(
                    kind="bare_except",
                    line=node.lineno,
                    message="Bare 'except:' clause -- catch a specific exception type",
                    fixable=False,
                )
            )
    return issues


def _check_unused_imports(source: str) -> list[RefactorIssue]:
    """Heuristically detect imported names that are never used."""
    issues: list[RefactorIssue] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return issues

    imported: dict[str, int] = {}  # name -> line
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".")[0]
                imported[local_name] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname or alias.name
                imported[local_name] = node.lineno

    # Collect all Name nodes outside import statements
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Store):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                used.add(node.value.id)

    for name, lineno in imported.items():
        if name not in used:
            issues.append(
                RefactorIssue(
                    kind="unused_import",
                    line=lineno,
                    message=f"Imported name '{name}' appears unused",
                    fixable=True,
                )
            )
    return issues


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_file(path: str | Path, max_line_len: int = 120) -> RefactorReport:
    """Scan a single Python file and return a :class:`RefactorReport`.

    Parameters
    ----------
    path:
        Path to the Python source file.
    max_line_len:
        Maximum allowed line length (default 120).

    Returns
    -------
    RefactorReport
        All issues found in the file.
    """
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return RefactorReport(path=str(path), issues=[RefactorIssue(kind="read_error", line=0, message=str(exc), fixable=False)])

    lines = source.splitlines(keepends=True)
    report = RefactorReport(path=str(path))
    report.issues.extend(_check_trailing_whitespace(lines))
    report.issues.extend(_check_mixed_indentation(lines))
    report.issues.extend(_check_long_lines(lines, max_line_len))
    report.issues.extend(_check_bare_except(source))
    report.issues.extend(_check_unused_imports(source))
    report.issues.sort(key=lambda i: i.line)
    return report


def scan_repo(root: str | Path, max_line_len: int = 120) -> list[RefactorReport]:
    """Scan all Python files under *root* and return reports.

    Parameters
    ----------
    root:
        Repository root directory.
    max_line_len:
        Maximum allowed line length.

    Returns
    -------
    list[RefactorReport]
        One report per Python file found.
    """
    root = Path(root)
    reports: list[RefactorReport] = []
    for py_file in sorted(root.rglob("*.py")):
        reports.append(scan_file(py_file, max_line_len))
    return reports


# ---------------------------------------------------------------------------
# Auto-fixer
# ---------------------------------------------------------------------------


def apply_fixes(report: RefactorReport) -> str:
    """Return the source of *report.path* with all fixable issues resolved.

    Parameters
    ----------
    report:
        The report whose file should be patched.

    Returns
    -------
    str
        The patched source code string.
    """
    path = Path(report.path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    lines = source.splitlines(keepends=True)

    # Collect line numbers to fix by kind
    trailing_ws_lines: set[int] = set()
    tab_lines: set[int] = set()
    unused_import_lines: set[int] = set()

    for issue in report.issues:
        if issue.fixable:
            if issue.kind in ("trailing_whitespace",):
                trailing_ws_lines.add(issue.line)
            elif issue.kind in ("mixed_indentation", "tab_indentation"):
                tab_lines.add(issue.line)
            elif issue.kind == "unused_import":
                unused_import_lines.add(issue.line)

    patched: list[str] = []
    for i, line in enumerate(lines, start=1):
        if i in unused_import_lines:
            continue  # drop the line entirely
        if i in tab_lines:
            line = line.replace("\t", "    ")
        if i in trailing_ws_lines:
            eol = "\n" if line.endswith("\n") else ""
            line = line.rstrip() + eol
        patched.append(line)

    return "".join(patched)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the refactor engine.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake refactor",
        description="Detect and fix code-quality issues.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--apply", action="store_true", help="Apply fixes")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    parser.add_argument(
        "--max-line-len",
        type=int,
        default=120,
        help="Maximum allowed line length (default: 120)",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    reports = scan_repo(root, max_line_len=args.max_line_len)
    total_issues = sum(len(r.issues) for r in reports)
    fixable = sum(r.fixable_count for r in reports)

    for report in reports:
        if report.issues:
            print(f"\n{report.path}")
            for issue in report.issues:
                fix_tag = " [fixable]" if issue.fixable else ""
                print(f"  line {issue.line:>4}: [{issue.kind}] {issue.message}{fix_tag}")

    print(f"\nTotal issues: {total_issues}  ({fixable} fixable)")

    if args.apply and fixable:
        if not args.yes:
            ans = input("Apply all fixable issues? [y/N] ").strip().lower()
            if ans != "y":
                print("Aborted.")
                return 0
        written = 0
        for report in reports:
            if report.fixable_count:
                patched = apply_fixes(report)
                Path(report.path).write_text(patched, encoding="utf-8")
                written += 1
        print(f"Fixed {written} files.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
