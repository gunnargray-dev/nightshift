"""Dependency graph visualizer for Awake.

Analyzes import relationships between all modules in ``src/`` and renders
a Markdown dependency matrix plus an ASCII adjacency list.  Detects:

- Which modules each file imports from within ``src/``
- Circular dependency chains
- Most-depended-upon modules (coupling hot-spots)
- Isolated modules (no cross-module imports)

Usage::

    from src.dep_graph import build_dep_graph, render_dep_graph, save_dep_graph
    graph = build_dep_graph(src_path=Path("src"))
    print(render_dep_graph(graph))
    save_dep_graph(graph, out_path=Path("docs/dep_graph.md"))
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ModuleNode:
    """A single src/ module with its inbound and outbound dependency counts."""

    name: str           # e.g. "health"
    path: str           # relative path e.g. "src/health.py"
    imports: list[str]  # other src/ module names this module imports
    line_count: int

    @property
    def fan_out(self) -> int:
        """Number of src/ modules this module depends on."""
        return len(self.imports)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "name": self.name,
            "path": self.path,
            "imports": self.imports,
            "line_count": self.line_count,
            "fan_out": self.fan_out,
        }


@dataclass
class DepGraph:
    """Complete dependency graph for all src/ modules."""

    nodes: list[ModuleNode]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    @property
    def module_names(self) -> list[str]:
        """Sorted list of all module names."""
        return sorted(n.name for n in self.nodes)

    @property
    def fan_in(self) -> dict[str, int]:
        """Map from module name -> how many other modules import it."""
        counts: dict[str, int] = {n.name: 0 for n in self.nodes}
        for node in self.nodes:
            for dep in node.imports:
                if dep in counts:
                    counts[dep] += 1
        return counts

    def find_cycles(self) -> list[list[str]]:
        """Detect circular dependency chains using DFS.

        Returns list of cycles (each cycle is a list of module names).
        """
        adj: dict[str, list[str]] = {n.name: list(n.imports) for n in self.nodes}
        visited: set[str] = set()
        path: list[str] = []
        on_path: set[str] = set()
        cycles: list[list[str]] = []

        def dfs(node: str) -> None:
            """Traverse the graph depth-first to detect cycles"""
            if node in on_path:
                # Found cycle — extract it
                idx = path.index(node)
                cycle = path[idx:] + [node]
                # Deduplicate
                cycle_key = tuple(sorted(cycle[:-1]))
                for existing in cycles:
                    if tuple(sorted(existing[:-1])) == cycle_key:
                        return
                cycles.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            on_path.add(node)
            path.append(node)
            for neighbor in adj.get(node, []):
                dfs(neighbor)
            path.pop()
            on_path.discard(node)

        for name in adj:
            dfs(name)

        return cycles

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "generated_at": self.generated_at,
            "modules": [n.to_dict() for n in self.nodes],
            "fan_in": self.fan_in,
            "cycles": self.find_cycles(),
        }


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_src_imports(source: str, known_modules: set[str]) -> list[str]:
    """Return src/ module names imported by *source* code.

    Handles both ``import src.foo`` and ``from src.foo import ...`` forms.
    """
    imports: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # e.g. import src.health
                parts = alias.name.split(".")
                if len(parts) >= 2 and parts[0] == "src":
                    mod = parts[1]
                    if mod in known_modules and mod not in imports:
                        imports.append(mod)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                parts = node.module.split(".")
                if len(parts) >= 2 and parts[0] == "src":
                    mod = parts[1]
                    if mod in known_modules and mod not in imports:
                        imports.append(mod)
            elif node.module and node.level == 1:
                # Relative import within src/ — rare but handle it
                mod = node.module.split(".")[0] if node.module else ""
                if mod in known_modules and mod not in imports:
                    imports.append(mod)

    return sorted(imports)


def build_dep_graph(src_path: Path) -> DepGraph:
    """Build the full dependency graph for all Python modules in *src_path*.

    Args:
        src_path: Path to the ``src/`` directory.

    Returns:
        A populated DepGraph.
    """
    py_files = sorted(p for p in src_path.glob("*.py") if p.name != "__init__.py")
    known_modules = {p.stem for p in py_files}

    nodes: list[ModuleNode] = []
    for py_file in py_files:
        source = py_file.read_text(encoding="utf-8", errors="replace")
        imports = _parse_src_imports(source, known_modules)
        nodes.append(ModuleNode(
            name=py_file.stem,
            path=str(py_file.relative_to(src_path.parent)) if src_path.parent != src_path else str(py_file),
            imports=imports,
            line_count=len(source.splitlines()),
        ))

    return DepGraph(nodes=nodes)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_dep_graph(graph: DepGraph) -> str:
    """Render the dependency graph as a Markdown document.

    Includes:
    - Dependency adjacency list (who imports who)
    - Fan-in / fan-out coupling table
    - Circular dependency warnings
    - Isolation report
    """
    lines: list[str] = [
        "# Module Dependency Graph",
        "",
        f"*Generated {graph.generated_at} — {len(graph.nodes)} modules analysed.*",
        "",
    ]

    # --- Adjacency list ---
    lines += ["## Dependency Adjacency List", ""]
    lines.append("Each module lists the src/ modules it imports.")
    lines.append("")
    for node in sorted(graph.nodes, key=lambda n: n.name):
        if node.imports:
            deps = ", ".join(f"`{d}`" for d in node.imports)
            lines.append(f"- **`{node.name}`** → {deps}")
        else:
            lines.append(f"- **`{node.name}`** → *(no src/ dependencies)*")
    lines.append("")

    # --- Coupling table ---
    fan_in = graph.fan_in
    lines += ["## Coupling Metrics", ""]
    lines += [
        "| Module | Fan-Out (depends on) | Fan-In (depended on by) | Lines |",
        "|--------|----------------------|--------------------------|-------|",
    ]
    for node in sorted(graph.nodes, key=lambda n: -(fan_in.get(n.name, 0) + n.fan_out)):
        fi = fan_in.get(node.name, 0)
        lines.append(
            f"| `{node.name}` | {node.fan_out} | {fi} | {node.line_count} |"
        )
    lines.append("")

    # --- Hot-spots ---
    top_fan_in = sorted(fan_in.items(), key=lambda x: -x[1])[:3]
    if top_fan_in and top_fan_in[0][1] > 0:
        lines += ["## Coupling Hot-Spots", ""]
        lines.append("Most depended-upon modules (high fan-in = more coupling risk):")
        lines.append("")
        for name, count in top_fan_in:
            if count > 0:
                lines.append(f"- **`{name}`** — imported by {count} module(s)")
        lines.append("")

    # --- Cycles ---
    cycles = graph.find_cycles()
    lines += ["## Circular Dependencies", ""]
    if cycles:
        lines.append(f"⚠️  **{len(cycles)} circular dependency chain(s) detected:**")
        lines.append("")
        for cycle in cycles:
            chain = " → ".join(f"`{c}`" for c in cycle)
            lines.append(f"- {chain}")
    else:
        lines.append("✅ No circular dependencies detected.")
    lines.append("")

    # --- Isolated modules ---
    isolated = [
        n.name for n in graph.nodes
        if n.fan_out == 0 and fan_in.get(n.name, 0) == 0
    ]
    lines += ["## Isolated Modules", ""]
    if isolated:
        lines.append("Modules with no cross-module imports or reverse dependencies:")
        lines.append("")
        for name in sorted(isolated):
            lines.append(f"- `{name}`")
    else:
        lines.append("All modules participate in at least one dependency relationship.")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Generated by `src/dep_graph.py` — part of the Awake autonomous development system.*")

    return "\n".join(lines)


def save_dep_graph(graph: DepGraph, out_path: Path) -> None:
    """Write the rendered dep graph Markdown to *out_path*.

    Also writes a JSON sidecar at ``out_path.with_suffix('.json')`` for
    machine consumption (dashboards, brain.py, etc.).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_dep_graph(graph), encoding="utf-8")

    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps(graph.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
