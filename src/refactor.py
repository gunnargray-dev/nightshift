"""Automated refactoring suggestions for Awake.

This module analyses Python source files and produces a ranked list of
refactoring suggestions. It is intentionally dependency-free and operates
purely through ``ast`` and ``pathlib``.

Suggestion categories
---------------------
- **long_function**: Functions longer than a configurable line threshold.
- **deep_nesting**: Code nested more than N levels deep.
- **duplicate_logic**: Identical or near-identical small functions.
- **large_module**: Modules that exceed a line threshold.
- **missing_docstring**: Public functions / classes without docstrings.
- **magic_numbers**: Numeric literals that should be named constants.
- **complex_condition**: Boolean expressions with too many operands.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RefactorSuggestion:
    """A single refactoring suggestion."""
    file: str
    line: int
    category: str
    severity: str  # low | medium | high
    message: str
    snippet: str = ""
    effort_minutes: int = 10

    def to_dict(self) -> dict:
        """Return a plain dictionary suitable for JSON serialisation."""
        return {
            "file": self.file,
            "line": self.line,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "snippet": self.snippet,
            "effort_minutes": self.effort_minutes,
        }


@dataclass
class RefactorReport:
    """Aggregated refactoring report for one or more files."""
    suggestions: list[RefactorSuggestion] = field(default_factory=list)
    files_analysed: int = 0
    total_effort_minutes: int = 0

    def to_dict(self) -> dict:
        """Return a plain dictionary suitable for JSON serialisation."""
        by_severity: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        by_category: dict[str, int] = {}
        for s in self.suggestions:
            by_severity[s.severity] = by_severity.get(s.severity, 0) + 1
            by_category[s.category] = by_category.get(s.category, 0) + 1
        return {
            "suggestions": [s.to_dict() for s in self.suggestions],
            "total": len(self.suggestions),
            "files_analysed": self.files_analysed,
            "total_effort_minutes": self.total_effort_minutes,
            "by_severity": by_severity,
            "by_category": by_category,
        }

    def to_markdown(self) -> str:
        """Render the report as Markdown."""
        if not self.suggestions:
            return "## Refactoring Suggestions\n\nNo suggestions found."
        lines = [
            "## Refactoring Suggestions",
            "",
            f"Analysed {self.files_analysed} file(s) -- "
            f"{len(self.suggestions)} suggestion(s) "
            f"(~{self.total_effort_minutes} min total effort)",
            "",
            "| File | Line | Severity | Category | Message |",
            "|------|------|----------|----------|---------|",
        ]
        for s in sorted(self.suggestions, key=lambda x: (x.severity == "low", x.severity == "medium", x.file, x.line)):
            sev_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.severity, "")
            lines.append(f"| `{s.file}` | {s.line} | {sev_icon} {s.severity} | {s.category} | {s.message} |")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AST visitors
# ---------------------------------------------------------------------------

class _NestingVisitor(ast.NodeVisitor):
    """Compute maximum nesting depth of a function body."""

    def __init__(self) -> None:
        self.max_depth = 0
        self._depth = 0

    def _enter(self, node: ast.AST) -> None:
        self._depth += 1
        self.max_depth = max(self.max_depth, self._depth)
        self.generic_visit(node)
        self._depth -= 1

    visit_If = visit_For = visit_While = visit_With = visit_Try = _enter  # type: ignore[assignment]


class _MagicNumberVisitor(ast.NodeVisitor):
    """Collect numeric literals that look like magic numbers."""

    ALLOWED = {0, 1, -1, 2, 100}

    def __init__(self) -> None:
        self.hits: list[tuple[int, float]] = []  # (line, value)

    def visit_Constant(self, node: ast.Constant) -> None:  # noqa: N802
        if isinstance(node.value, (int, float)) and node.value not in self.ALLOWED:
            self.hits.append((node.lineno, node.value))
        self.generic_visit(node)


class _BoolComplexityVisitor(ast.NodeVisitor):
    """Find boolean expressions with many operands."""

    def __init__(self, threshold: int = 4) -> None:
        self.threshold = threshold
        self.hits: list[tuple[int, int]] = []  # (line, operand_count)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:  # noqa: N802
        if len(node.values) >= self.threshold:
            self.hits.append((node.lineno, len(node.values)))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Per-file analysis
# ---------------------------------------------------------------------------

def _analyse_file(
    path: Path,
    rel: str,
    long_fn_lines: int,
    deep_nest: int,
    magic_threshold: int,
    bool_threshold: int,
) -> list[RefactorSuggestion]:
    """Analyse a single Python file and return suggestions."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    suggestions: list[RefactorSuggestion] = []
    lines = source.splitlines()
    module_lines = len(lines)

    if module_lines > 500:
        suggestions.append(RefactorSuggestion(
            file=rel, line=1, category="large_module", severity="medium",
            message=f"Module has {module_lines} lines; consider splitting it.",
            effort_minutes=30,
        ))

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        name = node.name
        start = node.lineno
        end = getattr(node, "end_lineno", start)
        fn_lines = end - start + 1

        # Missing docstring
        if (not node.body or
                not isinstance(node.body[0], ast.Expr) or
                not isinstance(node.body[0].value, ast.Constant)):
            if not name.startswith("_"):
                suggestions.append(RefactorSuggestion(
                    file=rel, line=start, category="missing_docstring", severity="low",
                    message=f"Public function `{name}` has no docstring.",
                    effort_minutes=5,
                ))

        # Long function
        if fn_lines > long_fn_lines:
            suggestions.append(RefactorSuggestion(
                file=rel, line=start, category="long_function", severity="medium",
                message=f"`{name}` is {fn_lines} lines (threshold: {long_fn_lines}).",
                effort_minutes=20,
            ))

        # Deep nesting
        nv = _NestingVisitor()
        nv.visit(node)
        if nv.max_depth > deep_nest:
            suggestions.append(RefactorSuggestion(
                file=rel, line=start, category="deep_nesting", severity="medium",
                message=f"`{name}` has nesting depth {nv.max_depth} (threshold: {deep_nest}).",
                effort_minutes=15,
            ))

        # Magic numbers
        mv = _MagicNumberVisitor()
        mv.visit(node)
        if len(mv.hits) > magic_threshold:
            lines_hit = sorted({h[0] for h in mv.hits})
            suggestions.append(RefactorSuggestion(
                file=rel, line=lines_hit[0], category="magic_numbers", severity="low",
                message=f"`{name}` contains {len(mv.hits)} magic number literal(s).",
                effort_minutes=10,
            ))

        # Complex boolean
        bv = _BoolComplexityVisitor(threshold=bool_threshold)
        bv.visit(node)
        for line_no, count in bv.hits:
            suggestions.append(RefactorSuggestion(
                file=rel, line=line_no, category="complex_condition", severity="medium",
                message=f"Boolean expression with {count} operands in `{name}`.",
                effort_minutes=10,
            ))

    return suggestions


