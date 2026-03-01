"""awake teach — generate a human-readable tutorial for any module.

Given a module name (e.g. ``health``, ``brain``, ``security``), this module
reads ``src/<name>.py`` and produces a structured walkthrough that explains:

1. **What the module does** — the high-level problem it solves
2. **Key data structures** — dataclasses/classes with their fields explained
3. **How it works** — step-by-step narrative of the main algorithm/entry point
4. **Public API** — every public function with its signature and purpose
5. **Usage examples** — practical code snippets showing how to call the module
6. **Internal design choices** — what decisions are reflected in the code structure

The tutorial is generated entirely from static analysis (AST + source parsing) —
no runtime execution, no external AI calls.  It reads the same code you already
have and explains it in plain language.

Output: Markdown document (``docs/tutorials/<name>.md``)

CLI:
    awake teach <module> [--write] [--json]
"""

from __future__ import annotations

import ast
import json
import textwrap
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FunctionDoc:
    """Documentation for a single public function."""

    name: str
    signature: str
    docstring: str
    args: list[str] = field(default_factory=list)
    returns: str = ""
    line_number: int = 0
    is_method: bool = False
    class_name: str = ""
    body_summary: str = ""       # 1-line summary of what the body does

    def to_dict(self) -> dict:
        """Return a dictionary representation of the function documentation"""
        return asdict(self)


@dataclass
class ClassDoc:
    """Documentation for a single class (usually a dataclass)."""

    name: str
    docstring: str
    fields: list[str] = field(default_factory=list)      # field names
    field_types: dict[str, str] = field(default_factory=dict)  # name -> type annotation
    methods: list[str] = field(default_factory=list)
    is_dataclass: bool = False
    line_number: int = 0

    def to_dict(self) -> dict:
        """Return a dictionary representation of the class documentation"""
        return asdict(self)


