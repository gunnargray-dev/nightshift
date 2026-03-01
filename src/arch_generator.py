"""Architecture documentation auto-generator for Awake.

Walks the entire repository using AST analysis and produces a rich
``docs/ARCHITECTURE.md`` that is always in sync with the actual codebase.

Generated sections
------------------
1. Directory tree (full repo layout)
2. Module inventory — each src/ file with its docstring summary, public API
   (classes, functions), and line count
3. Dependency graph — which modules import which (rendered as a Markdown table
   and a simple ASCII adjacency list)
4. Data-flow overview — dataclasses defined and where they are consumed
5. Design principles — copied from constants in this module so humans can
   update them without touching the generator
6. Stats snapshot — total functions, classes, lines, test coverage (if available)

The generator deliberately avoids external dependencies beyond the stdlib.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Design principles (human-editable constants)
# ---------------------------------------------------------------------------

DESIGN_PRINCIPLES = [
    "**Self-awareness** — The system can inspect and analyze its own codebase.",
    "**Self-improvement** — Each session should make future sessions better.",
    "**Transparency** — Every decision is logged and every PR explains itself.",
    "**Testability** — All code is tested before being pushed.",
    "**Zero runtime deps** — src/ uses only stdlib; heavy tools are dev-only.",
    "**Composability** — Each module is independently usable; the CLI composes them.",
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FunctionInfo:
    """Metadata for a single function or method."""

    name: str
    lineno: int
    is_async: bool = False
    docstring: str = ""
    args: list[str] = field(default_factory=list)
    returns: str = ""


@dataclass
class ClassInfo:
    """Metadata for a class definition."""

    name: str
    lineno: int
    docstring: str = ""
    bases: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """Full metadata for one Python source module."""

    path: str               # relative path, e.g. "src/stats.py"
    name: str               # module name without .py
    docstring: str = ""
    lines: int = 0
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)   # top-level imports


@dataclass
class ArchitectureDoc:
    """The complete generated architecture document (as Markdown string)."""

    content: str
    generated_at: str


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _first_docstring(node: ast.AST) -> str:
    """Return the first string constant in a node's body, or ''."""
    body = getattr(node, "body", [])
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        val = body[0].value.value
        if isinstance(val, str):
            for line in val.strip().splitlines():
                if line.strip():
                    return line.strip()
    return ""


def _arg_names(args: ast.arguments) -> list[str]:
    """Extract argument names from a function's argument list."""
    names = [a.arg for a in args.args]
    if args.vararg:
        names.append(f"*{args.vararg.arg}")
    names += [a.arg for a in args.kwonlyargs]
    if args.kwarg:
        names.append(f"**{args.kwarg.arg}")
    return names


def _return_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return the string representation of a return annotation, or ''."""
    if node.returns is None:
        return ""
    try:
        return ast.unparse(node.returns)
    except Exception:
        return ""


def _top_level_imports(tree: ast.Module) -> list[str]:
    """Return the module names imported at the top level."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module.split(".")[0])
    return sorted(set(names))