# ---------------------------------------------------------------------------
# Duplicate-logic detection (heuristic)
# ---------------------------------------------------------------------------

def _fn_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Produce a normalised hash of a small function's body."""
    try:
        src = ast.unparse(node)
    except Exception:
        return ""
    # Strip the function header so only the body hash matters
    body_lines = src.splitlines()[1:]
    normalised = "\n".join(l.strip() for l in body_lines if l.strip())
    return hashlib.md5(normalised.encode()).hexdigest() if normalised else ""


def _detect_duplicates(path: Path, rel: str) -> list[RefactorSuggestion]:
    """Detect near-identical small functions within a file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
    except SyntaxError:
        return []
    seen: dict[str, tuple[str, int]] = {}  # hash -> (name, line)
    suggestions: list[RefactorSuggestion] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        if end - node.lineno > 20:  # only flag small functions
            continue
        sig = _fn_signature(node)
        if not sig:
            continue
        if sig in seen:
            prev_name, prev_line = seen[sig]
            suggestions.append(RefactorSuggestion(
                file=rel, line=node.lineno, category="duplicate_logic", severity="high",
                message=f"`{node.name}` appears to duplicate `{prev_name}` (line {prev_line}).",
                effort_minutes=15,
            ))
        else:
            seen[sig] = (node.name, node.lineno)
    return suggestions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse_refactoring(
    repo_root: Path,
    *,
    long_fn_lines: int = 60,
    deep_nest: int = 4,
    magic_threshold: int = 3,
    bool_threshold: int = 4,
    include_tests: bool = False,
) -> RefactorReport:
    """Analyse all Python source files in *repo_root* for refactoring opportunities.

    Parameters
    ----------
    repo_root:
        Repository root directory.
    long_fn_lines:
        Flag functions longer than this many lines.
    deep_nest:
        Flag nesting deeper than this level.
    magic_threshold:
        Flag functions with more than this many magic-number literals.
    bool_threshold:
        Flag boolean expressions with this many or more operands.
    include_tests:
        Whether to include test files in the analysis.
    """
    src_dir = repo_root / "src"
    if not src_dir.exists():
        src_dir = repo_root
    py_files = sorted(src_dir.rglob("*.py"))
    if not include_tests:
        py_files = [p for p in py_files if "test" not in p.name.lower()]

    report = RefactorReport()
    for path in py_files:
        rel = str(path.relative_to(repo_root))
        report.suggestions.extend(
            _analyse_file(path, rel, long_fn_lines, deep_nest, magic_threshold, bool_threshold)
        )
        report.suggestions.extend(_detect_duplicates(path, rel))
        report.files_analysed += 1

    report.total_effort_minutes = sum(s.effort_minutes for s in report.suggestions)
    return report