@dataclass
class ModuleTutorial:
    """Full tutorial document for a single module."""

    module_name: str
    module_path: str
    module_docstring: str
    total_lines: int = 0
    classes: list[ClassDoc] = field(default_factory=list)
    functions: list[FunctionDoc] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the module tutorial"""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize the module tutorial to a JSON string"""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_markdown(self) -> str:
        """Render the full tutorial as a Markdown document."""
        lines: list[str] = [
            f"# Tutorial: `{self.module_name}`",
            "",
            f"*Source: `{self.module_path}` — {self.total_lines} lines*",
            "",
        ]

        # What does it do?
        if self.module_docstring:
            lines += [
                "## What This Module Does",
                "",
            ]
            # Show first paragraph of module docstring
            paragraphs = self.module_docstring.strip().split("\n\n")
            first_para = textwrap.dedent(paragraphs[0]).strip()
            lines.append(first_para)
            lines.append("")

        # Imports summary
        if self.imports:
            stdlib_imports = [i for i in self.imports if not i.startswith("src.")]
            src_imports = [i for i in self.imports if i.startswith("src.")]
            lines += ["## Dependencies", ""]
            if stdlib_imports:
                lines.append(
                    f"**Standard library:** `{'`, `'.join(stdlib_imports)}`  "
                )
            if src_imports:
                lines.append(
                    f"**Internal modules:** `{'`, `'.join(src_imports)}`  "
                )
            if not stdlib_imports and not src_imports:
                lines.append("No imports — fully self-contained.")
            lines.append("")

        # Data structures
        if self.classes:
            lines += ["## Data Structures", ""]
            for cls in self.classes:
                badge = " *(dataclass)*" if cls.is_dataclass else ""
                lines += [f"### `{cls.name}`{badge}", ""]
                if cls.docstring:
                    lines.append(f"> {cls.docstring.strip().splitlines()[0]}")
                    lines.append("")
                if cls.fields:
                    lines.append("**Fields:**")
                    lines.append("")
                    for fname in cls.fields:
                        ftype = cls.field_types.get(fname, "")
                        type_str = f" (`{ftype}`)" if ftype else ""
                        lines.append(f"- `{fname}`{type_str}")
                    lines.append("")
                if cls.methods:
                    public_methods = [m for m in cls.methods if not m.startswith("_") or m in ("__init__", "__post_init__")]
                    if public_methods:
                        lines.append(f"**Methods:** `{'`, `'.join(public_methods)}`")
                        lines.append("")

        # Public API
        if self.functions:
            lines += ["## Public API", ""]
            for fn in self.functions:
                if fn.is_method:
                    continue  # covered under data structures
                prefix = ""
                lines += [f"### `{fn.name}()`", ""]
                if fn.docstring:
                    first_line = fn.docstring.strip().splitlines()[0]
                    lines.append(f"*{first_line}*")
                    lines.append("")
                lines.append(f"```python")
                lines.append(f"def {fn.signature}")
                lines.append("```")
                lines.append("")
                if fn.args:
                    lines.append("**Parameters:**")
                    lines.append("")
                    for arg in fn.args:
                        if arg not in ("self", "cls"):
                            lines.append(f"- `{arg}`")
                    lines.append("")
                if fn.returns:
                    lines.append(f"**Returns:** `{fn.returns}`")
                    lines.append("")

        # How it works (algorithm narrative)
        entry_fn = _find_entry_function(self.functions)
        if entry_fn or self.functions:
            lines += ["## How It Works", ""]
            lines += _generate_how_it_works(self)
            lines.append("")

        # Usage examples
        lines += [
            "## Usage Examples",
            "",
            "```python",
            f"from src.{self.module_name} import *",
            "",
        ]
        lines += _generate_examples(self)
        lines += [
            "```",
            "",
        ]

        # Design notes
        design_notes = _extract_design_notes(self)
        if design_notes:
            lines += [
                "## Design Notes",
                "",
            ]
            for note in design_notes:
                lines.append(f"- {note}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AST extraction
# ---------------------------------------------------------------------------


def _extract_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract a readable function signature from an AST node."""
    args = []
    func_args = node.args

    # Regular args
    n_no_default = len(func_args.args) - len(func_args.defaults)
    for i, arg in enumerate(func_args.args):
        arg_str = arg.arg
        if arg.annotation:
            try:
                arg_str += f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        if i >= n_no_default:
            default_i = i - n_no_default
            try:
                default_str = ast.unparse(func_args.defaults[default_i])
                arg_str += f" = {default_str}"
            except Exception:
                pass
        args.append(arg_str)

    # *args
    if func_args.vararg:
        args.append(f"*{func_args.vararg.arg}")

    # **kwargs
    if func_args.kwarg:
        args.append(f"**{func_args.kwarg.arg}")

    # Return annotation
    ret = ""
    if node.returns:
        try:
            ret = f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass

    name = node.name
    return f"{name}({', '.join(args)}){ret}"


def _get_body_summary(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Infer a one-line summary of what a function body does."""
    keywords_seen = []
    for child in ast.walk(node):
        if isinstance(child, ast.Return):
            keywords_seen.append("returns a value")
        if isinstance(child, ast.Yield):
            keywords_seen.append("yields values")
        if isinstance(child, (ast.For, ast.While)):
            keywords_seen.append("iterates")
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Attribute) and child.func.attr in (
                "write_text", "write", "save", "dump"
            ):
                keywords_seen.append("writes to disk")
            if isinstance(child.func, ast.Attribute) and child.func.attr in (
                "read_text", "read", "load"
            ):
                keywords_seen.append("reads from disk")
        if isinstance(child, (ast.Import, ast.ImportFrom)):
            pass

    seen = list(dict.fromkeys(keywords_seen))  # deduplicate preserving order
    if seen:
        return ", ".join(seen[:3])
    return ""


