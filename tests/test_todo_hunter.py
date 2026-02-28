"""Tests for src/todo_hunter.py — 37 tests."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from src.todo_hunter import (
    TodoItem,
    hunt,
    render_todo_report,
    save_todo_report,
    TODO_PATTERN,
    _blame_line,
    _session_from_commit,
    _find_repo_root,
)


@pytest.fixture
def src_with_todos(tmp_path) -> Path:
    """Create a fake src/ directory with TODO/FIXME annotations."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "alpha.py").write_text(
        "# TODO: refactor this function\n"
        "def f(): pass\n"
        "# FIXME: broken edge case\n"
        "x = 1\n"
        "# HACK: workaround for issue #42\n"
        "# NOTE: see PR #7\n"
    )
    (src / "beta.py").write_text(
        "def clean(): pass\n"
        "# This is a normal comment\n"
    )
    return src


@pytest.fixture
def todo_items() -> list[TodoItem]:
    """A few manually constructed TodoItems."""
    return [
        TodoItem("src/alpha.py", 1, "TODO", "refactor this function", 3, 5, True),
        TodoItem("src/alpha.py", 3, "FIXME", "broken edge case", 7, 1, False),
        TodoItem("src/alpha.py", 5, "HACK", "workaround for issue #42", 2, 6, True),
        TodoItem("src/beta.py", 10, "NOTE", "see PR #7", None, 0, False),
    ]


class TestTodoPattern:
    def test_matches_todo(self):
        assert TODO_PATTERN.search("# TODO: do this") is not None

    def test_matches_fixme(self):
        m = TODO_PATTERN.search("# FIXME: broken")
        assert m is not None
        assert m.group(1).upper() == "FIXME"

    def test_matches_hack(self):
        assert TODO_PATTERN.search("# HACK: workaround") is not None

    def test_matches_xxx(self):
        assert TODO_PATTERN.search("# XXX: investigate") is not None

    def test_matches_note(self):
        assert TODO_PATTERN.search("# NOTE: see ticket") is not None

    def test_case_insensitive(self):
        assert TODO_PATTERN.search("# todo: lowercase") is not None

    def test_no_match_on_plain_comment(self):
        assert TODO_PATTERN.search("# This is a normal comment") is None

    def test_captures_text_after_tag(self):
        m = TODO_PATTERN.search("# TODO: refactor the loop")
        assert m is not None
        assert "refactor the loop" in m.group(2)


class TestTodoItem:
    def test_severity_fixme_is_highest(self):
        item = TodoItem("f.py", 1, "FIXME", "text", None, 0, False)
        assert item.severity == 0

    def test_severity_todo_lower_than_fixme(self):
        fixme = TodoItem("f.py", 1, "FIXME", "x", None, 0, False)
        todo = TodoItem("f.py", 2, "TODO", "x", None, 0, False)
        assert todo.severity > fixme.severity

    def test_to_dict_has_all_keys(self):
        item = TodoItem("src/alpha.py", 5, "TODO", "text", 3, 2, False)
        d = item.to_dict()
        assert all(k in d for k in ["file", "line", "tag", "text", "introduced_session", "age_sessions", "is_stale"])


class TestHunt:
    def test_finds_todo_in_source(self, src_with_todos):
        with patch("src.todo_hunter._blame_line", return_value=None):
            items = hunt(src_with_todos, current_session=10, threshold=2)
        assert any(i.tag == "TODO" for i in items)

    def test_finds_fixme(self, src_with_todos):
        with patch("src.todo_hunter._blame_line", return_value=None):
            items = hunt(src_with_todos, current_session=10, threshold=2)
        assert any(i.tag == "FIXME" for i in items)

    def test_clean_file_yields_no_items(self, src_with_todos):
        with patch("src.todo_hunter._blame_line", return_value=None):
            items = hunt(src_with_todos, current_session=10, threshold=2)
        assert not any("beta" in i.file for i in items)

    def test_items_sorted_by_severity(self, src_with_todos):
        with patch("src.todo_hunter._blame_line", return_value=None):
            items = hunt(src_with_todos, current_session=10, threshold=2)
        severities = [i.severity for i in items]
        assert severities == sorted(severities)

    def test_stale_flag_set_when_age_meets_threshold(self, src_with_todos):
        with patch("src.todo_hunter._blame_line", return_value="abc123"), \
             patch("src.todo_hunter._session_from_commit", return_value=1):
            items = hunt(src_with_todos, current_session=10, threshold=2)
        assert any(i.is_stale for i in items)

    def test_age_zero_when_blame_unavailable(self, src_with_todos):
        with patch("src.todo_hunter._blame_line", return_value=None):
            items = hunt(src_with_todos, current_session=10, threshold=2)
        assert all(i.age_sessions == 0 for i in items)

    def test_empty_src_returns_empty(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        assert hunt(src, current_session=5, threshold=2) == []


class TestRenderTodoReport:
    def test_returns_string(self, todo_items):
        assert isinstance(render_todo_report(todo_items, current_session=10), str)

    def test_has_title(self, todo_items):
        assert "# TODO / FIXME Hunter Report" in render_todo_report(todo_items, current_session=10)

    def test_stale_section_present(self, todo_items):
        assert "Stale" in render_todo_report(todo_items, current_session=10)

    def test_recent_section_present(self, todo_items):
        assert "Recent" in render_todo_report(todo_items, current_session=10)

    def test_empty_items_shows_clean_message(self):
        assert "No TODO" in render_todo_report([], current_session=5)

    def test_shows_file_names(self, todo_items):
        assert "src/alpha.py" in render_todo_report(todo_items, current_session=10)

    def test_shows_session_context(self, todo_items):
        assert "Session 10" in render_todo_report(todo_items, current_session=10)


class TestSaveTodoReport:
    def test_creates_markdown_file(self, todo_items, tmp_path):
        out = tmp_path / "todo_report.md"
        with patch("src.todo_hunter._blame_line", return_value=None):
            save_todo_report(todo_items, out, current_session=10)
        assert out.exists()
        assert "TODO" in out.read_text()

    def test_creates_json_sidecar(self, todo_items, tmp_path):
        out = tmp_path / "todo_report.md"
        with patch("src.todo_hunter._blame_line", return_value=None):
            save_todo_report(todo_items, out, current_session=10)
        json_file = tmp_path / "todo_report.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert "items" in data and "total" in data

    def test_creates_parent_dirs(self, todo_items, tmp_path):
        out = tmp_path / "a" / "b" / "report.md"
        with patch("src.todo_hunter._blame_line", return_value=None):
            save_todo_report(todo_items, out, current_session=10)
        assert out.exists()
