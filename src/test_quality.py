"""Test quality analyser for Awake."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class TestQualityConfig:
    """Configuration for test quality analysis."""

    model: str = "gpt-4o-mini"
    threshold: float = 0.7
    include_coverage: bool = False
    check_assertions: bool = True
    check_naming: bool = True
    check_isolation: bool = True


# ---------------------------------------------------------------------------
# AST-based checks
# ---------------------------------------------------------------------------


def _count_assertions(func_node: ast.FunctionDef) -> int:
    """Count assert statements and self.assert* calls in a test function."""
    count = 0
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assert):
            count += 1
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr.startswith("assert"):
                    count += 1
    return count


def _has_setup_teardown(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in ("setUp", "tearDown", "setup_method", "teardown_method",
                             "setup_function", "teardown_function"):
                return True
    return False


def _uses_mocks(source: str) -> bool:
    return bool(re.search(r"\b(mock|Mock|MagicMock|patch|mocker)\b", source))


def _check_test_isolation(tree: ast.Module, source: str) -> list[dict[str, Any]]:
    """Check for common test isolation issues."""
    issues = []
    # Check for global state mutation
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            issues.append(
                {
                    "type": "global-state",
                    "line": node.lineno,
                    "message": "Test uses global statement; may affect isolation.",
                }
            )
    return issues


def _analyse_test_file(path: Path) -> dict[str, Any]:
    """Analyse a single test file."""
    source = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"path": str(path), "error": str(exc)}

    test_functions: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            assertions = _count_assertions(node)
            func_info = {
                "name": node.name,
                "line": node.lineno,
                "assertions": assertions,
                "has_docstring": (
                    bool(node.body)
                    and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                ),
            }
            if assertions == 0:
                func_info["warning"] = "No assertions found."
            test_functions.append(func_info)

    isolation_issues = _check_test_isolation(tree, source)

    return {
        "path": str(path),
        "test_count": len(test_functions),
        "has_setup_teardown": _has_setup_teardown(tree),
        "uses_mocks": _uses_mocks(source),
        "isolation_issues": isolation_issues,
        "functions": test_functions,
    }


def analyze_test_quality(
    root: Path,
    config: Optional[TestQualityConfig] = None,
    glob_pattern: str = "**/test_*.py",
) -> list[dict[str, Any]]:
    """Analyse all test files under *root*."""
    cfg = config or TestQualityConfig()
    results = []
    for test_file in sorted(root.glob(glob_pattern)):
        if test_file.is_file():
            results.append(_analyse_test_file(test_file))
    return results
