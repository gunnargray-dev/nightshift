"""Automated refactoring helpers for awake."""

import ast
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class RefactorResult:
    path: str
    original: str
    refactored: str
    changes: list[str]

    @property
    def changed(self) -> bool:
        return self.original != self.refactored


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_imports(source: str) -> tuple[str, list[str]]:
    """
    Sort and deduplicate top-level import statements.

    Returns:
        (modified_source, list_of_change_descriptions)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, []

    lines = source.splitlines(keepends=True)
    changes: list[str] = []

    # Collect top-level import nodes
    import_nodes = [
        n
        for n in ast.iter_child_nodes(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
    ]
    if not import_nodes:
        return source, []

    first_line = import_nodes[0].lineno - 1
    last_line = import_nodes[-1].end_lineno  # exclusive

    original_block = lines[first_line:last_line]
    import_lines = [l.rstrip() for l in original_block if l.strip()]

    stdlib_imports = []
    third_party_imports = []
    local_imports = []

    for line in import_lines:
        stripped = line.lstrip()
        if stripped.startswith("from .") or stripped.startswith("import ."):
            local_imports.append(line)
        else:
            # Very rough stdlib detection: single-word imports that are stdlib
            m = re.match(r"^(?:from\s+(\S+)|import\s+(\S+))", stripped)
            mod = (m.group(1) or m.group(2)).split(".")[0] if m else ""
            try:
                import importlib.util as _ilu

                spec = _ilu.find_spec(mod)
                if spec and (spec.origin or "").startswith((__import__("sysconfig").get_path("stdlib"),)):
                    stdlib_imports.append(line)
                else:
                    third_party_imports.append(line)
            except Exception:  # noqa: BLE001
                third_party_imports.append(line)

    def _sort(lst):
        return sorted(set(lst))

    new_block_lines = []
    for group in (_sort(stdlib_imports), _sort(third_party_imports), _sort(local_imports)):
        if group:
            new_block_lines.extend(group)
            new_block_lines.append("")  # blank separator

    # Remove trailing blank
    while new_block_lines and not new_block_lines[-1]:
        new_block_lines.pop()

    new_block = [l + "\n" for l in new_block_lines]

    if new_block != original_block:
        changes.append("Sorted and deduplicated imports")
        lines[first_line:last_line] = new_block

    return "".join(lines), changes


def _remove_unused_variables(source: str) -> tuple[str, list[str]]:
    """
    Remove simple unused variable assignments of the form ``x = <expr>``
    at module level when ``x`` is never referenced afterwards.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, []

    # Collect names of all *loads* (references)
    loaded: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded.add(node.id)

    # Collect top-level simple assignments where the target is never loaded
    lines = source.splitlines(keepends=True)
    to_remove: list[tuple[int, int]] = []  # (start_lineno-1, end_lineno)
    changes: list[str] = []

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name.startswith("_") or name in loaded:
            continue
        to_remove.append((node.lineno - 1, node.end_lineno))
        changes.append(f"Removed unused variable '{name}'")

    # Remove in reverse order to preserve line numbers
    for start, end in reversed(to_remove):
        del lines[start:end]

    return "".join(lines), changes


def _add_missing_docstrings(source: str) -> tuple[str, list[str]]:
    """Add a placeholder docstring to any public function/class missing one."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source, []

    lines = source.splitlines(keepends=True)
    insertions: list[tuple[int, str]] = []  # (line index after def, docstring)
    changes: list[str] = []

    nodes = [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]

    for node in nodes:
        if node.name.startswith("_"):
            continue
        # Check if first statement is a docstring
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(
            node.body[0].value, ast.Constant
        ):
            continue

        # Determine indent from the def/class line
        def_line = lines[node.lineno - 1]
        indent = len(def_line) - len(def_line.lstrip())
        body_indent = " " * (indent + 4)
        placeholder = f'{body_indent}"""TODO: add docstring."""\n'

        # Insert after the colon line (node.lineno)
        insertions.append((node.lineno, placeholder))
        changes.append(f"Added placeholder docstring to '{node.name}'")

    # Apply insertions in reverse order
    for lineno, doc in sorted(insertions, reverse=True):
        lines.insert(lineno, doc)

    return "".join(lines), changes


def _wrap_long_lines(
    source: str, max_length: int = 120
) -> tuple[str, list[str]]:
    """Naively break comment lines and string literals that exceed max_length."""
    lines = source.splitlines(keepends=True)
    changes: list[str] = []
    new_lines = []

    for i, line in enumerate(lines):
        stripped = line.rstrip("\n")
        if len(stripped) <= max_length:
            new_lines.append(line)
            continue

        # Only attempt to wrap pure comment lines
        lstripped = stripped.lstrip()
        if lstripped.startswith("#"):
            indent = len(stripped) - len(lstripped)
            wrapped = textwrap.fill(
                lstripped[1:].strip(),
                width=max_length - indent - 2,
                initial_indent=" " * indent + "# ",
                subsequent_indent=" " * indent + "# ",
            )
            new_lines.append(wrapped + "\n")
            changes.append(f"Wrapped long comment on line {i + 1}")
        else:
            new_lines.append(line)

    return "".join(new_lines), changes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def refactor_source(
    source: str,
    *,
    normalize_imports: bool = True,
    remove_unused: bool = True,
    add_docstrings: bool = False,
    wrap_long_lines: bool = False,
    max_line_length: int = 120,
) -> RefactorResult:
    """
    Apply a set of safe refactoring passes to Python source code.

    Args:
        source: The source code string to refactor.
        normalize_imports: Sort and deduplicate imports.
        remove_unused: Remove obviously unused module-level variables.
        add_docstrings: Add placeholder docstrings to undocumented public items.
        wrap_long_lines: Wrap overlong comment lines.
        max_line_length: Line length threshold for wrapping.

    Returns:
        A RefactorResult with original, refactored code, and change list.
    """
    current = source
    all_changes: list[str] = []

    if normalize_imports:
        current, changes = _normalize_imports(current)
        all_changes.extend(changes)

    if remove_unused:
        current, changes = _remove_unused_variables(current)
        all_changes.extend(changes)

    if add_docstrings:
        current, changes = _add_missing_docstrings(current)
        all_changes.extend(changes)

    if wrap_long_lines:
        current, changes = _wrap_long_lines(current, max_length=max_line_length)
        all_changes.extend(changes)

    return RefactorResult(
        path="<string>",
        original=source,
        refactored=current,
        changes=all_changes,
    )


def refactor_file(
    path: str,
    *,
    normalize_imports: bool = True,
    remove_unused: bool = True,
    add_docstrings: bool = False,
    wrap_long_lines: bool = False,
    max_line_length: int = 120,
    dry_run: bool = False,
) -> RefactorResult:
    """
    Refactor a Python source file.

    Args:
        path: Path to the .py file.
        normalize_imports: Sort and deduplicate imports.
        remove_unused: Remove obviously unused module-level variables.
        add_docstrings: Add placeholder docstrings to undocumented public items.
        wrap_long_lines: Wrap overlong comment lines.
        max_line_length: Line length threshold for wrapping.
        dry_run: If True, do not write back to disk.

    Returns:
        A RefactorResult.
    """
    source = Path(path).read_text(encoding="utf-8")
    result = refactor_source(
        source,
        normalize_imports=normalize_imports,
        remove_unused=remove_unused,
        add_docstrings=add_docstrings,
        wrap_long_lines=wrap_long_lines,
        max_line_length=max_line_length,
    )
    result.path = path

    if result.changed and not dry_run:
        Path(path).write_text(result.refactored, encoding="utf-8")

    return result
