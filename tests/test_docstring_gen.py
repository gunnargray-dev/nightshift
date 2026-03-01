"""Tests for the docstring generator module.

Covers:
- AST scanning for missing docstrings
- Name-to-description heuristics
- Docstring generation (functions, methods, classes)
- Annotation parsing
- Report generation and serialisation
- Markdown rendering
- apply_docstrings (dry-run mode)
- Edge cases (syntax errors, empty files, dunder methods)
"""

from __future__ import annotations

import json
import textwrap
import tempfile
from pathlib import Path

import pytest

from src.docstring_gen import (
    MissingDocstring,
    DocstringReport,
    scan_missing_docstrings,
    generate_docstring,
    apply_docstrings,
    save_docstring_report,
    render_markdown,
    _name_to_description,
    _class_description,
    _annotation_to_str,
    _has_docstring,
    _get_params,
    _decorator_names,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal repo layout with src/ containing sample .py files."""
    src = tmp_path / "src"
    src.mkdir()
    return tmp_path


def _write_src(tmp_repo, filename, content):
    """Helper to write a Python file under src/."""
    fpath = tmp_repo / "src" / filename
    fpath.write_text(textwrap.dedent(content), encoding="utf-8")
    return fpath


# ---------------------------------------------------------------------------
# _name_to_description tests
# ---------------------------------------------------------------------------


class TestNameToDescription:
    def test_get_verb(self):
        assert _name_to_description("get_health_score") == "Return the health score."

    def test_set_verb(self):
        assert _name_to_description("set_threshold") == "Set the threshold."

    def test_is_verb(self):
        assert _name_to_description("is_valid") == "Check whether valid."

    def test_has_verb(self):
        assert _name_to_description("has_docstring") == "Check whether item has docstring."

    def test_parse_verb(self):
        assert _name_to_description("parse_config") == "Parse the config."

    def test_compute_verb(self):
        assert _name_to_description("compute_score") == "Compute the score."

    def test_leading_underscores(self):
        result = _name_to_description("_parse_config_file")
        assert result == "Parse the config file."

    def test_double_underscores(self):
        result = _name_to_description("__init__")
        assert result == "Initialise the instance."

    def test_repr_dunder(self):
        assert _name_to_description("__repr__") == "Return string representation."

    def test_str_dunder(self):
        assert _name_to_description("__str__") == "Return human-readable string."

    def test_len_dunder(self):
        assert _name_to_description("__len__") == "Return the length."

    def test_eq_dunder(self):
        assert _name_to_description("__eq__") == "Check equality."

    def test_iter_dunder(self):
        assert _name_to_description("__iter__") == "Return an iterator."

    def test_enter_dunder(self):
        assert _name_to_description("__enter__") == "Enter the context manager."

    def test_exit_dunder(self):
        assert _name_to_description("__exit__") == "Exit the context manager."

    def test_getitem_dunder(self):
        assert _name_to_description("__getitem__") == "Get item by key."

    def test_contains_dunder(self):
        assert _name_to_description("__contains__") == "Check membership."

    def test_unknown_verb_fallback(self):
        result = _name_to_description("frobnicate_data")
        assert result == "Frobnicate data."

    def test_single_word(self):
        result = _name_to_description("run")
        assert result == "Run."

    def test_empty_after_strip(self):
        result = _name_to_description("___")
        assert "description" in result.lower() or "no" in result.lower()

    def test_scan_verb(self):
        assert _name_to_description("scan_files") == "Scan files."

    def test_analyze_verb(self):
        assert _name_to_description("analyze_repo") == "Analyse the repo."

    def test_to_verb(self):
        assert _name_to_description("to_dict") == "Convert to dict."

    def test_score_verb(self):
        assert _name_to_description("score_file") == "Score the file."

    def test_validate_verb(self):
        assert _name_to_description("validate_input") == "Validate the input."

    def test_generate_verb(self):
        assert _name_to_description("generate_report") == "Generate the report."

    def test_create_verb(self):
        assert _name_to_description("create_branch") == "Create the branch."

    def test_delete_verb(self):
        assert _name_to_description("delete_file") == "Delete the file."

    def test_filter_verb(self):
        assert _name_to_description("filter_results") == "Filter the results."

    def test_sort_verb(self):
        assert _name_to_description("sort_items") == "Sort the items."

    def test_merge_verb(self):
        assert _name_to_description("merge_branches") == "Merge the branches."

    def test_load_verb(self):
        assert _name_to_description("load_config") == "Load the config."

    def test_save_verb(self):
        assert _name_to_description("save_report") == "Save the report."

    def test_multi_word_rest(self):
        result = _name_to_description("get_health_score_trend")
        assert result == "Return the health score trend."


# ---------------------------------------------------------------------------
# _class_description tests
# ---------------------------------------------------------------------------


class TestClassDescription:
    def test_simple_class(self):
        result = _class_description("HealthReport", [])
        assert result == "A health report."

    def test_class_with_bases(self):
        result = _class_description("SecurityFinding", ["BaseModel"])
        assert "BaseModel" in result

    def test_camel_case_split(self):
        result = _class_description("AutoMergeDecision", [])
        assert "auto merge decision" in result.lower()

    def test_single_word(self):
        result = _class_description("Config", [])
        assert "config" in result.lower()


# ---------------------------------------------------------------------------
# AST helper tests
# ---------------------------------------------------------------------------


class TestASTHelpers:
    def test_has_docstring_true(self):
        code = 'def foo():\n    """A doc."""\n    pass\n'
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        assert _has_docstring(func) is True

    def test_has_docstring_false(self):
        code = "def foo():\n    pass\n"
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        assert _has_docstring(func) is False

    def test_has_docstring_class_true(self):
        code = 'class Foo:\n    """Doc."""\n    pass\n'
        tree = __import__("ast").parse(code)
        cls = tree.body[0]
        assert _has_docstring(cls) is True

    def test_has_docstring_class_false(self):
        code = "class Foo:\n    pass\n"
        tree = __import__("ast").parse(code)
        cls = tree.body[0]
        assert _has_docstring(cls) is False

    def test_get_params_simple(self):
        code = "def foo(a, b, c):\n    pass\n"
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        assert _get_params(func) == ["a", "b", "c"]

    def test_get_params_self_excluded(self):
        code = "def foo(self, a, b):\n    pass\n"
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        assert _get_params(func) == ["a", "b"]

    def test_get_params_cls_excluded(self):
        code = "def foo(cls, a):\n    pass\n"
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        assert _get_params(func) == ["a"]

    def test_get_params_kwargs(self):
        code = "def foo(a, *args, b=1, **kwargs):\n    pass\n"
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        params = _get_params(func)
        assert "a" in params
        assert "b" in params
        assert "*args" in params
        assert "**kwargs" in params

    def test_annotation_to_str_name(self):
        code = "x: int"
        tree = __import__("ast").parse(code)
        ann = tree.body[0].annotation
        assert _annotation_to_str(ann) == "int"

    def test_annotation_to_str_none(self):
        assert _annotation_to_str(None) is None

    def test_annotation_to_str_subscript(self):
        code = "x: list[int]"
        tree = __import__("ast").parse(code)
        ann = tree.body[0].annotation
        result = _annotation_to_str(ann)
        assert result == "list[int]"

    def test_decorator_names(self):
        code = "@staticmethod\ndef foo():\n    pass\n"
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        names = _decorator_names(func.decorator_list)
        assert names == ["staticmethod"]

    def test_decorator_names_call(self):
        code = "@pytest.fixture\ndef foo():\n    pass\n"
        tree = __import__("ast").parse(code)
        func = tree.body[0]
        names = _decorator_names(func.decorator_list)
        assert len(names) == 1
        assert "pytest" in names[0] or "fixture" in names[0]


# ---------------------------------------------------------------------------
# generate_docstring tests
# ---------------------------------------------------------------------------


class TestGenerateDocstring:
    def test_simple_function(self):
        item = MissingDocstring(
            kind="function",
            name="get_score",
            qualified_name="health.py::get_score",
            file="src/health.py",
            line=10,
        )
        ds = generate_docstring(item)
        assert "Return" in ds
        assert "score" in ds

    def test_function_with_params(self):
        item = MissingDocstring(
            kind="function",
            name="compute_health",
            qualified_name="health.py::compute_health",
            file="src/health.py",
            line=20,
            params=["file_path", "threshold"],
        )
        ds = generate_docstring(item)
        assert "Parameters" in ds
        assert "file_path" in ds
        assert "threshold" in ds

    def test_function_with_return(self):
        item = MissingDocstring(
            kind="function",
            name="get_items",
            qualified_name="mod.py::get_items",
            file="src/mod.py",
            line=5,
            return_annotation="list[str]",
        )
        ds = generate_docstring(item)
        assert "Returns" in ds
        assert "list[str]" in ds

    def test_function_return_none_omitted(self):
        item = MissingDocstring(
            kind="function",
            name="set_value",
            qualified_name="mod.py::set_value",
            file="src/mod.py",
            line=5,
            return_annotation="None",
        )
        ds = generate_docstring(item)
        assert "Returns" not in ds

    def test_class_docstring(self):
        item = MissingDocstring(
            kind="class",
            name="HealthReport",
            qualified_name="health.py::HealthReport",
            file="src/health.py",
            line=15,
            bases=["BaseModel"],
        )
        ds = generate_docstring(item)
        assert "health report" in ds.lower()
        assert "BaseModel" in ds

    def test_class_no_bases(self):
        item = MissingDocstring(
            kind="class",
            name="Config",
            qualified_name="config.py::Config",
            file="src/config.py",
            line=10,
        )
        ds = generate_docstring(item)
        assert "config" in ds.lower()

    def test_method_docstring(self):
        item = MissingDocstring(
            kind="method",
            name="to_dict",
            qualified_name="health.py::to_dict",
            file="src/health.py",
            line=30,
        )
        ds = generate_docstring(item)
        assert "Convert" in ds or "dict" in ds.lower()

    def test_dunder_init(self):
        item = MissingDocstring(
            kind="method",
            name="__init__",
            qualified_name="mod.py::__init__",
            file="src/mod.py",
            line=5,
        )
        ds = generate_docstring(item)
        assert "Initialise" in ds

    def test_dunder_repr(self):
        item = MissingDocstring(
            kind="method",
            name="__repr__",
            qualified_name="mod.py::__repr__",
            file="src/mod.py",
            line=5,
        )
        ds = generate_docstring(item)
        assert "representation" in ds.lower()


# ---------------------------------------------------------------------------
# scan_missing_docstrings tests
# ---------------------------------------------------------------------------


class TestScanMissingDocstrings:
    def test_fully_documented(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            '''\
            """Module doc."""
            def foo():
                """Foo doc."""
                pass

            class Bar:
                """Bar doc."""
                def method(self):
                    """Method doc."""
                    pass
            ''',
        )
        report = scan_missing_docstrings(tmp_repo)
        assert report.undocumented == 0
        assert report.coverage_pct == 100.0

    def test_all_undocumented(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            def foo():
                pass

            class Bar:
                def method(self):
                    pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        assert report.undocumented >= 2  # foo + Bar + method
        assert report.coverage_pct < 100.0
        assert len(report.items) >= 2

    def test_mixed_coverage(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            '''\
            def documented():
                """Has a doc."""
                pass

            def undocumented():
                pass
            ''',
        )
        report = scan_missing_docstrings(tmp_repo)
        assert report.documented == 1
        assert report.undocumented == 1
        assert 40.0 < report.coverage_pct < 60.0

    def test_syntax_error_handled(self, tmp_repo):
        _write_src(tmp_repo, "bad.py", "def broken(\n")
        report = scan_missing_docstrings(tmp_repo)
        assert len(report.errors) == 1
        assert "bad.py" in report.errors[0]

    def test_empty_file(self, tmp_repo):
        _write_src(tmp_repo, "empty.py", "")
        report = scan_missing_docstrings(tmp_repo)
        assert report.total_items == 0
        assert report.files_scanned == 1

    def test_no_src_directory(self, tmp_path):
        report = scan_missing_docstrings(tmp_path)
        assert len(report.errors) == 1
        assert "src/ not found" in report.errors[0]

    def test_nested_functions(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            def outer():
                def inner():
                    pass
                pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        assert report.undocumented >= 2

    def test_async_function(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            async def fetch_data():
                pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        assert report.undocumented == 1
        assert report.items[0].name == "fetch_data"

    def test_generated_docstrings_populated(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            def get_score():
                pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        assert report.items[0].generated_docstring is not None
        assert len(report.items[0].generated_docstring) > 0

    def test_decorators_captured(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            import functools

            class Foo:
                @staticmethod
                def bar():
                    pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        bar_items = [i for i in report.items if i.name == "bar"]
        assert len(bar_items) == 1
        assert "staticmethod" in bar_items[0].decorators

    def test_method_detection(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            class Foo:
                def bar(self):
                    pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        bar_items = [i for i in report.items if i.name == "bar"]
        assert len(bar_items) == 1
        assert bar_items[0].kind == "method"

    def test_params_captured(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            def foo(a, b, c=3):
                pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        foo = [i for i in report.items if i.name == "foo"][0]
        assert "a" in foo.params
        assert "b" in foo.params
        assert "c" in foo.params

    def test_return_annotation_captured(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            def foo() -> int:
                pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        foo = [i for i in report.items if i.name == "foo"][0]
        assert foo.return_annotation == "int"

    def test_class_bases_captured(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
            class MyError(ValueError):
                pass
            """,
        )
        report = scan_missing_docstrings(tmp_repo)
        cls = [i for i in report.items if i.name == "MyError"][0]
        assert "ValueError" in cls.bases

    def test_multiple_files(self, tmp_repo):
        _write_src(tmp_repo, "a.py", "def foo():\n    pass\n")
        _write_src(tmp_repo, "b.py", "def bar():\n    pass\n")
        report = scan_missing_docstrings(tmp_repo)
        assert report.files_scanned >= 2
        assert report.undocumented >= 2


