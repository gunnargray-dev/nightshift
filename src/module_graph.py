"""Module interconnection visualizer for Nightshift.

Generates Mermaid flowchart diagrams and ASCII representations showing how
all src/ modules relate to one another via imports and functional coupling.

CLI
---
    nightshift modules                  # Print Mermaid diagram to stdout
    nightshift modules --ascii          # ASCII art diagram
    nightshift modules --write          # Write docs/MODULE_GRAPH.md
    nightshift modules --json           # Emit graph as JSON
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


_LAYER_MAP = {
    "config": "core", "session_logger": "core", "stats": "core", "cli": "core", "server": "core",
    "health": "analysis", "health_trend": "analysis", "complexity": "analysis",
    "coupling": "analysis", "dead_code": "analysis", "security": "analysis",
    "coverage_tracker": "analysis", "coverage_map": "analysis", "audit": "analysis",
    "maturity": "analysis", "predict": "analysis", "test_quality": "analysis",
    "gitstats": "git", "blame": "git", "diff_visualizer": "git",
    "changelog": "git", "semver": "git", "timeline": "git", "commit_analyzer": "git",
    "dep_graph": "intelligence", "arch_generator": "intelligence",
    "refactor": "intelligence", "brain": "intelligence", "dna": "intelligence",
    "readme_updater": "output", "exporter": "output", "dashboard": "output",
    "badges": "output", "report": "output", "openapi": "output", "module_graph": "output",
    "plugins": "extensibility",
    "diff_sessions": "sessions", "session_replay": "sessions", "compare": "sessions",
    "doctor": "misc", "issue_triage": "misc", "deps_checker": "misc",
    "teach": "misc", "story": "misc", "todo_hunter": "misc",
    "pr_scorer": "misc", "benchmark": "misc", "init_cmd": "misc",
    "trend_data": "analysis", "release_notes": "git",
}

_LAYER_STYLES = {
    "core": "fill:#58a6ff,color:#0d1117,stroke:#1f6feb",
    "analysis": "fill:#3fb950,color:#0d1117,stroke:#238636",
    "git": "fill:#f78166,color:#0d1117,stroke:#da3633",
    "intelligence": "fill:#bc8cff,color:#0d1117,stroke:#8957e5",
    "output": "fill:#79c0ff,color:#0d1117,stroke:#388bfd",
    "extensibility": "fill:#ffa657,color:#0d1117,stroke:#e3b341",
    "sessions": "fill:#56d364,color:#0d1117,stroke:#2ea043",
    "misc": "fill:#8b949e,color:#0d1117,stroke:#6e7681",
}


@dataclass
class ModuleNode:
    """A single module in the dependency graph with its layer and edges"""

    name: str
    layer: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of this module node"""
        return asdict(self)


