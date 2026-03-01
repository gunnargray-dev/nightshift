"""Module dependency graph builder for Awake.

Builds a directed import graph from the source tree, computes per-module
metrics (in-degree, out-degree, PageRank-style centrality), and detects
circular dependencies.

CLI
---
    awake graph                    # Print dependency table
    awake graph --json             # Emit JSON
    awake graph --cycles           # Show only cycles
    awake graph --top 10           # Show top 10 by centrality
"""

from __future__ import annotations

import ast
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ModuleNode:
    """A single module in the dependency graph."""

    name: str
    path: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    in_degree: int = 0
    out_degree: int = 0
    centrality: float = 0.0
    in_cycle: bool = False

    def to_dict(self) -> dict:
        """Return a dictionary representation of the module node."""
        return asdict(self)


@dataclass
class DependencyGraph:
    """Full module dependency graph for a repository."""

    repo_path: str
    nodes: list[ModuleNode] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    cycles: list[list[str]] = field(default_factory=list)
    total_modules: int = 0
    total_edges: int = 0
    cycle_count: int = 0

    def to_dict(self) -> dict:
        """Return a dictionary representation of the dependency graph."""
        return {
            "repo_path": self.repo_path,
            "total_modules": self.total_modules,
            "total_edges": self.total_edges,
            "cycle_count": self.cycle_count,
            "cycles": self.cycles,
            "nodes": [n.to_dict() for n in self.nodes],
        }

    def to_markdown(self) -> str:
        """Render the graph as a Markdown table, sorted by centrality."""
        lines = [
            "## Module Dependency Graph",
            "",
            f"| Metric | Value |",
            f"|--------|-------|]",
            f"| Total modules | {self.total_modules} |",
            f"| Total edges   | {self.total_edges} |",
            f"| Cycles        | {self.cycle_count} |",
            "",
            "| Module | In | Out | Centrality | Cycle |",
            "|--------|-----|-----|------------|-------|]",
        ]
        for n in sorted(self.nodes, key=lambda x: x.centrality, reverse=True)[:30]:
            cycle_mark = "YES" if n.in_cycle else "-"
            lines.append(
                f"| `{n.name}` | {n.in_degree} | {n.out_degree} "
                f"| {n.centrality:.3f} | {cycle_mark} |"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Import extractor
# ---------------------------------------------------------------------------


def _extract_imports(path: Path, repo_root: Path) -> list[str]:
    """Return a list of local module names imported by *path*."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    # Keep only local imports (those resolvable within the repo)
    src_modules = {_path_to_module(p, repo_root) for p in repo_root.rglob("*.py")}
    return [i for i in imports if _is_local(i, src_modules)]


def _path_to_module(path: Path, repo_root: Path) -> str:
    """Convert a file path to a dotted module name relative to repo_root."""
    rel = path.relative_to(repo_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]  # strip .py
    return ".".join(parts)


def _is_local(import_name: str, src_modules: set[str]) -> bool:
    """Return True if *import_name* refers to a module within the repo."""
    # Exact match or prefix match (package import)
    return any(
        m == import_name or m.startswith(import_name + ".")
        for m in src_modules
    )


# ---------------------------------------------------------------------------
# Cycle detection  (DFS / Tarjan SCC)
# ---------------------------------------------------------------------------


def _find_cycles(adj: dict[str, list[str]]) -> list[list[str]]:
    """Return all strongly-connected components (size >= 2) via Tarjan's."""
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        """Recursive DFS for Tarjan's SCC."""
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in adj.get(v, []):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1:
                sccs.append(scc)

    for v in list(adj.keys()):
        if v not in index:
            strongconnect(v)

    return sccs


# ---------------------------------------------------------------------------
# Centrality (simple iterative PageRank)
# ---------------------------------------------------------------------------


def _compute_centrality(
    nodes: list[str], adj: dict[str, list[str]], iterations: int = 20
) -> dict[str, float]:
    """Compute a PageRank-style centrality score for each node."""
    n = len(nodes)
    if n == 0:
        return {}
    rank: dict[str, float] = {v: 1.0 / n for v in nodes}
    damping = 0.85

    for _ in range(iterations):
        new_rank: dict[str, float] = {v: (1.0 - damping) / n for v in nodes}
        for v in nodes:
            out_edges = adj.get(v, [])
            if not out_edges:
                # Dangling node: distribute evenly
                contrib = damping * rank[v] / n
                for u in nodes:
                    new_rank[u] += contrib
            else:
                contrib = damping * rank[v] / len(out_edges)
                for u in out_edges:
                    if u in new_rank:
                        new_rank[u] += contrib
        rank = new_rank

    return rank


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_module_graph(repo_root: Path) -> DependencyGraph:
    """Build and return the full module dependency graph."""
    src_dir = repo_root / "src"
    if not src_dir.exists():
        src_dir = repo_root

    py_files = sorted(src_dir.rglob("*.py"))
    module_map: dict[str, Path] = {}
    for p in py_files:
        name = _path_to_module(p, repo_root)
        module_map[name] = p

    adj: dict[str, list[str]] = {}
    for name, path in module_map.items():
        deps = _extract_imports(path, repo_root)
        adj[name] = [d for d in deps if d in module_map]

    # Build reverse adjacency
    rev_adj: dict[str, list[str]] = defaultdict(list)
    for src, targets in adj.items():
        for tgt in targets:
            rev_adj[tgt].append(src)

    cycles = _find_cycles(adj)
    cycle_members: set[str] = {m for cycle in cycles for m in cycle}

    centrality = _compute_centrality(list(module_map.keys()), adj)

    nodes: list[ModuleNode] = []
    edges: list[tuple[str, str]] = []
    for name in sorted(module_map.keys()):
        node = ModuleNode(
            name=name,
            path=str(module_map[name].relative_to(repo_root)),
            imports=adj.get(name, []),
            imported_by=rev_adj.get(name, []),
            in_degree=len(rev_adj.get(name, [])),
            out_degree=len(adj.get(name, [])),
            centrality=round(centrality.get(name, 0.0), 4),
            in_cycle=name in cycle_members,
        )
        nodes.append(node)
        for tgt in adj.get(name, []):
            edges.append((name, tgt))

    return DependencyGraph(
        repo_path=str(repo_root),
        nodes=nodes,
        edges=edges,
        cycles=cycles,
        total_modules=len(nodes),
        total_edges=len(edges),
        cycle_count=len(cycles),
    )