# ---------------------------------------------------------------------------
# apply_docstrings tests
# ---------------------------------------------------------------------------


class TestApplyDocstrings:
    def test_dry_run_no_changes(self, tmp_repo):
        _write_src(tmp_repo, "mod.py", "def foo():\n    pass\n")
        report = scan_missing_docstrings(tmp_repo)
        modified = apply_docstrings(report, tmp_repo, dry_run=True)
        assert len(modified) >= 1
        # File should be unchanged
        content = (tmp_repo / "src" / "mod.py").read_text()
        assert '"""' not in content or "Module" in content  # no new docstrings added

    def test_apply_inserts_docstrings(self, tmp_repo):
        _write_src(tmp_repo, "mod.py", "def foo():\n    pass\n")
        report = scan_missing_docstrings(tmp_repo)
        modified = apply_docstrings(report, tmp_repo, dry_run=False)
        assert len(modified) >= 1
        content = (tmp_repo / "src" / "mod.py").read_text()
        assert '"""' in content

    def test_apply_multiple_items(self, tmp_repo):
        _write_src(
            tmp_repo,
            "mod.py",
            """\
def get_a():
    pass

def set_b():
    pass
""",
        )
        report = scan_missing_docstrings(tmp_repo)
        apply_docstrings(report, tmp_repo, dry_run=False)
        content = (tmp_repo / "src" / "mod.py").read_text()
        assert content.count('"""') >= 4  # 2 docstrings = 4 triple-quotes


