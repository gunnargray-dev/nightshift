"""AI-powered refactoring engine for Python source files."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RefactorConfig:
    """Configuration for the refactoring engine."""

    model: str = "gpt-4o-mini"
    rules: Optional[list[str]] = None  # None = all rules
    dry_run: bool = False
    max_function_lines: int = 50
    max_complexity: int = 10
    rename_threshold: float = 0.85  # similarity threshold for rename suggestions


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _find_long_functions(
    tree: ast.Module, source_lines: list[str], max_lines: int
) -> list[dict[str, Any]]:
    """Find functions that exceed *max_lines* lines."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = (node.end_lineno or 0) - node.lineno + 1
            if length > max_lines:
                issues.append(
                    {
                        "rule": "long-function",
                        "name": node.name,
                        "line": node.lineno,
                        "length": length,
                        "suggestion": f"Split into smaller functions (currently {length} lines).",
                    }
                )
    return issues


def _cyclomatic_complexity(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Compute a simple approximation of cyclomatic complexity."""
    count = 1
    for child in ast.walk(node):
        if isinstance(
            child,
            (
                ast.If,
                ast.While,
                ast.For,
                ast.ExceptHandler,
                ast.With,
                ast.AsyncWith,
                ast.AsyncFor,
                ast.comprehension,
            ),
        ):
            count += 1
        elif isinstance(child, ast.BoolOp):
            count += len(child.values) - 1
    return count


def _find_complex_functions(
    tree: ast.Module, max_complexity: int
) -> list[dict[str, Any]]:
    """Find functions with high cyclomatic complexity."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            cc = _cyclomatic_complexity(node)
            if cc > max_complexity:
                issues.append(
                    {
                        "rule": "high-complexity",
                        "name": node.name,
                        "line": node.lineno,
                        "complexity": cc,
                        "suggestion": f"Reduce complexity (currently {cc}, threshold {max_complexity}).",
                    }
                )
    return issues


def _find_magic_numbers(tree: ast.Module) -> list[dict[str, Any]]:
    """Flag numeric literals that are not 0, 1, or -1."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if node.value not in (0, 1, -1, 0.0, 1.0, -1.0, 100, 1000):
                issues.append(
                    {
                        "rule": "magic-number",
                        "value": node.value,
                        "line": node.lineno,
                        "suggestion": "Replace with a named constant.",
                    }
                )
    return issues


def _find_bare_excepts(tree: ast.Module) -> list[dict[str, Any]]:
    """Flag bare except clauses."""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(
                {
                    "rule": "bare-except",
                    "line": node.lineno,
                    "suggestion": "Specify the exception type(s) to catch.",
                }
            )
    return issues


def _find_unused_imports(tree: ast.Module, source: str) -> list[dict[str, Any]]:
    """Heuristically find imported names that are never used."""
    issues = []
    imported_names: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported_names.append((name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                name = alias.asname or alias.name
                if name != "*":
                    imported_names.append((name, node.lineno))

    for name, lineno in imported_names:
        # Count occurrences outside the import line itself
        occurrences = len(re.findall(rf"\b{re.escape(name)}\b", source))
        if occurrences <= 1:  # only the import statement itself
            issues.append(
                {
                    "rule": "unused-import",
                    "name": name,
                    "line": lineno,
                    "suggestion": f"Remove unused import {name!r}.",
                }
            )
    return issues


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class RefactorEngine:
    """Runs configured refactoring rules against Python source files."""

    ALL_RULES = {
        "long-function",
        "high-complexity",
        "magic-number",
        "bare-except",
        "unused-import",
    }

    def __init__(self, config: Optional[RefactorConfig] = None) -> None:
        self.config = config or RefactorConfig()
        self.active_rules = (
            set(self.config.rules) if self.config.rules else self.ALL_RULES
        )

    def analyse_source(self, source: str, path: str = "<string>") -> list[dict[str, Any]]:
        """Run all active rules on *source* and return a list of issues."""
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return [{"rule": "syntax-error", "line": exc.lineno, "message": str(exc)}]

        issues: list[dict[str, Any]] = []
        source_lines = source.splitlines()

        if "long-function" in self.active_rules:
            issues += _find_long_functions(tree, source_lines, self.config.max_function_lines)
        if "high-complexity" in self.active_rules:
            issues += _find_complex_functions(tree, self.config.max_complexity)
        if "magic-number" in self.active_rules:
            issues += _find_magic_numbers(tree)
        if "bare-except" in self.active_rules:
            issues += _find_bare_excepts(tree)
        if "unused-import" in self.active_rules:
            issues += _find_unused_imports(tree, source)

        for issue in issues:
            issue["path"] = path

        return issues

    def run(self, root: Path, glob: str = "**/*.py") -> list[dict[str, Any]]:
        """Analyse all Python files under *root*."""
        all_issues: list[dict[str, Any]] = []
        for py_file in sorted(root.glob(glob)):
            if py_file.is_file():
                source = py_file.read_text(encoding="utf-8", errors="replace")
                all_issues += self.analyse_source(source, str(py_file))
        return all_issues
