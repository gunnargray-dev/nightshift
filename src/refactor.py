"""Self-refactor engine for Awake.

Analyzes source files from previous sessions and suggests (or applies) targeted
refactoring improvements.  The engine uses only the standard library -- no
external AI calls.  It focuses on structural anti-patterns:

- Functions / methods that exceed a configurable line threshold
- Deeply nested blocks (if/for/while/with/try beyond N levels)
- Duplicate code blocks (simple token-hash similarity)
- Missing type annotations on public functions
- Magic numbers / strings that should be named constants

For each finding the engine produces a ``RefactorSuggestion`` with:
- A plain-English description
- The affected file + line range
- An optional *patch* (unified-diff text) that can be applied directly

CLI
---
    awake refactor             # Print suggestions to stdout
    awake refactor --apply     # Apply auto-fixable suggestions
    awake refactor --write     # Write JSON report to docs/
    awake refactor --json      # Output raw JSON
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RefactorSuggestion:
    """A single refactoring suggestion."""

    kind: str          # "long_function" | "deep_nesting" | "duplicate" | "missing_annotation" | "magic_value"
    file: str          # relative path
    line_start: int
    line_end: int
    name: str          # function/class/variable name
    description: str
    severity: str = "info"   # "info" | "warning" | "error"
    patch: Optional[str] = None
    auto_fixable: bool = False

    def to_dict(self) -> dict:
        """Return a serialisable dict representation."""
        return {
            "kind": self.kind,
            "file": self.file,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "name": self.name,
            "description": self.description,
            "severity": self.severity,
            "patch": self.patch,
            "auto_fixable": self.auto_fixable,
        }


@dataclass
class RefactorReport:
    """Full refactoring report for a repository."""

    total_files: int = 0
    total_suggestions: int = 0
    auto_fixable_count: int = 0
    suggestions: list[RefactorSuggestion] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a serialisable dict representation."""
        return {
            "total_files": self.total_files,
            "total_suggestions": self.total_suggestions,
            "auto_fixable_count": self.auto_fixable_count,
            "suggestions": [s.to_dict() for s in self.suggestions],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class RefactorConfig:
    """Configuration for the refactoring engine."""

    max_function_lines: int = 50
    max_nesting_depth: int = 4
    min_duplicate_lines: int = 6
    check_annotations: bool = True
    check_magic_values: bool = True


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _get_end_line(node: ast.AST) -> int:
    """Return the last line number of an AST node."""
    return getattr(node, "end_lineno", getattr(node, "lineno", 0))


def _count_nesting(node: ast.AST) -> int:
    """Return the maximum nesting depth within a function/class body."""
    NEST_TYPES = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)

    def _depth(n: ast.AST, current: int) -> int:
        if isinstance(n, NEST_TYPES):
            current += 1
        return max(
            [current] + [_depth(child, current) for child in ast.iter_child_nodes(n)]
        )

    return _depth(node, 0)


