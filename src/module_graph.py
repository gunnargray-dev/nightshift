"""Module interconnection visualizer for Awake.

Generates a directed graph of Python module imports within a repository
and can render it as:

- A `DOT <https://graphviz.org/>`_ file (``--dot``)
- A Mermaid ``flowchart`` snippet (``--mermaid``)
- A JSON adjacency list (``--json``)

The graph nodes are Python module paths relative to the repository root
(e.g. ``src/health.py``).  Edges represent *import* relationships -- an
edge A -> B means "A imports B".

Public API
----------
- ``ModuleNode``        -- single node in the graph
- ``ModuleGraph``       -- the full graph
- ``build_module_graph(repo_path)`` -> ``ModuleGraph``
- ``to_dot(graph)``     -> ``str``
- ``to_mermaid(graph)`` -> ``str``
- ``save_graph(graph, out_path)``

CLI
---
    awake graph [--dot] [--mermaid] [--json] [--output PATH]
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ModuleNode:
    """A single Python file (module) in the repository."""

    path: str  # relative path, e.g. "src/health.py"
    imports: list[str] = field(default_factory=list)  # resolved relative paths
    raw_imports: list[str] = field(default_factory=list)  # as written in source


@dataclass
class ModuleGraph:
    """Directed import graph for the entire repository."""

    nodes: dict[str, ModuleNode] = field(default_factory=dict)  # path -> node
    root: str = ""

    @property
    def edges(self) -> list[tuple[str, str]]:
        """Return all directed edges as (src, dst) pairs."""
        result: list[tuple[str, str]] = []
        for node in self.nodes.values():
            for imp in node.imports:
                result.append((node.path, imp))
        return result


# ---------------------------------------------------------------------------
# Import resolver
# ---------------------------------------------------------------------------


def _collect_imports(source: str, filename: str) -> list[str]:
    """Return a list of raw module names imported in *source*."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                prefix = "." * (node.level or 0)
                names.append(prefix + node.module)
    return names


def _resolve_import(raw: str, importer: str, all_paths: set[str]) -> str | None:
    """Try to resolve *raw* import to a relative repo path.

    Returns the resolved path string or *None* if not a local module.
    """
    # Strip leading dots (relative imports) - treat as absolute for now
    module = raw.lstrip(".")
    parts = module.replace(".", "/")

    # Candidates: direct file, __init__.py in package
    candidates = [
        f"{parts}.py",
        f"{parts}/__init__.py",
    ]
    # Also try relative to importer's directory
    importer_dir = str(Path(importer).parent)
    candidates += [
        f"{importer_dir}/{parts}.py",
        f"{importer_dir}/{parts}/__init__.py",
    ]

    for c in candidates:
        # Normalise path separators
        norm = str(Path(c))
        if norm in all_paths:
            return norm
    return None


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_module_graph(repo_path: str | Path) -> ModuleGraph:
    """Build a :class:`ModuleGraph` for the repository at *repo_path*.

    Parameters
    ----------
    repo_path:
        Root directory of the repository.

    Returns
    -------
    ModuleGraph
        The completed module import graph.
    """
    root = Path(repo_path)
    graph = ModuleGraph(root=str(root))

    py_files = sorted(root.rglob("*.py"))
    all_paths: set[str] = {str(f.relative_to(root)) for f in py_files}

    for py_file in py_files:
        rel = str(py_file.relative_to(root))
        try:
            source = py_file.read_text(encoding="utf-8")
        except OSError:
            continue

        raw_imports = _collect_imports(source, rel)
        resolved: list[str] = []
        for raw in raw_imports:
            r = _resolve_import(raw, rel, all_paths)
            if r is not None:
                resolved.append(r)

        graph.nodes[rel] = ModuleNode(
            path=rel,
            imports=resolved,
            raw_imports=raw_imports,
        )

    return graph


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def to_dot(graph: ModuleGraph) -> str:
    """Render *graph* as a Graphviz DOT string.

    Parameters
    ----------
    graph:
        The module graph to render.

    Returns
    -------
    str
        DOT-format string.
    """
    lines = ["digraph modules {"]
    lines.append('    rankdir="LR";')
    lines.append('    node [shape=box fontname="Helvetica"];')
    for node in graph.nodes.values():
        label = node.path.replace("\\", "/")
        safe = label.replace("/", "_").replace(".", "_")
        lines.append(f'    {safe} [label="{label}"];')
    for src, dst in graph.edges:
        src_safe = src.replace("/", "_").replace(".", "_")
        dst_safe = dst.replace("/", "_").replace(".", "_")
        lines.append(f"    {src_safe} -> {dst_safe};")
    lines.append("}")
    return "\n".join(lines)


def to_mermaid(graph: ModuleGraph) -> str:
    """Render *graph* as a Mermaid flowchart string.

    Parameters
    ----------
    graph:
        The module graph to render.

    Returns
    -------
    str
        Mermaid flowchart string.
    """
    lines = ["flowchart LR"]
    for node in graph.nodes.values():
        label = node.path.replace("\\", "/")
        safe = label.replace("/", "_").replace(".", "_").replace("-", "_")
        lines.append(f'    {safe}["{label}"]')
    for src, dst in graph.edges:
        src_safe = src.replace("/", "_").replace(".", "_").replace("-", "_")
        dst_safe = dst.replace("/", "_").replace(".", "_").replace("-", "_")
        lines.append(f"    {src_safe} --> {dst_safe}")
    return "\n".join(lines)


def save_graph(graph: ModuleGraph, out_path: str | Path) -> None:
    """Serialise *graph* as JSON and write to *out_path*.

    Parameters
    ----------
    graph:
        The module graph to save.
    out_path:
        Destination file path.
    """
    data = {
        "root": graph.root,
        "nodes": [
            {
                "path": n.path,
                "imports": n.imports,
                "raw_imports": n.raw_imports,
            }
            for n in graph.nodes.values()
        ],
    }
    Path(out_path).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the module graph visualizer.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake graph",
        description="Visualise module import relationships.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--dot", action="store_true", help="Output DOT format")
    parser.add_argument("--mermaid", action="store_true", help="Output Mermaid format")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--output", "-o", default="", help="Write output to file")
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    graph = build_module_graph(root)

    if args.dot:
        output = to_dot(graph)
    elif args.mermaid:
        output = to_mermaid(graph)
    else:
        # default to JSON
        nodes_data = [
            {
                "path": n.path,
                "imports": n.imports,
                "raw_imports": n.raw_imports,
            }
            for n in graph.nodes.values()
        ]
        output = json.dumps({"root": graph.root, "nodes": nodes_data}, indent=2)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Graph written to {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
