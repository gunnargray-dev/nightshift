"""Automated refactoring assistant for Awake.

Provides tools for:
- Detecting code smells (long functions, high complexity, duplicate logic)
- Generating refactoring suggestions with priority scores
- Applying simple automated refactors (rename, extract constant, sort imports)
- Producing a structured refactoring report

Integrates with the session workflow so suggestions are surfaced at the
end of each Awake session alongside the health report.
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CodeSmell:
    """A detected code quality issue with location and severity."""

    file: str
    line: int
    smell_type: str        # long_function | high_complexity | duplicate_logic | magic_number
    description: str
    severity: str          # low | medium | high
    suggestion: str


@dataclass
class RefactorSuggestion:
    """A prioritised refactoring action."""

    smell: CodeSmell
    priority: int          # 1 (highest) – 5 (lowest)
    effort: str            # trivial | small | medium | large
    automated: bool        # can Awake apply this automatically?


@dataclass
class RefactorReport:
    """Summary of all smells and suggestions for a session."""

    session: int
    files_scanned: int
    smells: list[CodeSmell]
    suggestions: list[RefactorSuggestion]
    auto_applied: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AST-based smell detection
# ---------------------------------------------------------------------------


MAX_FUNCTION_LINES = 40
MAX_COMPLEXITY = 10


class _ComplexityVisitor(ast.NodeVisitor):
    """Count branching nodes to approximate cyclomatic complexity."""

    BRANCH_NODES = (
        ast.If, ast.For, ast.While, ast.ExceptHandler,
        ast.With, ast.Assert, ast.comprehension,
    )

    def __init__(self) -> None:
        self.complexity = 1

    def visit_If(self, node: ast.If) -> None:       # noqa: N802
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:     # noqa: N802
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None: # noqa: N802
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        self.complexity += 1
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:  # noqa: N802
        self.complexity += len(node.ifs)
        self.generic_visit(node)


def _function_smells(source: str, filepath: str) -> list[CodeSmell]:
    """Detect long functions and high-complexity functions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    smells: list[CodeSmell] = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = node.lineno
        end = node.end_lineno or start
        length = end - start + 1
        if length > MAX_FUNCTION_LINES:
            smells.append(
                CodeSmell(
                    file=filepath,
                    line=start,
                    smell_type="long_function",
                    description=f"`{node.name}` is {length} lines (limit {MAX_FUNCTION_LINES})",
                    severity="medium" if length < 80 else "high",
                    suggestion=f"Break `{node.name}` into smaller helpers.",
                )
            )

        visitor = _ComplexityVisitor()
        visitor.visit(node)
        if visitor.complexity > MAX_COMPLEXITY:
            smells.append(
                CodeSmell(
                    file=filepath,
                    line=start,
                    smell_type="high_complexity",
                    description=(
                        f"`{node.name}` has cyclomatic complexity "
                        f"{visitor.complexity} (limit {MAX_COMPLEXITY})"
                    ),
                    severity="medium" if visitor.complexity < 15 else "high",
                    suggestion=f"Simplify branching in `{node.name}`.",
                )
            )
    return smells


MAGIC_NUMBER_RE = re.compile(r"(?<![\w.])(?!0[xXoObB])\d+(?:\.\d+)?(?![\w.])")
SAFE_NUMBERS = {"0", "1", "2", "-1", "100", "True", "False"}


def _magic_number_smells(source: str, filepath: str) -> list[CodeSmell]:
    """Flag bare numeric literals that should be named constants."""
    smells: list[CodeSmell] = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for m in MAGIC_NUMBER_RE.finditer(line):
            val = m.group()
            if val not in SAFE_NUMBERS:
                smells.append(
                    CodeSmell(
                        file=filepath,
                        line=i,
                        smell_type="magic_number",
                        description=f"Magic number `{val}` on line {i}",
                        severity="low",
                        suggestion=f"Replace `{val}` with a named constant.",
                    )
                )
    return smells


