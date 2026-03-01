"""Docstring generator for Awake.

Scans the repository for Python modules and functions that are missing
docstrings, then produces stub docstrings using a simple template engine.

The generator intentionally avoids LLM calls; it produces deterministic,
structurally-valid docstrings that can later be enriched by a human or AI.

CLI
---
    awake docstrings                # Show missing-docstring report
    awake docstrings --apply        # Write stubs to source files
    awake docstrings --dry-run      # Preview changes without writing
    awake docstrings --write        # Write JSON + Markdown report to docs/
    awake docstrings --json         # Emit JSON to stdout
"""

from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class MissingDocstring:
    """A single location where a docstring is absent."""

    file: str
    line: int
    kind: str          # "module", "class", "function", "method"
    name: str
    stub: str = ""     # generated stub text (filled later)
    context: str = ""  # up to 3 lines of source context

    def to_dict(self) -> dict:
        """Return a dictionary representation of the missing docstring entry."""
        return asdict(self)


@dataclass
class DocstringReport:
    """Aggregate report: coverage metrics and list of missing locations."""

    repo_path: str
    total_checked: int = 0
    missing_count: int = 0
    coverage_pct: float = 0.0
    missing: list[MissingDocstring] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the report."""
        return {
            "repo_path": self.repo_path,
            "total_checked": self.total_checked,
            "missing_count": self.missing_count,
            "coverage_pct": round(self.coverage_pct, 1),
            "missing": [m.to_dict() for m in self.missing],
        }


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _has_docstring(node: ast.AST) -> bool:
    """Return True if *node* already has a docstring."""
    body = getattr(node, "body", [])
    if not body:
        return False
    first = body[0]
    return (
        isinstance(first, ast.Expr)
        and isinstance(getattr(first, "value", None), ast.Constant)
        and isinstance(first.value.value, str)
    )


def _node_name(node: ast.AST) -> str:
    """Return the human-readable name of an AST node."""
    return getattr(node, "name", "<anonymous>")


def _source_context(lines: list[str], lineno: int, window: int = 2) -> str:
    """Return up to *window* lines around *lineno* (1-based) as a string."""
    start = max(0, lineno - 1 - window)
    end = min(len(lines), lineno - 1 + window + 1)
    snippet = lines[start:end]
    return "\n".join(snippet).strip()


# ---------------------------------------------------------------------------
# Stub generator
# ---------------------------------------------------------------------------

_KIND_TEMPLATES: dict[str, str] = {
    "module": "{name} module.",
    "class": "{name} class.",
    "function": "{name}.",
    "method": "{name}.",
}


def _generate_stub(kind: str, name: str, node: ast.AST) -> str:
    """Generate a minimal docstring stub for the given node."""
    template = _KIND_TEMPLATES.get(kind, "{name}.")
    summary = template.format(name=name)

    # For functions/methods, add Args/Returns sections if they have params
    if kind in ("function", "method"):
        func_node = node  # type: ignore[assignment]
        args = getattr(getattr(func_node, "args", None), "args", [])
        # Filter out 'self' and 'cls'
        params = [a.arg for a in args if a.arg not in ("self", "cls")]
        if params:
            args_block = "\n".join(f"    {p}: Description of {p}." for p in params)
            returns = getattr(func_node, "returns", None)
            returns_line = "    Description of return value." if returns else ""
            if returns_line:
                return (
                    f"{summary}\n\nArgs:\n{args_block}\n\nReturns:\n{returns_line}"
                )
            return f"{summary}\n\nArgs:\n{args_block}"
    return summary


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def _scan_file(
    path: Path,
    repo_root: Path,
) -> tuple[list[MissingDocstring], int]:
    """Scan a single Python file and return (missing_list, total_checked)."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return [], 0

    lines = source.splitlines()
    rel_path = str(path.relative_to(repo_root))
    missing: list[MissingDocstring] = []
    total = 0

    # Module-level docstring
    total += 1
    if not _has_docstring(tree):
        stub = _generate_stub("module", path.stem, tree)
        missing.append(
            MissingDocstring(
                file=rel_path, line=1, kind="module", name=path.stem,
                stub=stub, context=_source_context(lines, 1),
            )
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            total += 1
            if not _has_docstring(node):
                stub = _generate_stub("class", _node_name(node), node)
                missing.append(
                    MissingDocstring(
                        file=rel_path,
                        line=node.lineno,
                        kind="class",
                        name=_node_name(node),
                        stub=stub,
                        context=_source_context(lines, node.lineno),
                    )
                )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1
            kind = "method" if "self" in [a.arg for a in node.args.args] else "function"
            if not _has_docstring(node):
                stub = _generate_stub(kind, _node_name(node), node)
                missing.append(
                    MissingDocstring(
                        file=rel_path,
                        line=node.lineno,
                        kind=kind,
                        name=_node_name(node),
                        stub=stub,
                        context=_source_context(lines, node.lineno),
                    )
                )
    return missing, total


def scan_missing_docstrings(repo_root: Path) -> DocstringReport:
    """Scan the entire repository for missing docstrings."""
    src_dir = repo_root / "src"
    if not src_dir.exists():
        src_dir = repo_root

    all_missing: list[MissingDocstring] = []
    total_checked = 0

    for py_file in sorted(src_dir.rglob("*.py")):
        missing, checked = _scan_file(py_file, repo_root)
        all_missing.extend(missing)
        total_checked += checked

    coverage = (
        (total_checked - len(all_missing)) / total_checked * 100
        if total_checked
        else 100.0
    )
    return DocstringReport(
        repo_path=str(repo_root),
        total_checked=total_checked,
        missing_count=len(all_missing),
        coverage_pct=round(coverage, 1),
        missing=all_missing,
    )


# ---------------------------------------------------------------------------
# Applier
# ---------------------------------------------------------------------------


def apply_docstrings(
    report: DocstringReport,
    repo_root: Path,
    dry_run: bool = False,
) -> list[str]:
    """Insert stub docstrings into source files.

    Args:
        report: DocstringReport with the list of missing docstrings.
        repo_root: Root path of the repository.
        dry_run: If True, do not write changes to disk.

    Returns:
        List of relative file paths that were (or would be) modified.
    """
    from collections import defaultdict
    import tokenize
    import io

    # Group by file
    by_file: dict[str, list[MissingDocstring]] = defaultdict(list)
    for item in report.missing:
        by_file[item.file].append(item)

    modified: list[str] = []

    for rel_path, items in by_file.items():
        path = repo_root / rel_path
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue

        lines = source.splitlines(keepends=True)
        # Sort by line descending so insertions don't shift later line numbers
        items_sorted = sorted(items, key=lambda x: x.line, reverse=True)

        changed = False
        for item in items_sorted:
            insert_after = _find_insert_line(lines, item.line, item.kind)
            if insert_after is None:
                continue
            indent = _detect_indent(lines, item.line)
            docstring = _format_docstring(item.stub, indent)
            lines.insert(insert_after, docstring + "\n")
            changed = True

        if changed:
            modified.append(rel_path)
            if not dry_run:
                path.write_text("".join(lines), encoding="utf-8")

    return modified


def _find_insert_line(lines: list[str], def_lineno: int, kind: str) -> Optional[int]:
    """Find the line index (0-based) *after* which to insert the docstring.

    For modules (kind=="module"), insert at line 0.
    For classes/functions, insert after the `def` or `class` header line,
    accounting for multi-line signatures.
    """
    if kind == "module":
        # Insert before any existing content on line 0
        return 0

    idx = def_lineno - 1  # 0-based
    # Advance past multi-line signatures (lines ending with `(`, `,`, `:` continuation)
    while idx < len(lines):
        stripped = lines[idx].rstrip()
        if stripped.endswith(":"):
            return idx + 1
        idx += 1
    return None


def _detect_indent(lines: list[str], def_lineno: int) -> str:
    """Detect the indentation of the def/class line."""
    idx = def_lineno - 1
    if idx < len(lines):
        raw = lines[idx]
        return raw[: len(raw) - len(raw.lstrip())]
    return ""


def _format_docstring(stub: str, indent: str) -> str:
    """Wrap *stub* in triple-quotes with consistent indentation."""
    inner_indent = indent + "    "
    if "\n" in stub:
        body = textwrap.indent(stub, inner_indent)
        return f'{indent}"""\n{body}\n{indent}"""'
    return f'{indent}"""{ stub }"""'


# ---------------------------------------------------------------------------
# Report writers
# ---------------------------------------------------------------------------


def save_docstring_report(report: DocstringReport, output_path: Path) -> None:
    """Serialise the report to a JSON file."""
    import json
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )


def render_markdown(report: DocstringReport) -> str:
    """Render the report as a Markdown document."""
    lines: list[str] = [
        "## Docstring Coverage Report",
        "",
        f"| Metric | Value |",
        f"|--------|-------|]",
        f"| Repo | `{report.repo_path}` |",
        f"| Total checked | {report.total_checked} |",
        f"| Missing | {report.missing_count} |",
        f"| Coverage | **{report.coverage_pct:.1f}%** |",
        "",
    ]
    if report.missing:
        lines += [
            "### Missing Docstrings",
            "",
            "| File | Line | Kind | Name |",
            "|------|------|------|------|",
        ]
        for m in report.missing[:50]:  # cap at 50 rows
            lines.append(f"| `{m.file}` | {m.line} | {m.kind} | `{m.name}` |")
        if len(report.missing) > 50:
            lines.append(f"| ... | | | _{len(report.missing) - 50} more_ |")
        lines.append("")
    return "\n".join(lines)
