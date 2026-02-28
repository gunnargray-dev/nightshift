"""Module coupling analyzer for Nightshift.

Computes afferent coupling (Ca), efferent coupling (Ce), and the instability
metric (I = Ce / (Ca + Ce)) for every module in src/.  Based on Robert C.
Martin's stability metrics from "Agile Software Development, Principles,
Patterns, and Practices".

Additionally measures:
- Abstractness (A): ratio of abstract classes/functions to total (0–1)
- Distance from the Main Sequence (D = |A + I - 1|): lower is better
- Fan-in / fan-out per module
- Coupling strength score (0–100, higher = more problematic)

Public API
----------
analyze_coupling(repo_path) -> CouplingReport
render_coupling_report(report) -> str
save_coupling_report(report, out_path) -> None
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ModuleCoupling:
    """Coupling metrics for a single module."""

    name: str                    # e.g. "health"
    afferent: int = 0            # Ca: # other modules that import this one
    efferent: int = 0            # Ce: # modules this one imports
    instability: float = 0.0    # I = Ce / (Ca + Ce); 0=stable, 1=unstable
    abstractness: float = 0.0   # A = abstract / total symbols
    distance: float = 0.0       # D = |A + I - 1|; ideal=0
    coupling_score: int = 0     # 0–100 combined badness score
    imports: list[str] = field(default_factory=list)   # modules this imports
    imported_by: list[str] = field(default_factory=list)  # modules that import this
    abstract_symbols: list[str] = field(default_factory=list)
    total_symbols: int = 0
    grade: str = "A"            # A–F

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CouplingReport:
    """Full coupling analysis report."""

    modules: list[ModuleCoupling] = field(default_factory=list)
    most_stable: list[str] = field(default_factory=list)    # low instability
    most_unstable: list[str] = field(default_factory=list)  # high instability
    most_coupled: list[str] = field(default_factory=list)   # high coupling_score
    circular_groups: list[list[str]] = field(default_factory=list)
    avg_instability: float = 0.0
    avg_coupling_score: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        return render_coupling_report(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# AST analysis helpers
# ---------------------------------------------------------------------------


def _collect_src_modules(src_path: Path) -> dict[str, Path]:
    """Return {module_name: path} for all .py files in src/."""
    modules: dict[str, Path] = {}
    for p in sorted(src_path.glob("*.py")):
        if p.name == "__init__.py":
            continue
        modules[p.stem] = p
    return modules


def _parse_imports(py_path: Path, known_modules: set[str]) -> list[str]:
    """Return list of known module names imported by py_path."""
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except (SyntaxError, OSError, FileNotFoundError):
        return []

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # e.g. from src.health import ...  OR  from health import ...
            if node.module:
                parts = node.module.split(".")
                # Check last part first, then first part
                for part in parts:
                    if part in known_modules:
                        if part not in imported:
                            imported.append(part)
                        break
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split(".")[0]
                if name in known_modules and name not in imported:
                    imported.append(name)

    return imported


def _is_abstract_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if the function has only a docstring body (abstract interface)."""
    body = node.body
    if len(body) == 1 and isinstance(body[0], ast.Expr):
        return isinstance(body[0].value, (ast.Constant, ast.Str))
    if len(body) == 2 and isinstance(body[0], ast.Expr) and isinstance(body[1], ast.Raise):
        return True
    return False


def _analyze_abstractness(py_path: Path) -> tuple[float, list[str], int]:
    """Return (abstractness 0-1, abstract_symbol_names, total_symbols)."""
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return 0.0, [], 0

    abstract_syms: list[str] = []
    total = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                total += 1
                if _is_abstract_function(node):
                    abstract_syms.append(node.name)
        elif isinstance(node, ast.ClassDef):
            # Check if class has ABC in bases
            for base in node.bases:
                name = getattr(base, "id", None) or getattr(base, "attr", None)
                if name in ("ABC", "ABCMeta", "Protocol"):
                    abstract_syms.append(node.name)
                    break

    abstract_count = len(abstract_syms)
    abstractness = abstract_count / max(total, 1)
    return min(abstractness, 1.0), abstract_syms, total