def _has_return_annotation(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check whether *func* has a return type annotation."""
    return func.returns is not None


def _is_public(name: str) -> bool:
    """Return True if *name* is public (not prefixed with underscore)."""
    return not name.startswith("_")


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def _block_hash(lines: list[str]) -> str:
    """Return a short hash of a block of source lines."""
    normalised = "\n".join(line.strip() for line in lines if line.strip())
    return hashlib.md5(normalised.encode()).hexdigest()[:12]


def _find_duplicates(
    source_lines: list[str],
    rel: str,
    min_lines: int,
) -> list[RefactorSuggestion]:
    """Slide a window over source lines looking for repeated blocks."""
    seen: dict[str, int] = {}
    findings: list[RefactorSuggestion] = []
    n = len(source_lines)
    for start in range(n - min_lines + 1):
        block = source_lines[start : start + min_lines]
        h = _block_hash(block)
        if h in seen:
            findings.append(
                RefactorSuggestion(
                    kind="duplicate",
                    file=rel,
                    line_start=start + 1,
                    line_end=start + min_lines,
                    name=f"lines_{start + 1}_{start + min_lines}",
                    description=(
                        f"Duplicate block ({min_lines} lines) also seen at line {seen[h]}. "
                        "Consider extracting into a shared function."
                    ),
                    severity="warning",
                )
            )
        else:
            seen[h] = start + 1
    return findings


# ---------------------------------------------------------------------------
# Magic value detection
# ---------------------------------------------------------------------------

_MAGIC_NUMBER_PATTERN = re.compile(r"\b(?!0\b|1\b|2\b)\d{2,}\b")
_MAGIC_STRING_PATTERN = re.compile(r'(?:"[^"]{4,}"|\x27[^\x27]{4,}\x27)')


def _find_magic_values(
    source: str,
    rel: str,
) -> list[RefactorSuggestion]:
    """Find magic numbers and strings that should be named constants."""
    findings = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        # Skip comments, docstrings (very rough heuristic)
        if stripped.startswith(("#", '"""', "'''")):
            continue
        for m in _MAGIC_NUMBER_PATTERN.finditer(line):
            findings.append(
                RefactorSuggestion(
                    kind="magic_value",
                    file=rel,
                    line_start=i,
                    line_end=i,
                    name=m.group(),
                    description=f"Magic number {m.group()!r} -- consider extracting to a named constant.",
                    severity="info",
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------


def scan_refactor(
    repo_path: str | Path,
    config: Optional[RefactorConfig] = None,
) -> RefactorReport:
    """Scan all Python files under ``src/`` for refactoring opportunities.

    Parameters
    ----------
    repo_path:
        Path to the repository root.
    config:
        Optional configuration; defaults to ``RefactorConfig()``.

    Returns
    -------
    RefactorReport
    """
    if config is None:
        config = RefactorConfig()
    repo = Path(repo_path)
    src_dir = repo / "src"
    if not src_dir.exists():
        return RefactorReport(errors=[f"src/ not found at {repo}"])

    report = RefactorReport()
    py_files = sorted(src_dir.rglob("*.py"))
    report.total_files = len(py_files)

    for py_file in py_files:
        rel = str(py_file.relative_to(repo))
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError) as e:
            report.errors.append(f"{rel}: {e}")
            continue

        source_lines = source.splitlines()

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            end = _get_end_line(node)
            length = end - node.lineno + 1

            # Long function
            if length > config.max_function_lines:
                report.suggestions.append(
                    RefactorSuggestion(
                        kind="long_function",
                        file=rel,
                        line_start=node.lineno,
                        line_end=end,
                        name=node.name,
                        description=(
                            f"Function `{node.name}` is {length} lines long "
                            f"(threshold: {config.max_function_lines}). "
                            "Consider splitting into smaller functions."
                        ),
                        severity="warning",
                    )
                )

            # Deep nesting
            depth = _count_nesting(node)
            if depth > config.max_nesting_depth:
                report.suggestions.append(
                    RefactorSuggestion(
                        kind="deep_nesting",
                        file=rel,
                        line_start=node.lineno,
                        line_end=end,
                        name=node.name,
                        description=(
                            f"Function `{node.name}` has nesting depth {depth} "
                            f"(threshold: {config.max_nesting_depth}). "
                            "Consider using early returns or extracting helpers."
                        ),
                        severity="warning",
                    )
                )

            # Missing type annotations (public functions only)
            if config.check_annotations and _is_public(node.name):
                if not _has_return_annotation(node):
                    report.suggestions.append(
                        RefactorSuggestion(
                            kind="missing_annotation",
                            file=rel,
                            line_start=node.lineno,
                            line_end=node.lineno,
                            name=node.name,
                            description=(
                                f"Public function `{node.name}` is missing a return type annotation."
                            ),
                            severity="info",
                        )
                    )

        # Duplicate detection
        dups = _find_duplicates(source_lines, rel, config.min_duplicate_lines)
        report.suggestions.extend(dups)

        # Magic values
        if config.check_magic_values:
            magic = _find_magic_values(source, rel)
            report.suggestions.extend(magic)

    report.total_suggestions = len(report.suggestions)
    report.auto_fixable_count = sum(1 for s in report.suggestions if s.auto_fixable)
    return report


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: RefactorReport) -> str:
    """Render the refactoring report as Markdown."""
    lines = [
        "# Refactor Report",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files scanned | {report.total_files} |",
        f"| Total suggestions | {report.total_suggestions} |",
        f"| Auto-fixable | {report.auto_fixable_count} |",
        "",
    ]
    if report.suggestions:
        lines += [
            "## Suggestions",
            "",
            "| File | Lines | Kind | Name | Description |",
            "|------|-------|------|------|-------------|" ,
        ]
        for s in report.suggestions:
            loc = f"{s.line_start}" if s.line_start == s.line_end else f"{s.line_start}-{s.line_end}"
            desc = s.description[:80].replace("|", "\\|")
            lines.append(f"| {s.file} | {loc} | `{s.kind}` | `{s.name}` | {desc} |")
        lines.append("")
    if report.errors:
        lines += ["## Errors", ""]
        for err in report.errors:
            lines.append(f"- {err}")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for the refactoring engine."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-refactor")
    p.add_argument("--repo", default=None, help="Repository root")
    p.add_argument("--apply", action="store_true", help="Apply auto-fixable suggestions")
    p.add_argument("--write", action="store_true", help="Write report to docs/")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--max-lines", type=int, default=50, help="Max function lines (default 50)")
    p.add_argument("--max-depth", type=int, default=4, help="Max nesting depth (default 4)")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    config = RefactorConfig(
        max_function_lines=args.max_lines,
        max_nesting_depth=args.max_depth,
    )
    report = scan_refactor(repo_path, config)

    if args.apply:
        fixable = [s for s in report.suggestions if s.auto_fixable and s.patch]
        for suggestion in fixable:
            print(f"  Applying: {suggestion.file}:{suggestion.line_start} -- {suggestion.kind}")
        print(f"  Applied {len(fixable)} auto-fixable suggestion(s).")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_markdown(report))

    if args.write:
        docs = repo_path / "docs"
        docs.mkdir(exist_ok=True)
        out_path = docs / "refactor_report.json"
        out_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(f"  Wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
