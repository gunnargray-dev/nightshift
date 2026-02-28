"""Cyclomatic complexity tracker for Nightshift.

Computes McCabe cyclomatic complexity for every function/method in src/.
Tracks complexity over time using a JSON history file, renders trend tables
with Unicode sparklines, and flags functions that exceed configurable
thresholds.

Complexity rating:
    1–5     Simple — low risk
    6–10    Moderate — manageable
    11–20   Complex — refactor candidate
    21+     Very high — critical refactor target

Public API
----------
analyze_complexity(repo_path, session_number) -> ComplexityReport
load_complexity_history(history_path) -> ComplexityHistory
save_complexity_report(report, out_path) -> None
render_complexity_report(report) -> str
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FunctionComplexity:
    """Complexity info for a single function or method."""

    module: str
    name: str
    qualname: str         # e.g. "MyClass.my_method"
    complexity: int
    lineno: int
    rating: str           # simple / moderate / complex / critical
    is_method: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModuleComplexity:
    """Aggregated complexity for a module."""

    name: str
    avg_complexity: float
    max_complexity: int
    total_functions: int
    functions: list[FunctionComplexity] = field(default_factory=list)
    hot_spots: list[FunctionComplexity] = field(default_factory=list)  # complexity > 10

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComplexityReport:
    """Full complexity analysis for a session snapshot."""

    session_number: int
    modules: list[ModuleComplexity] = field(default_factory=list)
    global_avg: float = 0.0
    global_max: int = 0
    total_functions: int = 0
    hot_spots: list[FunctionComplexity] = field(default_factory=list)
    simple_count: int = 0
    moderate_count: int = 0
    complex_count: int = 0
    critical_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        return render_complexity_report(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class ComplexitySnapshot:
    """Compact per-session snapshot for history tracking."""

    session_number: int
    global_avg: float
    global_max: int
    total_functions: int
    hot_spot_count: int
    critical_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComplexityHistory:
    """Time-series history of complexity across sessions."""

    snapshots: list[ComplexitySnapshot] = field(default_factory=list)

    def add(self, report: ComplexityReport) -> None:
        """Add or update a snapshot for the given session."""
        snap = ComplexitySnapshot(
            session_number=report.session_number,
            global_avg=report.global_avg,
            global_max=report.global_max,
            total_functions=report.total_functions,
            hot_spot_count=len(report.hot_spots),
            critical_count=report.critical_count,
        )
        # Replace if session already exists
        self.snapshots = [s for s in self.snapshots if s.session_number != report.session_number]
        self.snapshots.append(snap)
        self.snapshots.sort(key=lambda s: s.session_number)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ComplexityHistory":
        snaps = [ComplexitySnapshot(**s) for s in d.get("snapshots", [])]
        return cls(snapshots=snaps)

    def to_markdown(self) -> str:
        """Render a trend table with sparklines."""
        if not self.snapshots:
            return "_No complexity history yet._\n"

        lines: list[str] = []
        lines.append("## Complexity Trend")
        lines.append("")
        lines.append("| Session | Avg CC | Max CC | Functions | Hot Spots | Critical | Trend |")
        lines.append("|--------:|-------:|-------:|----------:|----------:|---------:|-------|")

        avgs = [s.global_avg for s in self.snapshots]
        max_avg = max(avgs) if avgs else 1.0

        for snap in self.snapshots:
            trend = _spark_char(snap.global_avg, max_avg)
            lines.append(
                f"| {snap.session_number} "
                f"| {snap.global_avg:.1f} "
                f"| {snap.global_max} "
                f"| {snap.total_functions} "
                f"| {snap.hot_spot_count} "
                f"| {snap.critical_count} "
                f"| {trend} |"
            )

        lines.append("")
        spark = "".join(_spark_char(s.global_avg, max_avg) for s in self.snapshots)
        lines.append(f"**Complexity trend:** `{spark}` (avg CC over sessions)")
        lines.append("")
        return "\n".join(lines)


def _spark_char(value: float, max_val: float) -> str:
    """Map value to a Unicode sparkline character."""
    chars = "▁▂▃▄▅▆▇█"
    if max_val == 0:
        return "▁"
    ratio = min(value / max_val, 1.0)
    idx = int(ratio * (len(chars) - 1))
    return chars[idx]


# ---------------------------------------------------------------------------
# AST-based complexity calculation
# ---------------------------------------------------------------------------


class _ComplexityVisitor(ast.NodeVisitor):
    """Compute McCabe cyclomatic complexity via AST walk."""

    def __init__(self) -> None:
        self.functions: list[tuple[str, str, int, int]] = []
        self._stack: list[str] = []
        self._complexity: list[int] = []

    def _qualname(self, name: str) -> str:
        return ".".join(self._stack + [name])

    def _visit_func(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        qualname = self._qualname(node.name)
        self._stack.append(node.name)
        self._complexity.append(1)  # base complexity

        self.generic_visit(node)

        complexity = self._complexity.pop()
        self._stack.pop()
        self.functions.append((qualname, node.name, complexity, node.lineno))

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def _add_branch(self) -> None:
        if self._complexity:
            self._complexity[-1] += 1

    def visit_If(self, node: ast.If) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if self._complexity:
            self._complexity[-1] += len(node.values) - 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._add_branch()
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._add_branch()
        self.generic_visit(node)


def _rate_complexity(cc: int) -> str:
    if cc <= 5:
        return "simple"
    elif cc <= 10:
        return "moderate"
    elif cc <= 20:
        return "complex"
    else:
        return "critical"


def _analyze_module(module_name: str, path: Path) -> Optional[ModuleComplexity]:
    """Analyze a single Python file for complexity."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return None

    visitor = _ComplexityVisitor()
    visitor.visit(tree)

    if not visitor.functions:
        return ModuleComplexity(
            name=module_name,
            avg_complexity=1.0,
            max_complexity=1,
            total_functions=0,
            functions=[],
            hot_spots=[],
        )

    funcs: list[FunctionComplexity] = []
    for qualname, name, cc, lineno in visitor.functions:
        is_method = "." in qualname
        rating = _rate_complexity(cc)
        funcs.append(FunctionComplexity(
            module=module_name,
            name=name,
            qualname=qualname,
            complexity=cc,
            lineno=lineno,
            rating=rating,
            is_method=is_method,
        ))

    funcs.sort(key=lambda f: f.complexity, reverse=True)
    hot_spots = [f for f in funcs if f.complexity > 10]

    avg_cc = sum(f.complexity for f in funcs) / len(funcs)
    max_cc = max(f.complexity for f in funcs)

    return ModuleComplexity(
        name=module_name,
        avg_complexity=round(avg_cc, 2),
        max_complexity=max_cc,
        total_functions=len(funcs),
        functions=funcs,
        hot_spots=hot_spots,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_complexity(
    repo_path: Optional[Path] = None,
    session_number: int = 0,
) -> ComplexityReport:
    """Analyze cyclomatic complexity for all modules in src/.

    Parameters
    ----------
    repo_path:
        Repo root directory.  Defaults to cwd.
    session_number:
        Session number for this snapshot.
    """
    root = repo_path or Path.cwd()
    src_path = root / "src"

    if not src_path.exists():
        return ComplexityReport(
            session_number=session_number,
        )

    module_complexities: list[ModuleComplexity] = []
    for path in sorted(src_path.glob("*.py")):
        if path.name == "__init__.py":
            continue
        mc = _analyze_module(path.stem, path)
        if mc is not None:
            module_complexities.append(mc)

    all_funcs: list[FunctionComplexity] = []
    for mc in module_complexities:
        all_funcs.extend(mc.functions)

    global_avg = (
        sum(f.complexity for f in all_funcs) / len(all_funcs)
        if all_funcs else 0.0
    )
    global_max = max((f.complexity for f in all_funcs), default=0)
    hot_spots = sorted(
        [f for f in all_funcs if f.complexity > 10],
        key=lambda f: f.complexity,
        reverse=True,
    )

    counts = {"simple": 0, "moderate": 0, "complex": 0, "critical": 0}
    for f in all_funcs:
        counts[f.rating] = counts.get(f.rating, 0) + 1

    report = ComplexityReport(
        session_number=session_number,
        modules=sorted(module_complexities, key=lambda m: m.avg_complexity, reverse=True),
        global_avg=round(global_avg, 2),
        global_max=global_max,
        total_functions=len(all_funcs),
        hot_spots=hot_spots[:10],
        simple_count=counts["simple"],
        moderate_count=counts["moderate"],
        complex_count=counts["complex"],
        critical_count=counts["critical"],
    )
    return report


def load_complexity_history(history_path: Path) -> ComplexityHistory:
    """Load or create a ComplexityHistory from a JSON file."""
    if history_path.exists():
        try:
            return ComplexityHistory.from_dict(
                json.loads(history_path.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, KeyError):
            pass
    return ComplexityHistory()


def save_complexity_report(report: ComplexityReport, out_path: Path) -> None:
    """Write Markdown report and JSON sidecar."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")


def save_complexity_history(history: ComplexityHistory, history_path: Path) -> None:
    """Persist the history JSON file."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(history.to_dict(), indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

_RATING_ICON = {
    "simple": "🟢",
    "moderate": "🟡",
    "complex": "🟠",
    "critical": "🔴",
}


def render_complexity_report(report: ComplexityReport) -> str:
    """Render the complexity report as Markdown."""
    lines: list[str] = []
    lines.append("# 🔬 Cyclomatic Complexity Report")
    lines.append("")
    lines.append(
        f"**Session {report.session_number}** · "
        f"{report.total_functions} functions · "
        f"avg CC: **{report.global_avg:.1f}** · "
        f"max CC: **{report.global_max}**"
    )
    lines.append("")

    total = max(report.total_functions, 1)
    lines.append("## Distribution")
    lines.append("")
    lines.append(f"| Rating | Count | % | Range |")
    lines.append(f"|--------|------:|--:|-------|")
    lines.append(f"| 🟢 Simple | {report.simple_count} | {report.simple_count*100//total}% | CC 1–5 |")
    lines.append(f"| 🟡 Moderate | {report.moderate_count} | {report.moderate_count*100//total}% | CC 6–10 |")
    lines.append(f"| 🟠 Complex | {report.complex_count} | {report.complex_count*100//total}% | CC 11–20 |")
    lines.append(f"| 🔴 Critical | {report.critical_count} | {report.critical_count*100//total}% | CC 21+ |")
    lines.append("")

    if report.hot_spots:
        lines.append("## 🔥 Hot Spots (CC > 10)")
        lines.append("")
        lines.append("| Module | Function | CC | Rating |")
        lines.append("|--------|----------|----|--------|")
        for f in report.hot_spots:
            icon = _RATING_ICON.get(f.rating, "")
            lines.append(f"| `{f.module}` | `{f.qualname}` | {f.complexity} | {icon} {f.rating} |")
        lines.append("")

    lines.append("## Per-Module Summary")
    lines.append("")
    lines.append("| Module | Functions | Avg CC | Max CC | Hot Spots |")
    lines.append("|--------|----------:|-------:|-------:|----------:|")
    for mc in report.modules:
        lines.append(
            f"| `{mc.name}` "
            f"| {mc.total_functions} "
            f"| {mc.avg_complexity:.1f} "
            f"| {mc.max_complexity} "
            f"| {len(mc.hot_spots)} |"
        )
    lines.append("")

    lines.append("## Complexity Chart")
    lines.append("")
    lines.append("```")
    lines.append("Avg Cyclomatic Complexity per module (▓ = higher = more complex)")
    lines.append("")
    max_avg = max((mc.avg_complexity for mc in report.modules), default=1.0)
    max_name = max((len(mc.name) for mc in report.modules), default=10)
    for mc in sorted(report.modules, key=lambda m: m.avg_complexity, reverse=True):
        bar_len = int((mc.avg_complexity / max(max_avg, 1)) * 30)
        bar = "▓" * bar_len + "░" * (30 - bar_len)
        lines.append(f"  {mc.name.ljust(max_name)}  {mc.avg_complexity:5.1f}  │{bar}│")
    lines.append("```")
    lines.append("")

    lines.append("---")
    lines.append("_Generated by `nightshift complexity`_")
    lines.append("")
    return "\n".join(lines)
