"""Tests for src/teach.py — Module Tutorial Generator."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from src.teach import (
    FunctionDoc,
    ClassDoc,
    ModuleTutorial,
    teach_module,
    save_tutorial,
    list_teachable_modules,
    _parse_module,
    _extract_signature,
    _get_body_summary,
    _find_entry_function,
    _generate_how_it_works,
    _generate_examples,
    _extract_design_notes,
)


# ---------------------------------------------------------------------------
# Sample Python sources
# ---------------------------------------------------------------------------

SIMPLE_MODULE = '''\
"""A simple analysis module.

Analyses source files and produces a structured report.

Output formats:
- Markdown
- JSON
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path


MAX_SCORE = 100.0
DEFAULT_THRESHOLD = 5


@dataclass
class AnalysisResult:
    """Result of the analysis."""

    name: str
    score: float = 0.0
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {"name": self.name, "score": self.score, "issues": self.issues}

    def to_markdown(self) -> str:
        """Render as markdown."""
        return f"# {self.name}\\n\\nScore: {self.score}"


def analyze(repo_path: Path, threshold: int = DEFAULT_THRESHOLD) -> AnalysisResult:
    """Analyse the repository.

    Args:
        repo_path: Path to the repository.
        threshold: Complexity threshold.

    Returns:
        An AnalysisResult instance.
    """
    return AnalysisResult(name=str(repo_path))


def save_result(result: AnalysisResult, output_path: Path) -> None:
    """Save the result to a file.

    Args:
        result: The result to save.
        output_path: Where to write.
    """
    output_path.write_text(result.to_markdown())


def _private_helper(x: int) -> int:
    """This is private and should not appear in docs."""
    return x * 2
'''

MODULE_NO_DOCSTRING = '''\
import os
import sys

def run():
    return 42
'''

MODULE_WITH_SUBPROCESS = '''\
"""Module using subprocess."""

import subprocess
import ast
from pathlib import Path

def check(repo_path: Path) -> str:
    """Check something."""
    result = subprocess.run(["git", "log"], capture_output=True)
    return result.stdout.decode()