# ---------------------------------------------------------------------------
# Report serialisation tests
# ---------------------------------------------------------------------------


class TestReportSerialisation:
    def test_to_dict(self):
        report = DocstringReport(
            total_items=10,
            documented=7,
            undocumented=3,
            coverage_pct=70.0,
            files_scanned=5,
        )
        d = report.to_dict()
        assert d["total_items"] == 10
        assert d["coverage_pct"] == 70.0
        assert d["files_scanned"] == 5

    def test_item_to_dict(self):
        item = MissingDocstring(
            kind="function",
            name="foo",
            qualified_name="mod.py::foo",
            file="src/mod.py",
            line=5,
            params=["a", "b"],
            return_annotation="int",
            decorators=["staticmethod"],
        )
        d = item.to_dict()
        assert d["kind"] == "function"
        assert d["params"] == ["a", "b"]
        assert d["return_annotation"] == "int"

    def test_save_report(self, tmp_path):
        report = DocstringReport(
            total_items=5, documented=3, undocumented=2, coverage_pct=60.0
        )
        out = tmp_path / "report.json"
        save_docstring_report(report, out)
        data = json.loads(out.read_text())
        assert data["total_items"] == 5
        assert data["coverage_pct"] == 60.0


# ---------------------------------------------------------------------------
# Markdown rendering tests
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_empty_report(self):
        report = DocstringReport()
        md = render_markdown(report)
        assert "Docstring Coverage Report" in md
        assert "0" in md

    def test_with_items(self):
        item = MissingDocstring(
            kind="function",
            name="foo",
            qualified_name="mod.py::foo",
            file="src/mod.py",
            line=10,
            generated_docstring="Foo the bar.",
        )
        report = DocstringReport(
            total_items=2,
            documented=1,
            undocumented=1,
            coverage_pct=50.0,
            items=[item],
        )
        md = render_markdown(report)
        assert "Undocumented Items" in md
        assert "foo" in md
        assert "50.0%" in md

    def test_with_errors(self):
        report = DocstringReport(errors=["bad.py: SyntaxError"])
        md = render_markdown(report)
        assert "Errors" in md
        assert "bad.py" in md