def _grade_coupling(score: int) -> str:
    if score <= 15:
        return "A"
    elif score <= 30:
        return "B"
    elif score <= 50:
        return "C"
    elif score <= 65:
        return "D"
    elif score <= 80:
        return "F"
    else:
        return "F"


# ---------------------------------------------------------------------------
# Circular dependency detection
# ---------------------------------------------------------------------------


def _find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Return list of cycles (each cycle is a list of module names)."""
    visited: set[str] = set()
    cycles: list[list[str]] = []

    def dfs(node: str, path: list[str], path_set: set[str]) -> None:
        visited.add(node)
        path_set.add(node)
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor, path[:], path_set.copy())
            elif neighbor in path_set:
                # Found a cycle: neighbor is in the current DFS path
                try:
                    cycle_start = path.index(neighbor)
                except ValueError:
                    continue
                cycle = path[cycle_start:] + [neighbor]
                # Deduplicate
                cycle_key = frozenset(cycle)
                if not any(frozenset(c) == cycle_key for c in cycles):
                    cycles.append(cycle)

    for node in graph:
        if node not in visited:
            dfs(node, [], set())

    return cycles


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def analyze_coupling(repo_path: Optional[Path] = None) -> CouplingReport:
    """Analyze module coupling for all src/ modules.

    Parameters
    ----------
    repo_path:
        Repo root directory.  Defaults to cwd.
    """
    root = repo_path or Path.cwd()
    src_path = root / "src"

    if not src_path.exists():
        return CouplingReport(summary="src/ directory not found")

    module_files = _collect_src_modules(src_path)
    known_modules = set(module_files.keys())

    # Build import graph
    imports_map: dict[str, list[str]] = {}
    for name, path in module_files.items():
        imports_map[name] = _parse_imports(path, known_modules)

    # Compute Ca (afferent) for each module: how many other modules import it
    ca: dict[str, int] = {name: 0 for name in known_modules}
    imported_by_map: dict[str, list[str]] = {name: [] for name in known_modules}
    for name, deps in imports_map.items():
        for dep in deps:
            if dep in ca:
                ca[dep] += 1
                imported_by_map[dep].append(name)

    # Build coupling objects
    modules: list[ModuleCoupling] = []
    for name, path in sorted(module_files.items()):
        efferent = len(imports_map[name])
        afferent_val = ca[name]
        total_coupling = afferent_val + efferent
        instability = efferent / max(total_coupling, 1)

        abstractness, abstract_syms, total_syms = _analyze_abstractness(path)
        distance = abs(abstractness + instability - 1.0)

        # Coupling score: weighted combination
        # High instability + high distance = bad
        score_raw = (
            instability * 40          # 0–40
            + distance * 30           # 0–30
            + min(efferent / 5, 1) * 20  # 0–20 (penalise high fan-out)
            + min(afferent_val / 8, 1) * 10  # 0–10 (reward being widely used)
        )
        coupling_score = int(min(score_raw, 100))
        grade = _grade_coupling(coupling_score)

        modules.append(ModuleCoupling(
            name=name,
            afferent=afferent_val,
            efferent=efferent,
            instability=round(instability, 3),
            abstractness=round(abstractness, 3),
            distance=round(distance, 3),
            coupling_score=coupling_score,
            imports=imports_map[name],
            imported_by=imported_by_map[name],
            abstract_symbols=abstract_syms,
            total_symbols=total_syms,
            grade=grade,
        ))

    # Sort by coupling_score descending
    modules.sort(key=lambda m: m.coupling_score, reverse=True)

    # Summary stats
    avg_instability = sum(m.instability for m in modules) / max(len(modules), 1)
    avg_coupling = sum(m.coupling_score for m in modules) / max(len(modules), 1)

    most_stable = [m.name for m in sorted(modules, key=lambda m: m.instability)[:3]]
    most_unstable = [m.name for m in sorted(modules, key=lambda m: m.instability, reverse=True)[:3]]
    most_coupled = [m.name for m in modules[:3]]

    # Detect cycles
    cycles = _find_cycles(imports_map)

    report = CouplingReport(
        modules=modules,
        most_stable=most_stable,
        most_unstable=most_unstable,
        most_coupled=most_coupled,
        circular_groups=cycles,
        avg_instability=round(avg_instability, 3),
        avg_coupling_score=round(avg_coupling, 1),
        summary=f"{len(modules)} modules analyzed",
    )
    return report


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

_GRADE_COLORS = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "⛔"}


def render_coupling_report(report: CouplingReport) -> str:
    """Render the coupling report as Markdown."""
    lines: list[str] = []
    lines.append("# 🔗 Module Coupling Analysis")
    lines.append("")
    lines.append(
        f"**{len(report.modules)} modules** · "
        f"avg instability: **{report.avg_instability:.2f}** · "
        f"avg coupling score: **{report.avg_coupling_score:.0f}/100**"
    )
    lines.append("")

    if report.circular_groups:
        lines.append("## ⚠️ Circular Dependencies Detected")
        lines.append("")
        for cycle in report.circular_groups:
            lines.append(f"- `{'` → `'.join(cycle)}`")
        lines.append("")

    lines.append("## Coupling Metrics Table")
    lines.append("")
    lines.append("| Module | Ca | Ce | I | A | D | Score | Grade |")
    lines.append("|--------|---:|---:|--:|--:|--:|------:|-------|")

    for m in sorted(report.modules, key=lambda x: x.coupling_score, reverse=True):
        icon = _GRADE_COLORS.get(m.grade, "")
        lines.append(
            f"| `{m.name}` "
            f"| {m.afferent} "
            f"| {m.efferent} "
            f"| {m.instability:.2f} "
            f"| {m.abstractness:.2f} "
            f"| {m.distance:.2f} "
            f"| {m.coupling_score} "
            f"| {icon} {m.grade} |"
        )

    lines.append("")
    lines.append("> **Ca** = afferent coupling (who imports this) · "
                 "**Ce** = efferent coupling (what this imports) · "
                 "**I** = instability (0=stable, 1=unstable) · "
                 "**A** = abstractness · "
                 "**D** = distance from main sequence")
    lines.append("")

    # Stability analysis
    lines.append("## Stability Summary")
    lines.append("")
    lines.append(f"**Most stable** (low I): {', '.join(f'`{n}`' for n in report.most_stable)}")
    lines.append(f"**Most unstable** (high I): {', '.join(f'`{n}`' for n in report.most_unstable)}")
    lines.append(f"**Most coupled** (high score): {', '.join(f'`{n}`' for n in report.most_coupled)}")
    lines.append("")

    # ASCII stability chart
    lines.append("## Instability Distribution")
    lines.append("")
    lines.append("```")
    lines.append("Instability (I): 0=stable, 1=unstable")
    lines.append("")
    max_name = max((len(m.name) for m in report.modules), default=10)
    for m in sorted(report.modules, key=lambda x: x.instability, reverse=True):
        bar_len = int(m.instability * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        lines.append(f"  {m.name.ljust(max_name)}  {m.instability:.2f}  │{bar}│")
    lines.append("```")
    lines.append("")

    # Per-module detail
    lines.append("## Per-Module Detail")
    lines.append("")
    for m in sorted(report.modules, key=lambda x: x.name):
        icon = _GRADE_COLORS.get(m.grade, "")
        lines.append(f"### `{m.name}` {icon} Grade {m.grade}")
        lines.append("")
        lines.append(f"- **Instability:** {m.instability:.3f}")
        lines.append(f"- **Afferent (Ca):** {m.afferent} — imported by: "
                     + (", ".join(f"`{x}`" for x in m.imported_by) or "_none_"))
        lines.append(f"- **Efferent (Ce):** {m.efferent} — imports: "
                     + (", ".join(f"`{x}`" for x in m.imports) or "_none_"))
        lines.append(f"- **Abstractness:** {m.abstractness:.3f}")
        lines.append(f"- **Distance (D):** {m.distance:.3f}")
        if m.abstract_symbols:
            lines.append(f"- **Abstract symbols:** {', '.join(m.abstract_symbols[:5])}")
        lines.append("")

    lines.append("---")
    lines.append("_Generated by `nightshift coupling`_")
    lines.append("")

    return "\n".join(lines)


def save_coupling_report(report: CouplingReport, out_path: Path) -> None:
    """Write the Markdown report and a JSON sidecar."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")