def _parse_module(src_path: Path) -> ModuleTutorial:
    """Parse a Python source file into a ModuleTutorial."""
    source = src_path.read_text(encoding="utf-8")
    lines_count = len(source.splitlines())

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ModuleTutorial(
            module_name=src_path.stem,
            module_path=str(src_path),
            module_docstring=f"(Parse error: {e})",
            total_lines=lines_count,
        )

    module_docstring = ast.get_docstring(tree) or ""

    # Collect imports
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    # Deduplicate, keep order
    seen_imports: set[str] = set()
    unique_imports: list[str] = []
    for imp in imports:
        if imp not in seen_imports:
            seen_imports.add(imp)
            unique_imports.append(imp)

    # Collect constants (module-level NAME = value)
    constants: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    constants.append(target.id)

    # Collect classes
    classes: list[ClassDoc] = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_dc = any(
            (isinstance(d, ast.Name) and d.id == "dataclass")
            or (isinstance(d, ast.Attribute) and d.attr == "dataclass")
            for d in node.decorator_list
        )
        fields: list[str] = []
        field_types: dict[str, str] = {}
        methods: list[str] = []

        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields.append(child.target.id)
                try:
                    field_types[child.target.id] = ast.unparse(child.annotation)
                except Exception:
                    pass
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(child.name)

        classes.append(
            ClassDoc(
                name=node.name,
                docstring=ast.get_docstring(node) or "",
                fields=fields,
                field_types=field_types,
                methods=methods,
                is_dataclass=is_dc,
                line_number=node.lineno,
            )
        )

    # Collect top-level functions and methods
    functions: list[FunctionDoc] = []

    def _process_func(
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str = "",
        is_method: bool = False,
    ) -> None:
        if node.name.startswith("__") and node.name not in ("__init__", "__post_init__"):
            return
        sig = _extract_signature(node)
        docstring = ast.get_docstring(node) or ""
        args = [a.arg for a in node.args.args]
        ret = ""
        if node.returns:
            try:
                ret = ast.unparse(node.returns)
            except Exception:
                pass
        body_summary = _get_body_summary(node)
        functions.append(
            FunctionDoc(
                name=node.name,
                signature=sig,
                docstring=docstring,
                args=args,
                returns=ret,
                line_number=node.lineno,
                is_method=is_method,
                class_name=class_name,
                body_summary=body_summary,
            )
        )

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                _process_func(node)
        elif isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _process_func(child, class_name=node.name, is_method=True)

    return ModuleTutorial(
        module_name=src_path.stem,
        module_path=str(src_path),
        module_docstring=module_docstring,
        total_lines=lines_count,
        classes=classes,
        functions=functions,
        imports=unique_imports,
        constants=constants,
    )


# ---------------------------------------------------------------------------
# Narrative generators
# ---------------------------------------------------------------------------


def _find_entry_function(functions: list[FunctionDoc]) -> Optional[FunctionDoc]:
    """Find the most likely 'main' entry function of a module."""
    priority_names = ["generate", "analyze", "build", "compute", "run", "assess", "audit", "check", "find"]
    for pname in priority_names:
        for fn in functions:
            if fn.name.startswith(pname) and not fn.is_method:
                return fn
    if functions:
        return next((f for f in functions if not f.is_method), functions[0])
    return None


def _generate_how_it_works(tutorial: ModuleTutorial) -> list[str]:
    """Generate a step-by-step walkthrough narrative."""
    lines: list[str] = []

    entry = _find_entry_function(tutorial.functions)
    top_funcs = [f for f in tutorial.functions if not f.is_method]

    if not top_funcs:
        lines.append("This module exposes its functionality through class methods.")
        return lines

    if entry:
        lines.append(
            f"The main entry point is **`{entry.name}()`**. "
            + (f"It {entry.body_summary}." if entry.body_summary else "")
        )
        lines.append("")

    if tutorial.classes:
        class_names = [c.name for c in tutorial.classes]
        lines.append(
            f"Internally, the module uses {len(tutorial.classes)} data structure(s): "
            f"`{'`, `'.join(class_names)}`. "
            f"These dataclasses carry the results through the analysis pipeline."
        )
        lines.append("")

    if len(top_funcs) > 1:
        helper_fns = [f for f in top_funcs if f != entry][:4]
        if helper_fns:
            fn_names = ", ".join(f"`{f.name}()`" for f in helper_fns)
            lines.append(
                f"Supporting functions include {fn_names}, each handling a distinct "
                f"aspect of the analysis to keep the code modular."
            )
            lines.append("")

    if tutorial.constants:
        lines.append(
            f"Constants like `{'`, `'.join(tutorial.constants[:4])}` control behaviour "
            f"and can be easily adjusted without touching the core logic."
        )
        lines.append("")

    return lines


