"""Python module dependency graph builder."""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ModuleNode:
    """A node in the module dependency graph."""

    name: str
    path: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)


@dataclass
class ModuleGraph:
    """The full dependency graph for a Python project."""

    root: str
    nodes: dict[str, ModuleNode] = field(default_factory=dict)

    def add_node(self, node: ModuleNode) -> None:
        self.nodes[node.name] = node

    def add_edge(self, from_module: str, to_module: str) -> None:
        if from_module in self.nodes:
            if to_module not in self.nodes[from_module].imports:
                self.nodes[from_module].imports.append(to_module)
        if to_module in self.nodes:
            if from_module not in self.nodes[to_module].imported_by:
                self.nodes[to_module].imported_by.append(from_module)


def _module_name_from_path(path: Path, root: Path) -> str:
    """Convert a file path to a dotted module name."""
    rel = path.relative_to(root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _extract_imports(source: str, current_module: str, root_package: str) -> list[str]:
    """Extract imported module names from Python source."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import
                parts = current_module.split(".")
                base = parts[: max(0, len(parts) - node.level)]
                if node.module:
                    base.append(node.module)
                imports.append(".".join(base))
            elif node.module:
                imports.append(node.module)
    return imports


def build_module_graph(
    root: Path,
    exclude: Optional[set[str]] = None,
    glob_pattern: str = "**/*.py",
) -> ModuleGraph:
    """Build a module dependency graph for the Python project at *root*."""
    exclude = exclude or set()
    graph = ModuleGraph(root=str(root))
    root_package = root.name

    # First pass: register all modules
    py_files = sorted(root.glob(glob_pattern))
    for py_file in py_files:
        if any(exc in py_file.parts for exc in exclude):
            continue
        mod_name = _module_name_from_path(py_file, root)
        graph.add_node(ModuleNode(name=mod_name, path=str(py_file)))

    # Second pass: extract imports and add edges
    for mod_name, node in list(graph.nodes.items()):
        source = Path(node.path).read_text(encoding="utf-8", errors="replace")
        imports = _extract_imports(source, mod_name, root_package)
        for imp in imports:
            # Only track intra-project imports
            if imp in graph.nodes or any(
                n.startswith(imp + ".") or imp.startswith(n + ".") for n in graph.nodes
            ):
                graph.add_edge(mod_name, imp)

    return graph


def render_dot(graph: ModuleGraph) -> str:
    """Render the graph as a Graphviz DOT string."""
    lines = ["digraph modules {"]
    lines.append('  rankdir="LR";')
    lines.append('  node [shape=box, fontname="monospace"];')
    for mod_name in graph.nodes:
        label = mod_name.replace('"', '\\"')
        lines.append(f'  "{label}";')
    for mod_name, node in graph.nodes.items():
        src = mod_name.replace('"', '\\"')
        for imp in node.imports:
            dst = imp.replace('"', '\\"')
            lines.append(f'  "{src}" -> "{dst}";')
    lines.append("}")
    return "\n".join(lines)


def render_json(graph: ModuleGraph) -> str:
    """Render the graph as a JSON string."""
    data = {
        "root": graph.root,
        "nodes": [
            {
                "name": n.name,
                "path": n.path,
                "imports": n.imports,
                "imported_by": n.imported_by,
            }
            for n in graph.nodes.values()
        ],
    }
    return json.dumps(data, indent=2)