'''


@pytest.fixture()
def src_dir(tmp_path: Path) -> Path:
    d = tmp_path / "src"
    d.mkdir()
    (d / "__init__.py").write_text("")
    (d / "simple.py").write_text(SIMPLE_MODULE)
    (d / "nodoc.py").write_text(MODULE_NO_DOCSTRING)
    (d / "git_module.py").write_text(MODULE_WITH_SUBPROCESS)
    return d


@pytest.fixture()
def repo(tmp_path: Path, src_dir: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# _parse_module
# ---------------------------------------------------------------------------


def test_parse_module_name(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    assert tutorial.module_name == "simple"


def test_parse_module_docstring(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    assert "analysis module" in tutorial.module_docstring.lower()


def test_parse_module_no_docstring(src_dir: Path):
    tutorial = _parse_module(src_dir / "nodoc.py")
    assert tutorial.module_docstring == ""


def test_parse_module_class_count(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    assert len(tutorial.classes) == 1
    assert tutorial.classes[0].name == "AnalysisResult"


def test_parse_module_function_count(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    # Should include analyze, save_result (not _private_helper)
    pub_fn_names = [f.name for f in tutorial.functions if not f.is_method]
    assert "analyze" in pub_fn_names
    assert "save_result" in pub_fn_names
    assert "_private_helper" not in pub_fn_names


def test_parse_module_imports(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    assert "ast" in tutorial.imports
    assert "json" in tutorial.imports


def test_parse_module_constants(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    assert "MAX_SCORE" in tutorial.constants
    assert "DEFAULT_THRESHOLD" in tutorial.constants


def test_parse_module_line_count(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    assert tutorial.total_lines > 0


def test_parse_module_bad_syntax(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(: pass")
    tutorial = _parse_module(bad)
    assert "Parse error" in tutorial.module_docstring or tutorial.module_docstring == ""


# ---------------------------------------------------------------------------
# _extract_signature
# ---------------------------------------------------------------------------


def test_extract_signature_simple():
    import ast
    tree = ast.parse("def foo(x: int, y: str = 'hello') -> bool: pass")
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    sig = _extract_signature(fn)
    assert "foo" in sig
    assert "x" in sig
    assert "y" in sig


def test_extract_signature_no_args():
    import ast
    tree = ast.parse("def no_args(): pass")
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    sig = _extract_signature(fn)
    assert "no_args()" in sig


def test_extract_signature_with_varargs():
    import ast
    tree = ast.parse("def func(*args, **kwargs): pass")
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    sig = _extract_signature(fn)
    assert "*args" in sig
    assert "**kwargs" in sig


def test_extract_signature_with_return():
    import ast
    tree = ast.parse("def get() -> str: return 'x'")
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    sig = _extract_signature(fn)
    assert "-> str" in sig


# ---------------------------------------------------------------------------
# ClassDoc
# ---------------------------------------------------------------------------


def test_class_doc_from_parse(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    cls = tutorial.classes[0]
    assert cls.name == "AnalysisResult"
    assert cls.is_dataclass is True
    assert "name" in cls.fields
    assert "score" in cls.fields
    assert "to_dict" in cls.methods
    assert "to_markdown" in cls.methods


def test_class_doc_types(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    cls = tutorial.classes[0]
    assert "str" in cls.field_types.get("name", "")


# ---------------------------------------------------------------------------
# FunctionDoc
# ---------------------------------------------------------------------------


def test_function_doc_has_docstring(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    analyze_fn = next(f for f in tutorial.functions if f.name == "analyze")
    assert "Analyse" in analyze_fn.docstring


def test_function_doc_args(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    analyze_fn = next(f for f in tutorial.functions if f.name == "analyze")
    assert "repo_path" in analyze_fn.args


def test_function_doc_returns(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    analyze_fn = next(f for f in tutorial.functions if f.name == "analyze")
    assert "AnalysisResult" in analyze_fn.returns


def test_function_doc_is_not_private(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    names = [f.name for f in tutorial.functions]
    assert "_private_helper" not in names


# ---------------------------------------------------------------------------
# _find_entry_function
# ---------------------------------------------------------------------------


def test_find_entry_function_prefers_analyze(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    entry = _find_entry_function(tutorial.functions)
    assert entry is not None
    assert entry.name == "analyze"


def test_find_entry_function_none():
    assert _find_entry_function([]) is None


def test_find_entry_function_fallback():
    fns = [FunctionDoc(name="helper", signature="helper()", docstring="")]
    entry = _find_entry_function(fns)
    assert entry is not None


# ---------------------------------------------------------------------------
# _extract_design_notes
# ---------------------------------------------------------------------------


def test_design_notes_zero_deps(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    notes = _extract_design_notes(tutorial)
    assert any("Zero external" in n or "stdlib" in n for n in notes)


def test_design_notes_dataclass(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    notes = _extract_design_notes(tutorial)
    assert any("dataclass" in n.lower() for n in notes)


def test_design_notes_ast(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    notes = _extract_design_notes(tutorial)
    assert any("ast" in n.lower() for n in notes)


def test_design_notes_subprocess(src_dir: Path):
    tutorial = _parse_module(src_dir / "git_module.py")
    notes = _extract_design_notes(tutorial)
    assert any("subprocess" in n.lower() or "git" in n.lower() for n in notes)


# ---------------------------------------------------------------------------
# ModuleTutorial.to_markdown
# ---------------------------------------------------------------------------


def test_to_markdown_has_title(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    md = tutorial.to_markdown()
    assert "# Tutorial" in md
    assert "simple" in md


def test_to_markdown_has_data_structures_section(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    md = tutorial.to_markdown()
    assert "## Data Structures" in md
    assert "AnalysisResult" in md


def test_to_markdown_has_public_api_section(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    md = tutorial.to_markdown()
    assert "## Public API" in md
    assert "analyze" in md


def test_to_markdown_has_how_it_works(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    md = tutorial.to_markdown()
    assert "## How It Works" in md


def test_to_markdown_has_usage_examples(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    md = tutorial.to_markdown()
    assert "## Usage Examples" in md
    assert "```python" in md


def test_to_markdown_has_design_notes(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    md = tutorial.to_markdown()
    assert "## Design Notes" in md


def test_to_markdown_no_private_functions(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    md = tutorial.to_markdown()
    assert "_private_helper" not in md


def test_to_json_valid(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    data = json.loads(tutorial.to_json())
    assert "module_name" in data
    assert "classes" in data
    assert "functions" in data


def test_to_json_class_fields(src_dir: Path):
    tutorial = _parse_module(src_dir / "simple.py")
    data = json.loads(tutorial.to_json())
    classes = data["classes"]
    assert len(classes) == 1
    assert classes[0]["name"] == "AnalysisResult"
    assert "name" in classes[0]["fields"]


# ---------------------------------------------------------------------------
# teach_module
# ---------------------------------------------------------------------------


def test_teach_module_returns_tutorial(repo: Path):
    tutorial = teach_module("simple", repo)
    assert isinstance(tutorial, ModuleTutorial)
    assert tutorial.module_name == "simple"


def test_teach_module_not_found(repo: Path):
    with pytest.raises(FileNotFoundError) as exc_info:
        teach_module("nonexistent_xyz", repo)
    assert "not found" in str(exc_info.value).lower()


def test_teach_module_error_message_lists_modules(repo: Path):
    with pytest.raises(FileNotFoundError) as exc_info:
        teach_module("nonexistent_xyz", repo)
    assert "simple" in str(exc_info.value)


def test_teach_module_no_src_dir(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        teach_module("anything", tmp_path)


# ---------------------------------------------------------------------------
# list_teachable_modules
# ---------------------------------------------------------------------------


def test_list_teachable_modules(repo: Path):
    modules = list_teachable_modules(repo)
    assert "simple" in modules
    assert "nodoc" in modules
    assert "git_module" in modules


def test_list_teachable_modules_excludes_init(repo: Path):
    modules = list_teachable_modules(repo)
    assert "__init__" not in modules


def test_list_teachable_modules_sorted(repo: Path):
    modules = list_teachable_modules(repo)
    assert modules == sorted(modules)


def test_list_teachable_modules_no_src(tmp_path: Path):
    modules = list_teachable_modules(tmp_path)
    assert modules == []


# ---------------------------------------------------------------------------
# save_tutorial
# ---------------------------------------------------------------------------


def test_save_tutorial_writes_md(tmp_path: Path, repo: Path):
    tutorial = teach_module("simple", repo)
    out = tmp_path / "docs" / "tutorials" / "simple.md"
    save_tutorial(tutorial, out)
    assert out.exists()
    assert "Tutorial" in out.read_text()


def test_save_tutorial_writes_json(tmp_path: Path, repo: Path):
    tutorial = teach_module("simple", repo)
    out = tmp_path / "docs" / "tutorials" / "simple.md"
    save_tutorial(tutorial, out)
    json_out = out.with_suffix(".json")
    assert json_out.exists()
    json.loads(json_out.read_text())


def test_save_tutorial_creates_dirs(tmp_path: Path, repo: Path):
    tutorial = teach_module("simple", repo)
    out = tmp_path / "a" / "b" / "c" / "simple.md"
    save_tutorial(tutorial, out)
    assert out.exists()
