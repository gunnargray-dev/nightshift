"""Tests for diff visualization utilities."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.diff_visualizer import (
    DiffChunk,
    FileDiff,
    compute_diff,
    diff_files,
    render_html,
    render_terminal,
)


# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


def test_compute_diff_identical():
    text = "line1\nline2\nline3\n"
    diff = compute_diff(text, text, path="file.py")
    assert diff.added == 0
    assert diff.removed == 0


def test_compute_diff_insertion():
    old = "line1\nline2\n"
    new = "line1\nline1.5\nline2\n"
    diff = compute_diff(old, new)
    assert diff.added >= 1


def test_compute_diff_deletion():
    old = "line1\nline2\nline3\n"
    new = "line1\nline3\n"
    diff = compute_diff(old, new)
    assert diff.removed >= 1


def test_compute_diff_replacement():
    old = "aaa\nbbb\nccc\n"
    new = "aaa\nXXX\nccc\n"
    diff = compute_diff(old, new)
    assert diff.added >= 1
    assert diff.removed >= 1


def test_compute_diff_path():
    diff = compute_diff("a\n", "b\n", path="src/main.py")
    assert diff.path == "src/main.py"
    assert diff.old_path is None


def test_file_diff_is_rename():
    diff = FileDiff(path="new.py", old_path="old.py")
    assert diff.is_rename is True


def test_file_diff_not_rename():
    diff = FileDiff(path="same.py", old_path="same.py")
    assert diff.is_rename is False


def test_file_diff_no_old_path():
    diff = FileDiff(path="new.py", old_path=None)
    assert diff.is_rename is False


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------


def test_render_html_contains_table():
    diff = compute_diff("a\nb\n", "a\nc\n")
    html = render_html(diff)
    assert "<table>" in html
    assert "</table>" in html


def test_render_html_add_class():
    diff = compute_diff("old\n", "new\n")
    html = render_html(diff)
    assert 'class="add"' in html or 'class="del"' in html


def test_render_html_escapes_html_chars():
    diff = compute_diff("<b>bold</b>\n", "<i>italic</i>\n")
    html = render_html(diff)
    assert "<b>" not in html  # should be escaped
    assert "&lt;" in html


def test_render_html_empty_diff():
    diff = compute_diff("same\n", "same\n")
    html = render_html(diff)
    assert "<table>" in html


# ---------------------------------------------------------------------------
# render_terminal
# ---------------------------------------------------------------------------


def test_render_terminal_contains_plus_minus():
    diff = compute_diff("old\n", "new\n")
    output = render_terminal(diff, color=False)
    assert "-" in output or "+" in output


def test_render_terminal_no_color():
    diff = compute_diff("a\n", "b\n")
    output = render_terminal(diff, color=False)
    assert "\033[" not in output


def test_render_terminal_with_color():
    diff = compute_diff("a\n", "b\n")
    output = render_terminal(diff, color=True)
    assert "\033[" in output


def test_render_terminal_header_lines():
    diff = compute_diff("x\n", "y\n", path="foo.py")
    output = render_terminal(diff)
    assert "foo.py" in output


# ---------------------------------------------------------------------------
# diff_files
# ---------------------------------------------------------------------------


def test_diff_files_identical(tmp_path):
    f = tmp_path / "file.py"
    f.write_text("hello\nworld\n")
    diff = diff_files(f, f)
    assert diff.added == 0
    assert diff.removed == 0


def test_diff_files_different(tmp_path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("foo\nbar\n")
    b.write_text("foo\nbaz\n")
    diff = diff_files(a, b)
    assert diff.added >= 1
    assert diff.removed >= 1


def test_diff_files_path_set(tmp_path):
    f = tmp_path / "myfile.py"
    f.write_text("x\n")
    diff = diff_files(f, f)
    assert "myfile.py" in diff.path


# ---------------------------------------------------------------------------
# DiffChunk
# ---------------------------------------------------------------------------


def test_diff_chunk_fields():
    chunk = DiffChunk(
        tag="insert",
        old_start=0,
        old_lines=[],
        new_start=5,
        new_lines=["new line\n"],
    )
    assert chunk.tag == "insert"
    assert chunk.new_start == 5
    assert len(chunk.new_lines) == 1
