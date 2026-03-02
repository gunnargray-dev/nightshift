"""AI-powered docstring generation for Python source files."""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union


@dataclass
class DocstringConfig:
    """Configuration for docstring generation."""

    model: str = "gpt-4o-mini"
    style: str = "google"  # google | numpy | sphinx
    overwrite: bool = False
    dry_run: bool = False
    max_tokens: int = 512
    temperature: float = 0.2
    include_private: bool = False
    include_dunder: bool = False
    extra_context: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _has_docstring(node: Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]) -> bool:
    """Return True if the node already has a docstring."""
    return (
        bool(node.body)
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    )


def _get_source_segment(source: str, node: ast.AST) -> str:
    """Extract the source lines for a node."""
    lines = source.splitlines()
    start = node.lineno - 1  # type: ignore[attr-defined]
    end = node.end_lineno  # type: ignore[attr-defined]
    return "\n".join(lines[start:end])


def _build_google_docstring(summary: str, params: list[str], returns: Optional[str]) -> str:
    parts = [f'"""\n{summary}\n']
    if params:
        parts.append("\nArgs:\n")
        for p in params:
            parts.append(f"    {p}: TODO\n")
    if returns:
        parts.append(f"\nReturns:\n    {returns}\n")
    parts.append('"""')
    return "".join(parts)


def _build_numpy_docstring(summary: str, params: list[str], returns: Optional[str]) -> str:
    parts = [f'"""\n{summary}\n']
    if params:
        parts.append("\nParameters\n----------\n")
        for p in params:
            parts.append(f"{p} : type\n    TODO\n")
    if returns:
        parts.append(f"\nReturns\n-------\ntype\n    {returns}\n")
    parts.append('"""')
    return "".join(parts)


def _build_sphinx_docstring(summary: str, params: list[str], returns: Optional[str]) -> str:
    parts = [f'"""\n{summary}\n']
    for p in params:
        parts.append(f"\n:param {p}: TODO")
    if returns:
        parts.append(f"\n:returns: {returns}")
    parts.append('\n"""')
    return "".join(parts)


_BUILDERS = {
    "google": _build_google_docstring,
    "numpy": _build_numpy_docstring,
    "sphinx": _build_sphinx_docstring,
}


# ---------------------------------------------------------------------------
# Stub prompt builder (would call LLM in production)
# ---------------------------------------------------------------------------


def _generate_docstring_stub(
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef],
    source: str,
    config: DocstringConfig,
) -> str:
    """Generate a placeholder docstring (production would call the LLM)."""
    name = node.name
    params: list[str] = []
    returns: Optional[str] = None

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        params = [
            a.arg
            for a in node.args.args
            if a.arg not in ("self", "cls")
        ]
        if node.returns:
            returns = ast.unparse(node.returns)

    summary = f"{name.replace('_', ' ').capitalize()}."
    builder = _BUILDERS.get(config.style, _build_google_docstring)
    raw = builder(summary, params, returns)
    # Indent to match the node's indentation
    indent = " " * (node.col_offset + 4)
    return textwrap.indent(raw, indent)


# ---------------------------------------------------------------------------
# Core transformer
# ---------------------------------------------------------------------------


class DocstringInserter(ast.NodeTransformer):
    """AST transformer that inserts missing docstrings."""

    def __init__(self, source: str, config: DocstringConfig) -> None:
        self.source = source
        self.config = config
        self.modified: list[str] = []

    def _maybe_insert(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef],
    ) -> Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]:
        name = node.name

        # Skip private / dunder methods unless configured
        if name.startswith("__") and not self.config.include_dunder:
            return node
        if name.startswith("_") and not name.startswith("__") and not self.config.include_private:
            return node

        if _has_docstring(node) and not self.config.overwrite:
            return node

        docstring = _generate_docstring_stub(node, self.source, self.config)
        doc_node = ast.Expr(value=ast.Constant(value=docstring))
        ast.copy_location(doc_node, node.body[0])

        if _has_docstring(node):
            node.body[0] = doc_node  # overwrite
        else:
            node.body.insert(0, doc_node)

        self.modified.append(name)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:  # type: ignore[override]
        self._maybe_insert(node)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(  # type: ignore[override]
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        self._maybe_insert(node)
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:  # type: ignore[override]
        self._maybe_insert(node)
        self.generic_visit(node)
        return node


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_docstrings_to_source(source: str, config: Optional[DocstringConfig] = None) -> dict:
    """Add missing docstrings to Python *source* code.

    Returns a dict with keys ``modified_source`` and ``modified_functions``.
    """
    cfg = config or DocstringConfig()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"error": str(exc), "modified_source": source, "modified_functions": []}

    inserter = DocstringInserter(source, cfg)
    new_tree = inserter.visit(tree)
    ast.fix_missing_locations(new_tree)

    if cfg.dry_run:
        return {
            "modified_source": source,
            "modified_functions": inserter.modified,
            "dry_run": True,
        }

    try:
        new_source = ast.unparse(new_tree)
    except Exception:  # pragma: no cover
        new_source = source

    return {
        "modified_source": new_source,
        "modified_functions": inserter.modified,
        "dry_run": False,
    }


def add_docstrings_to_file(path: Path, config: Optional[DocstringConfig] = None) -> dict:
    """Add missing docstrings to the Python file at *path*."""
    source = path.read_text(encoding="utf-8")
    result = add_docstrings_to_source(source, config)
    if not result.get("error") and not (config and config.dry_run):
        path.write_text(result["modified_source"], encoding="utf-8")
    result["path"] = str(path)
    return result


def batch_add_docstrings(
    root: Path,
    config: Optional[DocstringConfig] = None,
    glob: str = "**/*.py",
) -> list[dict]:
    """Process all Python files under *root*."""
    results = []
    for py_file in sorted(root.glob(glob)):
        if py_file.is_file():
            results.append(add_docstrings_to_file(py_file, config))
    return results