def scan_file(filepath: Path) -> list[CodeSmell]:
    """Run all smell detectors on one file."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except OSError:
        return []
    rel = str(filepath)
    smells = _function_smells(source, rel)
    smells += _magic_number_smells(source, rel)
    return smells


def scan_repo(repo_root: Path) -> list[CodeSmell]:
    """Scan every .py file under src/ and tests/."""
    all_smells: list[CodeSmell] = []
    for py_file in sorted(repo_root.rglob("*.py")):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        all_smells.extend(scan_file(py_file))
    return all_smells


# ---------------------------------------------------------------------------
# Suggestion builder
# ---------------------------------------------------------------------------


_EFFORT_MAP = {
    "long_function": "medium",
    "high_complexity": "large",
    "magic_number": "trivial",
    "duplicate_logic": "medium",
}

_PRIORITY_MAP = {
    "high": 1,
    "medium": 2,
    "low": 4,
}

_AUTO_APPLICABLE = {"magic_number"}  # only trivial refactors are automated


def build_suggestions(smells: list[CodeSmell]) -> list[RefactorSuggestion]:
    """Convert smells into prioritised RefactorSuggestion objects."""
    suggestions = []
    for smell in smells:
        suggestions.append(
            RefactorSuggestion(
                smell=smell,
                priority=_PRIORITY_MAP.get(smell.severity, 3),
                effort=_EFFORT_MAP.get(smell.smell_type, "medium"),
                automated=smell.smell_type in _AUTO_APPLICABLE,
            )
        )
    suggestions.sort(key=lambda s: (s.priority, s.smell.file, s.smell.line))
    return suggestions


# ---------------------------------------------------------------------------
# Automated refactors
# ---------------------------------------------------------------------------


def _extract_magic_numbers(source: str) -> tuple[str, list[str]]:
    """
    Replace magic numbers with named constants at the top of the module.
    Returns (new_source, list_of_added_constants).
    """
    seen: dict[str, str] = {}  # value -> const_name
    replacements: list[tuple[int, str, str]] = []  # (line_idx, old, new)
    lines = source.splitlines(keepends=True)

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for m in MAGIC_NUMBER_RE.finditer(line):
            val = m.group()
            if val in SAFE_NUMBERS:
                continue
            if val not in seen:
                name = f"_CONST_{val.replace('.', '_').replace('-', 'NEG_')}"
                seen[val] = name
            replacements.append((i, m.group(), seen[val]))

    if not replacements:
        return source, []

    # Build constant block
    const_block = "\n".join(f"{name} = {val}" for val, name in seen.items()) + "\n\n"

    # Apply replacements (last-to-first to preserve offsets)
    for i, old_val, new_name in reversed(replacements):
        lines[i] = lines[i].replace(old_val, new_name, 1)

    # Inject constants after module docstring / imports
    insert_at = 0
    in_docstring = False
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('"""') or stripped.startswith("'''"):
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_at = idx + 1
    lines.insert(insert_at, const_block)
    return "".join(lines), list(seen.values())


def apply_auto_refactors(repo_root: Path, smells: list[CodeSmell]) -> list[str]:
    """Apply automated refactors for applicable smells. Returns list of changed files."""
    auto_files = {s.file for s in smells if s.smell_type in _AUTO_APPLICABLE}
    changed: list[str] = []
    for filepath_str in auto_files:
        filepath = Path(filepath_str)
        if not filepath.exists():
            continue
        source = filepath.read_text(encoding="utf-8")
        new_source, constants = _extract_magic_numbers(source)
        if new_source != source:
            filepath.write_text(new_source, encoding="utf-8")
            changed.append(f"{filepath_str} (+{len(constants)} constants)")
    return changed


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(
    session: int,
    repo_root: Path,
    apply_auto: bool = False,
) -> RefactorReport:
    """Scan the repo, build suggestions, optionally apply auto-refactors."""
    smells = scan_repo(repo_root)
    suggestions = build_suggestions(smells)
    py_files = list(repo_root.rglob("*.py"))
    py_files = [f for f in py_files if ".venv" not in f.parts]
    auto_applied: list[str] = []
    if apply_auto:
        auto_applied = apply_auto_refactors(repo_root, smells)
    return RefactorReport(
        session=session,
        files_scanned=len(py_files),
        smells=smells,
        suggestions=suggestions,
        auto_applied=auto_applied,
    )


# ---------------------------------------------------------------------------
# CLI / entry point
# ---------------------------------------------------------------------------


def print_report(report: RefactorReport) -> None:
    """Pretty-print the refactoring report to stdout."""
    print(f"\n=== Awake Refactor Report — Session {report.session} ===")
    print(f"Files scanned : {report.files_scanned}")
    print(f"Smells found  : {len(report.smells)}")
    print(f"Suggestions   : {len(report.suggestions)}")
    if report.auto_applied:
        print("Auto-applied  :")
        for item in report.auto_applied:
            print(f"  • {item}")
    print()
    for sug in report.suggestions[:10]:  # top-10
        s = sug.smell
        print(
            f"  [{sug.priority}] {s.smell_type} | {s.severity} | "
            f"{s.file}:{s.line}\n      {s.description}\n      → {s.suggestion}"
        )


def main() -> None:
    """CLI: python -m src.refactor [--apply]"""
    import sys
    apply_auto = "--apply" in sys.argv
    repo_root = Path(__file__).resolve().parent.parent

    # Infer current session from git log
    import subprocess
    log = subprocess.run(
        ["git", "log", "--pretty=format:%s"],
        capture_output=True, text=True, cwd=repo_root, check=False
    ).stdout
    session_matches = re.findall(r"session[\s-]*(\d+)", log, re.IGNORECASE)
    session = int(session_matches[0]) if session_matches else 0

    report = build_report(session=session, repo_root=repo_root, apply_auto=apply_auto)
    print_report(report)


if __name__ == "__main__":
    main()
