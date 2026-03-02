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
    generated_docstring: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "file": self.file,
            "line": self.line,
            "params": self.params,
            "return_annotation": self.return_annotation,
            "decorators": self.decorators,
            "bases": self.bases,
            "generated_docstring": self.generated_docstring,
        }


@dataclass
class DocstringReport:
    """Full report of missing docstrings across the repo."""

    total_items: int = 0  # total functions + classes scanned
    documented: int = 0
    undocumented: int = 0
    coverage_pct: float = 0.0
    items: list[MissingDocstring] = field(default_factory=list)
    files_scanned: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_items": self.total_items,
            "documented": self.documented,
            "undocumented": self.undocumented,
            "coverage_pct": round(self.coverage_pct, 1),
            "files_scanned": self.files_scanned,
            "items": [i.to_dict() for i in self.items],
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _annotation_to_str(node: ast.expr | None) -> Optional[str]:
    """Convert an AST annotation node to a readable string."""
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return repr(node.value) if isinstance(node.value, str) else str(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        n = node
        while isinstance(n, ast.Attribute):
            parts.append(n.attr)
            n = n.value
        if isinstance(n, ast.Name):
            parts.append(n.id)
        return ".".join(reversed(parts))
    if isinstance(node, ast.Subscript):
        base = _annotation_to_str(node.value)
        sl = _annotation_to_str(node.slice)
        return f"{base}[{sl}]" if base and sl else base
    if isinstance(node, ast.Tuple):
        elts = [_annotation_to_str(e) for e in node.elts]
        return ", ".join(e for e in elts if e)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _annotation_to_str(node.left)
        right = _annotation_to_str(node.right)
        return f"{left} | {right}"
    return None


def _decorator_names(decorators: list[ast.expr]) -> list[str]:
    """Extract decorator names from AST decorator list."""
    names = []
    for d in decorators:
        if isinstance(d, ast.Name):
            names.append(d.id)
        elif isinstance(d, ast.Attribute):
            names.append(_annotation_to_str(d) or "")
        elif isinstance(d, ast.Call):
            if isinstance(d.func, ast.Name):
                names.append(d.func.id)
            elif isinstance(d.func, ast.Attribute):
                names.append(_annotation_to_str(d.func) or "")
    return [n for n in names if n]


def _get_params(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract parameter names, excluding 'self' and 'cls'."""
    params = []
    for arg in func_node.args.args:
        if arg.arg not in ("self", "cls"):
            params.append(arg.arg)
    for arg in func_node.args.kwonlyargs:
        params.append(arg.arg)
    if func_node.args.vararg:
        params.append(f"*{func_node.args.vararg.arg}")
    if func_node.args.kwarg:
        params.append(f"**{func_node.args.kwarg.arg}")
    return params


def _has_docstring(node: ast.AST) -> bool:
    """Check if a function/class node has a docstring."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return False
    if not node.body:
        return False
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        if isinstance(first.value.value, str):
            return True
    return False


# ---------------------------------------------------------------------------
# Name-to-description heuristics
# ---------------------------------------------------------------------------

_VERB_MAP = {
    "get": "Return",
    "set": "Set",
    "is": "Check whether",
    "has": "Check whether item has",
    "can": "Check whether item can",
    "should": "Determine whether to",
    "compute": "Compute",
    "calculate": "Calculate",
    "parse": "Parse",
    "render": "Render",
    "format": "Format",
    "validate": "Validate",
    "check": "Check",
    "find": "Find",
    "search": "Search for",
    "load": "Load",
    "save": "Save",
    "write": "Write",
    "read": "Read",
    "create": "Create",
    "build": "Build",
    "make": "Construct",
    "init": "Initialise",
    "setup": "Set up",
    "run": "Run",
    "execute": "Execute",
    "process": "Process",
    "handle": "Handle",
    "convert": "Convert",
    "transform": "Transform",
    "extract": "Extract",
    "generate": "Generate",
    "update": "Update",
    "delete": "Delete",
    "remove": "Remove",
    "add": "Add",
    "append": "Append",
    "insert": "Insert",
    "merge": "Merge",
    "split": "Split",
    "filter": "Filter",
    "sort": "Sort",
    "count": "Count",
    "sum": "Sum",
    "avg": "Compute average of",
    "to": "Convert to",
    "from": "Create from",
    "ensure": "Ensure",
    "apply": "Apply",
    "reset": "Reset",
    "clear": "Clear",
    "close": "Close",
    "open": "Open",
    "start": "Start",
    "stop": "Stop",
    "emit": "Emit",
    "dispatch": "Dispatch",
    "notify": "Notify",
    "register": "Register",
    "unregister": "Unregister",
    "collect": "Collect",
    "aggregate": "Aggregate",
    "scan": "Scan",
    "analyze": "Analyse",
    "analyse": "Analyse",
    "score": "Score",
    "grade": "Grade",
    "rank": "Rank",
    "compare": "Compare",
    "diff": "Diff",
    "patch": "Patch",
    "test": "Test",
    "verify": "Verify",
    "assert": "Assert",
    "dump": "Dump",
    "serialize": "Serialise",
    "deserialize": "Deserialise",
    "encode": "Encode",
    "decode": "Decode",
    "compress": "Compress",
    "decompress": "Decompress",
    "log": "Log",
    "print": "Print",
    "display": "Display",
    "show": "Show",
    "hide": "Hide",
    "toggle": "Toggle",
    "enable": "Enable",
    "disable": "Disable",
}


def _name_to_description(name: str) -> str:
    """Convert a snake_case function name to a natural-language description.

    Examples
    --------
    >>> _name_to_description("get_health_score")
    'Return the health score.'
    >>> _name_to_description("_parse_config_file")
    'Parse the config file.'
    >>> _name_to_description("__repr__")
    'Return string representation.'
    """
    # Handle dunder methods
    clean = name.strip("_")
    if not clean:
        return "No description available."

    dunder_map = {
        "init": "Initialise the instance.",
        "repr": "Return string representation.",
        "str": "Return human-readable string.",
        "len": "Return the length.",
        "iter": "Return an iterator.",
        "next": "Return the next item.",
        "enter": "Enter the context manager.",
        "exit": "Exit the context manager.",
        "eq": "Check equality.",
        "ne": "Check inequality.",
        "lt": "Check less-than.",
        "gt": "Check greater-than.",
        "le": "Check less-than-or-equal.",
        "ge": "Check greater-than-or-equal.",
        "hash": "Return the hash.",
        "bool": "Return boolean value.",
        "getitem": "Get item by key.",
        "setitem": "Set item by key.",
        "delitem": "Delete item by key.",
        "contains": "Check membership.",
        "call": "Call the instance.",
        "add": "Addition operator.",
        "sub": "Subtraction operator.",
        "mul": "Multiplication operator.",
        "truediv": "Division operator.",
        "floordiv": "Floor division operator.",
        "mod": "Modulo operator.",
        "pow": "Power operator.",
        "and": "Bitwise AND.",
        "or": "Bitwise OR.",
        "xor": "Bitwise XOR.",
    }
    if clean in dunder_map:
        return dunder_map[clean]

    parts = clean.split("_")
    if not parts:
        return "No description available."

    verb = parts[0].lower()
    rest = parts[1:]

    if verb in _VERB_MAP:
        rest_str = " ".join(rest) if rest else ""
        prefix = _VERB_MAP[verb]
        if rest_str:
            # Add "the" for readability unless the prefix already sounds natural
            if prefix.endswith(("for", "to", "whether", "has", "can")):
                return f"{prefix} {rest_str}."
            else:
                return f"{prefix} the {rest_str}."
        else:
            return f"{prefix}."
    else:
        # Fallback: join all parts
        return " ".join(parts).capitalize() + "."


def _class_description(name: str, bases: list[str]) -> str:
    """Generate a class docstring from name and bases."""
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", name).split()
    desc = " ".join(w.lower() for w in words)
    if bases:
        return f"A {desc} ({', '.join(bases)})."
    return f"A {desc}."


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def generate_docstring(item: MissingDocstring) -> str:
    """Generate a docstring for a single undocumented item.

    Parameters
    ----------
    item:
        A ``MissingDocstring`` instance.

    Returns
    -------
    str
        The generated docstring text (without triple-quote delimiters).
    """
    if item.kind == "class":
        desc = _class_description(item.name, item.bases)
        return desc

    desc = _name_to_description(item.name)

    lines = [desc]

    # Add Parameters section if there are params
    if item.params:
        lines.append("")
        lines.append("Parameters")
        lines.append("----------")
        for p in item.params:
            clean_p = p.lstrip("*")
            lines.append(f"{clean_p}:")
            lines.append(f"    {clean_p.replace('_', ' ').capitalize()} value.")

    # Add Returns section if there's a return annotation
    if item.return_annotation and item.return_annotation not in ("None",):
        lines.append("")
        lines.append("Returns")
        lines.append("-------")
        lines.append(item.return_annotation)

    return "\n".join(lines)


def scan_missing_docstrings(repo_path: str | Path) -> DocstringReport:
    """Scan all Python files under ``src/`` for missing docstrings.

    Parameters
    ----------
    repo_path:
        Path to the repository root.

    Returns
    -------
    DocstringReport
    """
    repo = Path(repo_path)
    src_dir = repo / "src"
    if not src_dir.exists():
        return DocstringReport(errors=[f"src/ not found at {repo}"])

    report = DocstringReport()
    py_files = sorted(src_dir.rglob("*.py"))
    report.files_scanned = len(py_files)

    for py_file in py_files:
        rel = str(py_file.relative_to(repo))
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError) as e:
            report.errors.append(f"{rel}: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                report.total_items += 1
                if _has_docstring(node):
                    report.documented += 1
                else:
                    report.undocumented += 1
                    bases = []
                    for b in node.bases:
                        bs = _annotation_to_str(b)
                        if bs:
                            bases.append(bs)
                    item = MissingDocstring(
                        kind="class",
                        name=node.name,
                        qualified_name=f"{rel}::{node.name}",
                        file=rel,
                        line=node.lineno,
                        bases=bases,
                    )
                    item.generated_docstring = generate_docstring(item)
                    report.items.append(item)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                report.total_items += 1
                if _has_docstring(node):
                    report.documented += 1
                else:
                    report.undocumented += 1
                    # Determine if it's a method (parent is a ClassDef)
                    kind = "function"
                    # We can't easily get parent from ast.walk, so check name hints
                    params = _get_params(node)
                    # Check if first arg in .args.args is self/cls
                    if node.args.args and node.args.args[0].arg in ("self", "cls"):
                        kind = "method"

                    ret = _annotation_to_str(node.returns)
                    decos = _decorator_names(node.decorator_list)

                    item = MissingDocstring(
                        kind=kind,
                        name=node.name,
                        qualified_name=f"{rel}::{node.name}",
                        file=rel,
                        line=node.lineno,
                        params=params,
                        return_annotation=ret,
                        decorators=decos,
                    )
                    item.generated_docstring = generate_docstring(item)
                    report.items.append(item)

    if report.total_items > 0:
        report.coverage_pct = (report.documented / report.total_items) * 100

    return report


def apply_docstrings(
    report: DocstringReport,
    repo_path: str | Path,
    *,
    dry_run: bool = True,
) -> list[str]:
    """Insert generated docstrings into source files.

    Parameters
    ----------
    report:
        A ``DocstringReport`` with generated docstrings.
    repo_path:
        Path to the repository root.
    dry_run:
        If True (default), only report what would change without writing.

    Returns
    -------
    list[str]
        List of file paths that were (or would be) modified.
    """
    repo = Path(repo_path)
    # Group items by file
    by_file: dict[str, list[MissingDocstring]] = {}
    for item in report.items:
        if item.generated_docstring:
            by_file.setdefault(item.file, []).append(item)

    modified = []
    for rel, items in sorted(by_file.items()):
        fpath = repo / rel
        if not fpath.exists():
            continue

        source = fpath.read_text(encoding="utf-8")
        lines = source.splitlines(keepends=True)

        # Sort items by line number in reverse so insertions don't shift lines
        items_sorted = sorted(items, key=lambda x: x.line, reverse=True)

        for item in items_sorted:
            if item.line < 1 or item.line > len(lines):
                continue

            # Find the colon at the end of the def/class line
            idx = item.line - 1  # 0-based
            # Find the line with the colon (might span multiple lines)
            colon_line = idx
            while colon_line < len(lines) and ":" not in lines[colon_line]:
                colon_line += 1

            if colon_line >= len(lines):
                continue

            # Determine indentation of the body
            body_line = colon_line + 1
            if body_line < len(lines):
                existing = lines[body_line]
                indent = len(existing) - len(existing.lstrip())
                if indent == 0:
                    # Fallback: use def line indent + 4
                    def_indent = len(lines[idx]) - len(lines[idx].lstrip())
                    indent = def_indent + 4
            else:
                def_indent = len(lines[idx]) - len(lines[idx].lstrip())
                indent = def_indent + 4

            pad = " " * indent
            ds = item.generated_docstring
            if "\n" in ds:
                # Multi-line
                ds_lines = ds.split("\n")
                docstring_text = f'{pad}"""{ds_lines[0]}\n'
                for dl in ds_lines[1:]:
                    docstring_text += f"{pad}{dl}\n" if dl.strip() else f"\n"
                docstring_text += f'{pad}"""\n'
            else:
                docstring_text = f'{pad}"""{ds}"""\n'

            # Insert after the colon line
            lines.insert(body_line, docstring_text)

        if not dry_run:
            fpath.write_text("".join(lines), encoding="utf-8")
        modified.append(rel)

    return modified


def save_docstring_report(report: DocstringReport, out_path: str | Path) -> None:
    """Save the docstring report as JSON.

    Parameters
    ----------
    report:
        The report to save.
    out_path:
        Output file path.
    """
    Path(out_path).write_text(
        json.dumps(report.to_dict(), indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: DocstringReport) -> str:
    """Render the docstring report as Markdown.

    Parameters
    ----------
    report:
        The report to render.

    Returns
    -------
    str
    """
    lines = [
        "# Docstring Coverage Report",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files scanned | {report.files_scanned} |",
        f"| Total items | {report.total_items} |",
        f"| Documented | {report.documented} |",
        f"| Undocumented | {report.undocumented} |",
        f"| Coverage | {report.coverage_pct:.1f}% |",
        "",
    ]

    if report.items:
        lines.append("## Undocumented Items")
        lines.append("")
        lines.append("| File | Line | Kind | Name | Generated |")
        lines.append("|------|------|------|------|-----------|")
        for item in sorted(report.items, key=lambda x: (x.file, x.line)):
            preview = (item.generated_docstring or "")[:50].replace("|", "\\|")
            lines.append(
                f"| {item.file} | {item.line} | {item.kind} | `{item.name}` | {preview}... |"
            )
        lines.append("")

    if report.errors:
        lines.append("## Errors")
        lines.append("")
        for err in report.errors:
            lines.append(f"- {err}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for docstring generation.

    Examples
    --------
    python -m src.docstring_gen
    python -m src.docstring_gen --apply --dry-run
    python -m src.docstring_gen --json
    """
    import argparse

    p = argparse.ArgumentParser(prog="awake-docstrings")
    p.add_argument(
        "--repo", default=None, help="Repository root (default: auto-detect)"
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Insert generated docstrings into source files",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files (implies --apply)",
    )
    p.add_argument("--write", action="store_true", help="Write report to docs/")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    args = p.parse_args(argv)

    # Resolve repo root
    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    report = scan_missing_docstrings(repo_path)

    if args.apply or args.dry_run:
        modified = apply_docstrings(report, repo_path, dry_run=args.dry_run)
        action = "Would modify" if args.dry_run else "Modified"
        for m in modified:
            print(f"  {action}: {m}")
        if not modified:
            print("  No files to modify.")
        print()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_markdown(report))

    if args.write:
        docs = repo_path / "docs"
        docs.mkdir(exist_ok=True)
        save_docstring_report(report, docs / "docstring_report.json")
        (docs / "docstring_report.md").write_text(
            render_markdown(report), encoding="utf-8"
        )
        print(f"  Wrote docs/docstring_report.json")
        print(f"  Wrote docs/docstring_report.md")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