@dataclass
class ModuleGraph:
    """The full module interconnection graph with nodes, edges, and layers"""

    nodes: list[ModuleNode] = field(default_factory=list)
    edges: list[tuple] = field(default_factory=list)
    layers: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the full module graph"""
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [{"from": e[0], "to": e[1]} for e in self.edges],
            "layers": self.layers,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
        }

    def to_mermaid(self, show_all_edges: bool = False) -> str:
        """Render the module graph as a Mermaid flowchart diagram"""
        lines = ["```mermaid", "graph TD"]
        layer_order = ["core", "analysis", "git", "intelligence", "output", "extensibility", "sessions", "misc"]
        layer_labels = {
            "core": "Core Infrastructure", "analysis": "Analysis Engines",
            "git": "Git / History", "intelligence": "Code Intelligence",
            "output": "Reporting & Output", "extensibility": "Extensibility",
            "sessions": "Session Management", "misc": "Utilities",
        }
        for layer in layer_order:
            mods = self.layers.get(layer, [])
            if not mods:
                continue
            lines.append(f"    subgraph {layer_labels.get(layer, layer)}")
            for mod in sorted(mods):
                node_id = mod.replace("-", "_").replace(".", "_")
                lines.append(f"        {node_id}[{mod}]")
            lines.append("    end")
        lines.append("")
        drawn: set = set()
        priority_froms = {"cli", "server", "brain", "audit", "report", "openapi", "dashboard"}
        for frm, to in self.edges:
            frm_id = frm.replace("-", "_").replace(".", "_")
            to_id = to.replace("-", "_").replace(".", "_")
            key = (frm_id, to_id)
            if key in drawn:
                continue
            if not show_all_edges and frm not in priority_froms:
                continue
            drawn.add(key)
            lines.append(f"    {frm_id} --> {to_id}")
        lines.append("")
        for layer, style in _LAYER_STYLES.items():
            mods = self.layers.get(layer, [])
            if mods:
                for mod in mods:
                    mid = mod.replace("-", "_").replace(".", "_")
                    lines.append(f"    style {mid} {style}")
        lines.append("```")
        return "\n".join(lines)

    def to_ascii(self) -> str:
        """Render the module graph as an ASCII art diagram"""
        layer_order = ["core", "analysis", "git", "intelligence", "output", "extensibility", "sessions", "misc"]
        layer_labels = {
            "core": "Core Infrastructure", "analysis": "Analysis Engines",
            "git": "Git / History", "intelligence": "Code Intelligence",
            "output": "Reporting & Output", "extensibility": "Extensibility",
            "sessions": "Session Management", "misc": "Utilities",
        }
        lines = ["", "  Module Interconnection Graph - Nightshift", "  " + "-" * 50, ""]
        for layer in layer_order:
            mods = self.layers.get(layer, [])
            if not mods:
                continue
            label = layer_labels.get(layer, layer)
            lines.append(f"  +- {label} {'-' * max(0, 44 - len(label))}+")
            for mod in sorted(mods):
                node = next((n for n in self.nodes if n.name == mod), None)
                imports_str = ""
                if node and node.imports:
                    key_imports = [i for i in node.imports if i in ("config", "session_logger", "health", "stats")][:2]
                    if key_imports:
                        imports_str = f"  -> uses: {', '.join(key_imports)}"
                lines.append(f"  |  {mod:<28}{imports_str}")
            lines.append("  +" + "-" * 49 + "+")
            lines.append("")
        lines += [f"  Total modules : {len(self.nodes)}", f"  Total edges   : {len(self.edges)}", ""]
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render the module graph as a Markdown document with diagram and table"""
        mermaid = self.to_mermaid()
        layer_order = ["core", "analysis", "git", "intelligence", "output", "extensibility", "sessions", "misc"]
        layer_labels = {
            "core": "Core Infrastructure", "analysis": "Analysis Engines",
            "git": "Git / History", "intelligence": "Code Intelligence",
            "output": "Reporting & Output", "extensibility": "Extensibility",
            "sessions": "Session Management", "misc": "Utilities",
        }
        table_rows = []
        for layer in layer_order:
            mods = self.layers.get(layer, [])
            for mod in sorted(mods):
                node = next((n for n in self.nodes if n.name == mod), None)
                imports_str = ", ".join(f"`{i}`" for i in (node.imports if node else [])[:5])
                table_rows.append(f"| `{mod}` | {layer_labels.get(layer, layer)} | {imports_str} |")
        table = "\n".join(["| Module | Layer | Key Dependencies |", "|--------|-------|-----------------|"] + table_rows)
        return f"""# Module Interconnection Graph\n\nGenerated by `nightshift modules`.\n\n## Mermaid Diagram\n\n{mermaid}\n\n## Module Layer Table\n\n{table}\n\n---\n*{len(self.nodes)} modules - {len(self.edges)} dependency edges*\n"""


def _discover_modules(src_dir: Path) -> list[str]:
    return sorted(p.stem for p in src_dir.glob("*.py") if p.stem != "__init__")


def _extract_imports(src_file: Path, module_names: set) -> list[str]:
    try:
        tree = ast.parse(src_file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    imported: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in module_names:
                    imported.add(base)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                parts = node.module.split(".")
                if len(parts) >= 2 and parts[0] == "src" and parts[1] in module_names:
                    imported.add(parts[1])
                elif parts[0] in module_names:
                    imported.add(parts[0])
    return sorted(imported)


def generate_module_graph(repo_root: Path) -> ModuleGraph:
    """Build the full module interconnection graph from AST analysis."""
    src_dir = repo_root / "src"
    if not src_dir.exists():
        return ModuleGraph()
    module_names = _discover_modules(src_dir)
    name_set = set(module_names)
    nodes: list[ModuleNode] = []
    edges: list = []
    imported_by: dict = {m: [] for m in module_names}
    for mod_name in module_names:
        src_file = src_dir / f"{mod_name}.py"
        imports = _extract_imports(src_file, name_set)
        imports = [i for i in imports if i != mod_name]
        layer = _LAYER_MAP.get(mod_name, "misc")
        nodes.append(ModuleNode(name=mod_name, layer=layer, imports=imports))
        for dep in imports:
            edges.append((mod_name, dep))
            if dep in imported_by:
                imported_by[dep].append(mod_name)
    for node in nodes:
        node.imported_by = imported_by.get(node.name, [])
    layers: dict = {}
    for node in nodes:
        layers.setdefault(node.layer, []).append(node.name)
    return ModuleGraph(nodes=nodes, edges=edges, layers=layers)