# ---------------------------------------------------------------------------
# MissingDocstring dataclass tests
# ---------------------------------------------------------------------------


class TestMissingDocstring:
    def test_defaults(self):
        item = MissingDocstring(
            kind="function",
            name="foo",
            qualified_name="mod.py::foo",
            file="src/mod.py",
            line=1,
        )
        assert item.params == []
        assert item.return_annotation is None
        assert item.decorators == []
        assert item.bases == []
        assert item.generated_docstring is None

    def test_to_dict_complete(self):
        item = MissingDocstring(
            kind="method",
            name="bar",
            qualified_name="mod.py::bar",
            file="src/mod.py",
            line=5,
            params=["x"],
            return_annotation="str",
            decorators=["property"],
            bases=[],
            generated_docstring="Bar the baz.",
        )
        d = item.to_dict()
        assert d["kind"] == "method"
        assert d["generated_docstring"] == "Bar the baz."


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------


class TestCLI:
    def test_main_no_args(self, tmp_repo):
        _write_src(tmp_repo, "mod.py", "def foo():\n    pass\n")
        from src.docstring_gen import main

        ret = main(["--repo", str(tmp_repo)])
        assert ret == 0

    def test_main_json(self, tmp_repo, capsys):
        _write_src(tmp_repo, "mod.py", "def foo():\n    pass\n")
        from src.docstring_gen import main

        ret = main(["--repo", str(tmp_repo), "--json"])
        assert ret == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_items" in data

    def test_main_dry_run(self, tmp_repo):
        _write_src(tmp_repo, "mod.py", "def foo():\n    pass\n")
        from src.docstring_gen import main

        ret = main(["--repo", str(tmp_repo), "--dry-run"])
        assert ret == 0

    def test_main_write(self, tmp_repo):
        _write_src(tmp_repo, "mod.py", "def foo():\n    pass\n")
        from src.docstring_gen import main

        ret = main(["--repo", str(tmp_repo), "--write"])
        assert ret == 0
        assert (tmp_repo / "docs" / "docstring_report.json").exists()
        assert (tmp_repo / "docs" / "docstring_report.md").exists()
