"""Automatic docstring generator for Awake.

Scans Python source files via AST to find functions, methods, and classes
that lack docstrings, then generates sensible docstrings based on:

- Function/method name (split on underscores into natural language)
- Parameter names and type annotations
- Return type annotations
- Decorator metadata (e.g. ``@staticmethod``, ``@property``)
- Class base classes

The generated docstrings follow NumPy-style conventions and are intentionally
concise so they serve as useful stubs that a human (or AI) can refine later.

Public API
----------
- ``MissingDocstring``  -- a single undocumented item
- ``DocstringReport``   -- full scan report
- ``scan_missing_docstrings(repo_path)`` -> ``DocstringReport``
- ``generate_docstring(item)`` -> ``str``
- ``apply_docstrings(report, repo_path, *, dry_run=True)`` -> list of patched files
- ``save_docstring_report(report, out_path)``

CLI
---
    awake docstrings [--apply] [--dry-run] [--write] [--json]
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MissingDocstring:
    """A single function, method, or class that lacks a docstring."""

    kind: str  # "function" | "method" | "class"
    name: str
    qualified_name: str  # e.g. "health.py::HealthReport" or "health.py::score_file"
    file: str  # relative path
    line: int  # 1-based
    params: list[str] = field(default_factory=list)
    return_annotation: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)  # for classes


@dataclass
class DocstringReport:
    """Complete docstring scan report."""

    missing: list[MissingDocstring] = field(default_factory=list)
    scanned_files: int = 0
    total_items: int = 0  # functions + methods + classes found

    @property
    def coverage(self) -> float:
        """Return docstring coverage as a value in [0, 1]."""
        if self.total_items == 0:
            return 1.0
        return 1.0 - len(self.missing) / self.total_items


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _node_has_docstring(node: ast.AST) -> bool:
    """Return True if *node* already has a docstring."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    body = node.body
    if not body:
        return False
    first = body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    )


def _annotation_to_str(annotation: Optional[ast.expr]) -> Optional[str]:
    """Convert an AST annotation node to a readable string."""
    if annotation is None:
        return None
    return ast.unparse(annotation)


def _decorator_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    """Return the names (as strings) of decorators applied to *node*."""
    names: list[str] = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(ast.unparse(dec))
        elif isinstance(dec, ast.Call):
            func = dec.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(ast.unparse(func))
    return names


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class _DocstringScanner(ast.NodeVisitor):
    """Walk an AST and collect items that lack docstrings."""

    def __init__(self, rel_path: str) -> None:
        self._path = rel_path
        self._class_stack: list[str] = []
        self.missing: list[MissingDocstring] = []
        self.total_items: int = 0

    # ------------------------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition node."""
        self.total_items += 1
        qualified = f"{self._path}::{node.name}"
        if not _node_has_docstring(node):
            bases = [ast.unparse(b) for b in node.bases]
            self.missing.append(
                MissingDocstring(
                    kind="class",
                    name=node.name,
                    qualified_name=qualified,
                    file=self._path,
                    line=node.lineno,
                    bases=bases,
                    decorators=_decorator_names(node),
                )
            )
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    # ------------------------------------------------------------------
    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Common handler for function and async-function definitions."""
        self.total_items += 1
        if self._class_stack:
            kind = "method"
            qualified = f"{self._path}::{self._class_stack[-1]}.{node.name}"
        else:
            kind = "function"
            qualified = f"{self._path}::{node.name}"

        if not _node_has_docstring(node):
            args = node.args
            params: list[str] = [a.arg for a in args.args]
            # strip self / cls
            if params and params[0] in ("self", "cls"):
                params = params[1:]
            return_ann = _annotation_to_str(node.returns)
            self.missing.append(
                MissingDocstring(
                    kind=kind,
                    name=node.name,
                    qualified_name=qualified,
                    file=self._path,
                    line=node.lineno,
                    params=params,
                    return_annotation=return_ann,
                    decorators=_decorator_names(node),
                )
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Visit a (sync) function definition node."""
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """Visit an async function definition node."""
        self._visit_func(node)


