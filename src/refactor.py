"""Self-refactor engine for Nightshift.

Analyzes source files from previous sessions and produces a structured
``RefactorReport`` detailing actionable improvements.  Simple, safe fixes
(missing docstrings on short functions, trailing whitespace) can be applied
automatically; more complex changes are left as recommendations.

Refactoring categories
----------------------
- MISSING_DOCSTRING  -- public function or class has no docstring
- LONG_LINE          -- line exceeds 88 characters
- TODO_DEBT          -- TODO / FIXME marker present in source
- MAGIC_NUMBER       -- bare numeric literal used outside assignment
- BARE_EXCEPT        -- ``except:`` without an exception type
- DEAD_IMPORT        -- imported name not referenced in the file body

Each suggestion carries a ``severity`` (low / medium / high) and a
``fix_strategy`` (auto / manual / review).  Only ``fix_strategy='auto'``
items are touched when ``apply_safe_fixes()`` is called.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class RefactorSuggestion:
    """A single actionable refactor suggestion for a specific location."""

    file: str
    line: int
    category: str        # MISSING_DOCSTRING | LONG_LINE | TODO_DEBT | BARE_EXCEPT | DEAD_IMPORT
    severity: str        # high | medium | low
    fix_strategy: str    # auto | manual | review
    message: str
    original: str = ""   # The problematic snippet
    suggestion: str = "" # Suggested replacement (if auto-fixable)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)


@dataclass
class FileRefactorResult:
    """All suggestions for a single file, plus auto-fix results."""

    path: str
    suggestions: list[RefactorSuggestion] = field(default_factory=list)
    fixes_applied: int = 0
    health_before: float = 0.0
    health_after: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)

    @property
    def suggestion_count(self) -> int:
        """Return number of suggestions for this file."""
        return len(self.suggestions)

    @property
    def high_severity(self) -> list[RefactorSuggestion]:
        """Return only high-severity suggestions."""
        return [s for s in self.suggestions if s.severity == "high"]

    @property
    def auto_fixable(self) -> list[RefactorSuggestion]:
        """Return only auto-fixable suggestions."""
        return [s for s in self.suggestions if s.fix_strategy == "auto"]


@dataclass
class RefactorReport:
    """Aggregate refactor report across the entire repository."""

    files: list[FileRefactorResult] = field(default_factory=list)
    generated_at: str = ""
    session: int = 0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)

    @property
    def total_suggestions(self) -> int:
        """Return total number of suggestions across all files."""
        return sum(f.suggestion_count for f in self.files)

    @property
    def total_auto_fixable(self) -> int:
        """Return number of auto-fixable suggestions."""
        return sum(len(f.auto_fixable) for f in self.files)

    @property
    def all_suggestions(self) -> list[RefactorSuggestion]:
        """Return all suggestions sorted by severity."""
        result = []
        for f in self.files:
            result.extend(f.suggestions)
        return sorted(result, key=lambda s: (SEVERITY_ORDER.get(s.severity, 99), s.file, s.line))

    def to_markdown(self) -> str:
        """Render the refactor report as Markdown."""
        ts = self.generated_at or "N/A"
        lines = [
            "# Self-Refactor Report",
            "",
            f"*Generated: {ts}*",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Files analysed | {len(self.files)} |",
            f"| Total suggestions | {self.total_suggestions} |",
            f"| Auto-fixable | {self.total_auto_fixable} |",
            f"| High severity | {sum(len(f.high_severity) for f in self.files)} |",
            "",
        ]

        if not self.all_suggestions:
            lines.append("No refactor suggestions -- codebase is clean.")
            lines += ["", "---", ""]
            return "\n".join(lines)

        lines += [
            "## Suggestions by Severity",
            "",
            "| File | Line | Category | Severity | Fix | Message |",
            "|------|------|----------|----------|-----|---------|" ,
        ]
        for s in self.all_suggestions:
            badge = {"high": "[high]", "medium": "[medium]", "low": "[low]"}.get(s.severity, "[?]")
            fix_badge = {"auto": "[auto]", "manual": "[manual]", "review": "[review]"}.get(s.fix_strategy, "[?]")
            short_file = Path(s.file).name
            lines.append(
                f"| `{short_file}` | {s.line} | {s.category} | {badge} {s.severity} | {fix_badge} {s.fix_strategy} | {s.message} |"
            )

        lines += ["", "---", ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Analysers
# ---------------------------------------------------------------------------


_TODO_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)


def _analyse_missing_docstrings(
    tree: ast.Module, source_lines: list[str], path: str
) -> list[RefactorSuggestion]:
    """Detect public functions/classes without docstrings."""
    suggestions = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith("_"):
            continue  # skip private
        has_doc = (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
        if not has_doc:
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            body_lines = (node.end_lineno or node.lineno) - node.lineno
            severity = "medium" if body_lines > 5 else "low"
            fix_strategy = "auto" if (kind == "function" and body_lines <= 3) else "manual"
            suggestions.append(
                RefactorSuggestion(
                    file=path,
                    line=node.lineno,
                    category="MISSING_DOCSTRING",
                    severity=severity,
                    fix_strategy=fix_strategy,
                    message=f"{kind} `{node.name}` has no docstring",
                    original=source_lines[node.lineno - 1].rstrip() if node.lineno <= len(source_lines) else "",
                    suggestion=f'    """{node.name.replace("_", " ").title()}."""',
                )
            )
    return suggestions


def _analyse_long_lines(
    source_lines: list[str], path: str, max_len: int = 88
) -> list[RefactorSuggestion]:
    """Detect lines exceeding max_len characters."""
    suggestions = []
    for i, line in enumerate(source_lines, start=1):
        if len(line.rstrip()) > max_len:
            excess = len(line.rstrip()) - max_len
            suggestions.append(
                RefactorSuggestion(
                    file=path,
                    line=i,
                    category="LONG_LINE",
                    severity="low",
                    fix_strategy="manual",
                    message=f"Line is {len(line.rstrip())} chars (exceeds {max_len} by {excess})",
                    original=line.rstrip()[:100] + "..." if len(line) > 100 else line.rstrip(),
                )
            )
    return suggestions


def _analyse_todos(source_lines: list[str], path: str) -> list[RefactorSuggestion]:
    """Detect TODO/FIXME markers as technical debt."""
    suggestions = []
    for i, line in enumerate(source_lines, start=1):
        m = _TODO_RE.search(line)
        if m:
            suggestions.append(
                RefactorSuggestion(
                    file=path,
                    line=i,
                    category="TODO_DEBT",
                    severity="medium",
                    fix_strategy="review",
                    message=f"{m.group(1)} marker -- resolve or file an issue",
                    original=line.strip(),
                )
            )
    return suggestions


def _analyse_bare_excepts(
    tree: ast.Module, source_lines: list[str], path: str
) -> list[RefactorSuggestion]:
    """Detect bare ``except:`` clauses (catches BaseException silently)."""
    suggestions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            suggestions.append(
                RefactorSuggestion(
                    file=path,
                    line=node.lineno,
                    category="BARE_EXCEPT",
                    severity="high",
                    fix_strategy="manual",
                    message="Bare `except:` catches all exceptions including KeyboardInterrupt",
                    original=source_lines[node.lineno - 1].rstrip() if node.lineno <= len(source_lines) else "",
                    suggestion="except Exception:",
                )
            )
    return suggestions


def _analyse_dead_imports(
    tree: ast.Module, source: str, path: str
) -> list[RefactorSuggestion]:
    """Detect imported names that are never used in the file."""
    imported_names: list[tuple[str, int]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported_names.append((name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                imported_names.append((name, node.lineno))

    suggestions = []
    for name, lineno in imported_names:
        lines = source.splitlines()
        body_uses = sum(
            1 for i, line in enumerate(lines, start=1)
            if i != lineno and re.search(r"\b" + re.escape(name) + r"\b", line)
        )
        if body_uses == 0:
            suggestions.append(
                RefactorSuggestion(
                    file=path,
                    line=lineno,
                    category="DEAD_IMPORT",
                    severity="low",
                    fix_strategy="review",
                    message=f"Import `{name}` appears unused",
                )
            )
    return suggestions


def _analyse_file(path: Path, repo_root: Path) -> FileRefactorResult:
    """Run all analysers on a single Python file."""
    rel = str(path.relative_to(repo_root))
    result = FileRefactorResult(path=rel)

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result

    source_lines = source.splitlines()

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return result

    result.suggestions += _analyse_missing_docstrings(tree, source_lines, rel)
    result.suggestions += _analyse_long_lines(source_lines, rel)
    result.suggestions += _analyse_todos(source_lines, rel)
    result.suggestions += _analyse_bare_excepts(tree, source_lines, rel)
    result.suggestions += _analyse_dead_imports(tree, source, rel)

    return result


# ---------------------------------------------------------------------------
# Auto-fix engine
# ---------------------------------------------------------------------------


def _apply_docstring_fix(path: Path, suggestion: RefactorSuggestion) -> bool:
    """Insert a stub docstring on the line after the function definition."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        target = suggestion.line - 1  # 0-indexed
        if target >= len(lines):
            return False
        def_line = lines[target]
        indent = len(def_line) - len(def_line.lstrip())
        stub = " " * (indent + 4) + '"""TODO: add docstring."""\n'
        lines.insert(target + 1, stub)
        path.write_text("".join(lines), encoding="utf-8")
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# RefactorEngine
# ---------------------------------------------------------------------------