def _generate_examples(tutorial: ModuleTutorial) -> list[str]:
    """Generate realistic usage example lines."""
    lines: list[str] = []
    entry = _find_entry_function(tutorial.functions)

    if entry:
        lines.append(f"from pathlib import Path")
        lines.append("")
        lines.append(f"repo = Path('.')  # or any path to a repo")
        lines.append("")
        # Build a sensible call
        args = [a for a in entry.args if a not in ("self", "cls")]
        if not args:
            call = f"result = {entry.name}()"
        elif len(args) == 1:
            call = f"result = {entry.name}(repo_path=repo)"
        else:
            # Use keyword arg style
            sample_args = []
            for arg in args[:3]:
                if "path" in arg.lower() or "repo" in arg.lower():
                    sample_args.append(f"{arg}=repo")
                elif arg in ("name", "module"):
                    sample_args.append(f'{arg}="{tutorial.module_name}"')
                else:
                    sample_args.append(f"{arg}=...")
            call = f"result = {entry.name}({', '.join(sample_args)})"
        lines.append(call)
        lines.append("")

    # Show save function if it exists
    save_fns = [f for f in tutorial.functions if f.name.startswith("save") and not f.is_method]
    if save_fns:
        lines.append(f"# Save to docs/")
        lines.append(f"{save_fns[0].name}(result, Path('docs/{tutorial.module_name}_report.md'))")
        lines.append("")

    # Show to_markdown / to_json usage if any class has them
    for cls in tutorial.classes:
        if "to_markdown" in cls.methods:
            lines.append(f"# Render as Markdown")
            lines.append(f"print(result.to_markdown())")
            break

    if not lines:
        lines.append(f"# See module docstring and public API above for usage details")

    return lines


def _extract_design_notes(tutorial: ModuleTutorial) -> list[str]:
    """Extract design choices from docstrings and structure."""
    notes: list[str] = []

    # Zero-dependency check
    external_deps = [
        imp for imp in tutorial.imports
        if imp not in (
            "ast", "re", "json", "pathlib", "dataclasses", "datetime",
            "subprocess", "collections", "itertools", "typing", "functools",
            "math", "hashlib", "textwrap", "sys", "os", "__future__", "abc",
            "io", "copy", "string", "contextlib", "warnings", "logging",
            "time", "struct", "base64", "random", "enum", "inspect",
        )
        and not imp.startswith("src.")
        and not imp.startswith("_")
    ]
    if not external_deps:
        notes.append(
            "Zero external dependencies — uses Python stdlib only, keeping installation friction low."
        )
    else:
        notes.append(
            f"External dependencies: `{'`, `'.join(external_deps)}`."
        )

    # Dataclasses usage
    dc_count = sum(1 for c in tutorial.classes if c.is_dataclass)
    if dc_count > 0:
        notes.append(
            f"Uses {dc_count} `@dataclass`(es) for structured data — "
            f"all results are serializable via `to_dict()` / `to_json()`."
        )

    # AST usage
    if "ast" in tutorial.imports:
        notes.append(
            "Performs static analysis via Python's `ast` module — "
            "no code is executed, making it safe to run on any codebase."
        )

    # Subprocess usage
    if "subprocess" in tutorial.imports:
        notes.append(
            "Shells out to `git` via `subprocess` — "
            "requires git to be installed but avoids heavy git library dependencies."
        )

    return notes


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def teach_module(module_name: str, repo_path: Path) -> ModuleTutorial:
    """Generate a tutorial for a module in src/.

    Args:
        module_name: The name of the module (without .py extension).
        repo_path: Path to the repository root.

    Returns:
        A ModuleTutorial ready for rendering.

    Raises:
        FileNotFoundError: If src/<module_name>.py does not exist.
    """
    src_path = repo_path / "src" / f"{module_name}.py"
    if not src_path.exists():
        raise FileNotFoundError(
            f"Module not found: {src_path}\n"
            f"Available modules: "
            + ", ".join(
                p.stem
                for p in sorted((repo_path / "src").glob("*.py"))
                if not p.stem.startswith("_")
            )
        )
    return _parse_module(src_path)


def save_tutorial(tutorial: ModuleTutorial, output_path: Path) -> None:
    """Save the tutorial as Markdown + JSON sidecar.

    Args:
        tutorial: The ModuleTutorial to save.
        output_path: Path for the .md file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tutorial.to_markdown(), encoding="utf-8")
    output_path.with_suffix(".json").write_text(tutorial.to_json(), encoding="utf-8")


def list_teachable_modules(repo_path: Path) -> list[str]:
    """Return a sorted list of module names that can be taught.

    Args:
        repo_path: Path to the repository root.

    Returns:
        List of module names (without .py extension).
    """
    src_dir = repo_path / "src"
    if not src_dir.exists():
        return []
    return sorted(
        p.stem
        for p in src_dir.glob("*.py")
        if not p.stem.startswith("_")
    )