# ---------------------------------------------------------------------------
# Public scan API
# ---------------------------------------------------------------------------


def scan_missing_docstrings(repo_path: str | Path) -> DocstringReport:
    """Scan *repo_path* and return a :class:`DocstringReport`.

    Parameters
    ----------
    repo_path:
        Root directory of the repository to scan.

    Returns
    -------
    DocstringReport
        Report containing all undocumented items.
    """
    root = Path(repo_path)
    report = DocstringReport()

    py_files = sorted(root.rglob("*.py"))
    report.scanned_files = len(py_files)

    for py_file in py_files:
        rel = str(py_file.relative_to(root))
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (SyntaxError, OSError):
            continue

        scanner = _DocstringScanner(rel)
        scanner.visit(tree)
        report.missing.extend(scanner.missing)
        report.total_items += scanner.total_items

    return report


# ---------------------------------------------------------------------------
# Docstring generator
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(r"[_\s]+")


def _humanise(name: str) -> str:
    """Convert *name* (snake_case) to a short human-readable phrase."""
    words = _SPLIT_RE.split(name.strip("_"))
    return " ".join(w for w in words if w)


def generate_docstring(item: MissingDocstring) -> str:
    """Return a generated NumPy-style docstring for *item*.

    Parameters
    ----------
    item:
        The undocumented item to document.

    Returns
    -------
    str
        A docstring string (without the surrounding triple-quotes).
    """
    lines: list[str] = []

    if item.kind == "class":
        desc = _humanise(item.name)
        if item.bases:
            bases_str = ", ".join(item.bases)
            lines.append(f"{desc} ({bases_str}).")
        else:
            lines.append(f"{desc}.")
        return "\n".join(lines)

    # function or method
    desc = _humanise(item.name)
    if "property" in item.decorators:
        lines.append(f"Return {desc}.")
    elif "staticmethod" in item.decorators:
        lines.append(f"{desc}.")
    elif "classmethod" in item.decorators:
        lines.append(f"{desc}.")
    else:
        lines.append(f"{desc}.")

    # Parameters section
    if item.params:
        lines.append("")
        lines.append("Parameters")
        lines.append("----------")
        for p in item.params:
            lines.append(f"{p} :")
            lines.append(f"    {_humanise(p)}.")

    # Returns section
    if item.return_annotation and item.return_annotation not in ("None", "NoReturn"):
        lines.append("")
        lines.append("Returns")
        lines.append("-------")
        lines.append(f"{item.return_annotation}")
        lines.append(f"    {_humanise(item.name)} result.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Patch files
# ---------------------------------------------------------------------------


def _insert_docstring(source: str, item: MissingDocstring, docstring: str) -> str:
    """Return *source* with a docstring inserted for *item*."""
    lines = source.splitlines(keepends=True)
    # Find the line of the def/class statement (1-based -> 0-based)
    def_line_idx = item.line - 1

    # Determine indentation of the def/class line
    def_line = lines[def_line_idx]
    indent = len(def_line) - len(def_line.lstrip())
    body_indent = " " * (indent + 4)

    # Find the colon that ends the signature (may span multiple lines)
    search_start = def_line_idx
    colon_line_idx = def_line_idx
    for i in range(search_start, min(search_start + 20, len(lines))):
        if ":" in lines[i].split("#")[0]:  # ignore comments
            colon_line_idx = i
            break

    insert_idx = colon_line_idx + 1

    # Build the docstring block
    ds_lines = docstring.splitlines()
    if len(ds_lines) == 1:
        block = f'{body_indent}"""{ ds_lines[0]}"""\n'
    else:
        block = f'{body_indent}"""{ ds_lines[0]}\n'
        for dl in ds_lines[1:]:
            block += f"{body_indent}{dl}\n" if dl.strip() else "\n"
        block += f'{body_indent}"""\n'

    lines.insert(insert_idx, block)
    return "".join(lines)


def apply_docstrings(
    report: DocstringReport,
    repo_path: str | Path,
    *,
    dry_run: bool = True,
) -> list[str]:
    """Insert generated docstrings into the source files.

    Parameters
    ----------
    report:
        Report from :func:`scan_missing_docstrings`.
    repo_path:
        Root of the repository.
    dry_run:
        When *True* (default) print patches but do not write files.

    Returns
    -------
    list[str]
        Relative paths of files that were (or would be) patched.
    """
    root = Path(repo_path)
    # Group missing items by file
    by_file: dict[str, list[MissingDocstring]] = {}
    for item in report.missing:
        by_file.setdefault(item.file, []).append(item)

    patched: list[str] = []
    for rel_path, items in sorted(by_file.items()):
        full_path = root / rel_path
        try:
            source = full_path.read_text(encoding="utf-8")
        except OSError:
            continue

        # Sort items in *reverse* line order so insertions don't shift later lines
        for item in sorted(items, key=lambda x: x.line, reverse=True):
            ds = generate_docstring(item)
            source = _insert_docstring(source, item, ds)

        if dry_run:
            print(f"[dry-run] would patch {rel_path}")
        else:
            full_path.write_text(source, encoding="utf-8")

        patched.append(rel_path)

    return patched


# ---------------------------------------------------------------------------
# Save report
# ---------------------------------------------------------------------------


def save_docstring_report(report: DocstringReport, out_path: str | Path) -> None:
    """Serialise *report* to a JSON file at *out_path*.

    Parameters
    ----------
    report:
        The report to save.
    out_path:
        Destination file path.
    """
    data: dict = {
        "scanned_files": report.scanned_files,
        "total_items": report.total_items,
        "coverage": report.coverage,
        "missing_count": len(report.missing),
        "missing": [
            {
                "kind": m.kind,
                "name": m.name,
                "qualified_name": m.qualified_name,
                "file": m.file,
                "line": m.line,
                "params": m.params,
                "return_annotation": m.return_annotation,
                "decorators": m.decorators,
                "bases": m.bases,
            }
            for m in report.missing
        ],
    }
    Path(out_path).write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the docstring generator.

    Parameters
    ----------
    argv:
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake docstrings",
        description="Scan and generate missing docstrings.",
    )
    parser.add_argument(
        "repo",
        nargs="?",
        default=".",
        help="Path to the repository root (default: current directory)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply generated docstrings to source files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be patched without writing (default: True)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write patched files (disables --dry-run)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the report as JSON to stdout",
    )
    args = parser.parse_args(argv)

    repo_path = Path(args.repo).resolve()
    if not repo_path.is_dir():
        print(f"Error: {repo_path} is not a directory", file=sys.stderr)
        return 1

    report = scan_missing_docstrings(repo_path)

    if args.json:
        data = {
            "scanned_files": report.scanned_files,
            "total_items": report.total_items,
            "coverage": report.coverage,
            "missing_count": len(report.missing),
            "missing": [
                {
                    "kind": m.kind,
                    "name": m.name,
                    "qualified_name": m.qualified_name,
                    "file": m.file,
                    "line": m.line,
                    "params": m.params,
                    "return_annotation": m.return_annotation,
                    "decorators": m.decorators,
                    "bases": m.bases,
                }
                for m in report.missing
            ],
        }
        print(json.dumps(data, indent=2))
        return 0

    # Human-readable summary
    print(f"Scanned {report.scanned_files} files, {report.total_items} items")
    print(f"Coverage: {report.coverage:.1%}")
    print(f"Missing docstrings: {len(report.missing)}")

    if args.apply:
        dry = not args.write
        patched = apply_docstrings(report, repo_path, dry_run=dry)
        verb = "Would patch" if dry else "Patched"
        print(f"{verb} {len(patched)} files")

        if not dry:
            save_docstring_report(report, repo_path / "docs/docstring_report.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