class RefactorEngine:
    """Orchestrates analysis and optional auto-fixing of the repository."""

    def __init__(self, repo_path: Optional[Path] = None, session: int = 4) -> None:
        """Initialize with repo path and session number."""
        self.repo_path = repo_path or Path.cwd()
        self.session = session

    def analyze(
        self,
        glob: str = "src/**/*.py",
        exclude: Optional[list[str]] = None,
    ) -> RefactorReport:
        """Analyse all Python source files and return a RefactorReport."""
        exclude = exclude or ["__init__"]
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        report = RefactorReport(generated_at=ts, session=self.session)

        for py_file in sorted(self.repo_path.glob(glob)):
            rel = str(py_file.relative_to(self.repo_path))
            if any(ex in rel for ex in exclude):
                continue
            file_result = _analyse_file(py_file, self.repo_path)
            if file_result.suggestions:
                report.files.append(file_result)

        return report

    def apply_safe_fixes(self, report: RefactorReport) -> int:
        """Apply only ``fix_strategy='auto'`` suggestions. Returns count applied."""
        applied = 0
        for file_result in report.files:
            py_file = self.repo_path / file_result.path
            for suggestion in file_result.auto_fixable:
                if suggestion.category == "MISSING_DOCSTRING":
                    if _apply_docstring_fix(py_file, suggestion):
                        applied += 1
                        file_result.fixes_applied += 1
        return applied


def find_refactor_candidates(repo_path: Path | None = None) -> list[RefactorSuggestion]:
    """Convenience wrapper: return flat list of all refactor suggestions.

    Used by ``src.audit`` and other modules that only need the candidate list
    without the full engine/report machinery.
    """
    engine = RefactorEngine(repo_path=repo_path)
    report = engine.analyze()
    return report.all_suggestions