def _parse_module(path: Path, repo_root: Path) -> Optional[ModuleInfo]:
    """Parse a Python file into a ModuleInfo object."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return None

    rel = str(path.relative_to(repo_root))
    name = path.stem
    info = ModuleInfo(
        path=rel,
        name=name,
        docstring=_first_docstring(tree),
        lines=len(source.splitlines()),
        imports=_top_level_imports(tree),
    )

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = []
            for b in node.bases:
                try:
                    bases.append(ast.unparse(b))
                except Exception:
                    pass
            methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(FunctionInfo(
                        name=item.name,
                        lineno=item.lineno,
                        is_async=isinstance(item, ast.AsyncFunctionDef),
                        docstring=_first_docstring(item),
                        args=_arg_names(item.args),
                        returns=_return_annotation(item),
                    ))
            info.classes.append(ClassInfo(
                name=node.name,
                lineno=node.lineno,
                docstring=_first_docstring(node),
                bases=bases,
                methods=methods,
            ))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.functions.append(FunctionInfo(
                name=node.name,
                lineno=node.lineno,
                is_async=isinstance(node, ast.AsyncFunctionDef),
                docstring=_first_docstring(node),
                args=_arg_names(node.args),
                returns=_return_annotation(node),
            ))

    return info


# ---------------------------------------------------------------------------
# Directory tree renderer
# ---------------------------------------------------------------------------

_IGNORE = {".git", "__pycache__", ".pytest_cache", "*.egg-info", ".mypy_cache", "node_modules", ".venv", "venv"}


def _render_tree(root: Path, prefix: str = "", _rel: Path = Path(".")) -> list[str]:
    """Recursively render directory tree as list of strings."""
    lines = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return lines

    entries = [e for e in entries if not any(
        e.name == ig or e.name.endswith(ig.lstrip("*")) for ig in _IGNORE
    )]

    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        ext_prefix = "    " if i == len(entries) - 1 else "│   "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir():
            lines.extend(_render_tree(entry, prefix + ext_prefix, _rel / entry.name))

    return lines


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def _render_module_section(info: ModuleInfo) -> str:
    """Render one module as a Markdown subsection."""
    lines = [
        f"### `{info.path}`",
        "",
        f"*{info.docstring}*" if info.docstring else "*No module docstring.*",
        "",
        f"**{info.lines} lines** \u00b7 "
        f"**{len(info.classes)} class(es)** \u00b7 "
        f"**{len(info.functions)} top-level function(s)**",
        "",
    ]

    if info.classes:
        lines.append("**Classes:**")
        lines.append("")
        for cls in info.classes:
            base_str = f"({', '.join(cls.bases)})" if cls.bases else ""
            doc_str = f" — {cls.docstring}" if cls.docstring else ""
            lines.append(f"- `{cls.name}{base_str}`{doc_str}")
            public_methods = [m for m in cls.methods if not m.name.startswith("_") or m.name in ("__init__", "__post_init__")]
            for m in public_methods[:6]:
                ret = f" → `{m.returns}`" if m.returns else ""
                lines.append(f"  - `{'async ' if m.is_async else ''}{m.name}({', '.join(m.args)}){ret}`")
        lines.append("")

    if info.functions:
        lines.append("**Public functions:**")
        lines.append("")
        for fn in info.functions:
            if fn.name.startswith("_"):
                continue
            ret = f" → `{fn.returns}`" if fn.returns else ""
            doc_str = f" — {fn.docstring}" if fn.docstring else ""
            lines.append(f"- `{'async ' if fn.is_async else ''}{fn.name}({', '.join(fn.args)}){ret}`{doc_str}")
        lines.append("")

    return "\n".join(lines)


def _render_dep_graph(modules: list[ModuleInfo]) -> str:
    """Render a dependency graph showing which src modules import each other."""
    src_names = {m.name for m in modules}
    lines = [
        "| Module | Imports from src/ |",
        "|--------|-------------------|",
    ]
    for m in sorted(modules, key=lambda x: x.name):
        cross_imports = sorted(imp for imp in m.imports if imp in src_names and imp != m.name)
        dep_str = ", ".join(f"`{d}`" for d in cross_imports) if cross_imports else "*(standalone)*"
        lines.append(f"| `{m.name}` | {dep_str} |")
    return "\n".join(lines)


def _render_dataclass_inventory(modules: list[ModuleInfo]) -> str:
    """List all dataclasses and their home modules."""
    lines = [
        "| Dataclass | Module | Description |",
        "|-----------|--------|-------------|",
    ]
    found = False
    for m in sorted(modules, key=lambda x: x.name):
        for cls in m.classes:
            doc_str = cls.docstring or "—"
            lines.append(f"| `{cls.name}` | `{m.name}` | {doc_str} |")
            found = True
    if not found:
        return "*No dataclasses found.*"
    return "\n".join(lines)


def generate_architecture_doc(repo_path: Optional[Path] = None) -> str:
    """Generate the full ARCHITECTURE.md content as a string.

    Args:
        repo_path: Root of the repository. Defaults to CWD.

    Returns:
        Markdown string for docs/ARCHITECTURE.md.
    """
    root = repo_path or Path.cwd()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    src_dir = root / "src"
    modules: list[ModuleInfo] = []
    if src_dir.exists():
        for py_file in sorted(src_dir.glob("*.py")):
            if py_file.name == "__init__.py":
                continue
            info = _parse_module(py_file, root)
            if info:
                modules.append(info)

    total_lines = sum(m.lines for m in modules)
    total_classes = sum(len(m.classes) for m in modules)
    total_functions = sum(len(m.functions) for m in modules)

    parts: list[str] = []
    parts.append(f"# Architecture\n\n*Auto-generated by Awake on {ts}.*\n")

    parts.append("## Repository Structure\n\n```")
    parts.append("awake/")
    parts.extend(_render_tree(root))
    parts.append("```\n")

    parts.append(
        "## Codebase Stats\n\n"
        "| Metric | Value |\n"
        "|--------|-------|\n"
        f"| Source modules | {len(modules)} |\n"
        f"| Total source lines | {total_lines} |\n"
        f"| Classes | {total_classes} |\n"
        f"| Top-level functions | {total_functions} |\n"
    )

    parts.append("## Design Principles\n")
    for i, principle in enumerate(DESIGN_PRINCIPLES, start=1):
        parts.append(f"{i}. {principle}")
    parts.append("")

    parts.append("## Module Inventory\n")
    for m in modules:
        parts.append(_render_module_section(m))

    parts.append("## Internal Dependency Graph\n")
    parts.append(_render_dep_graph(modules))
    parts.append("")

    parts.append("## Dataclass Inventory\n")
    parts.append(_render_dataclass_inventory(modules))
    parts.append("")

    parts.append("---\n")
    parts.append("*Generated automatically by `src/arch_generator.py`. Do not edit by hand.*\n")

    return "\n".join(parts)


def save_architecture_doc(content: str, output_path: Path) -> None:
    """Write the architecture document to disk.

    Args:
        content: Markdown string returned by generate_architecture_doc.
        output_path: Destination path (usually docs/ARCHITECTURE.md).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
