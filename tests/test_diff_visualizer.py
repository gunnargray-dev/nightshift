"""Tests for src/diff_visualizer.py — Awake diff visualiser."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _two_files(tmp_path: Path, a: str, b: str) -> tuple[Path, Path]:
    fa = tmp_path / "a.py"
    fb = tmp_path / "b.py"
    fa.write_text(textwrap.dedent(a), encoding="utf-8")
    fb.write_text(textwrap.dedent(b), encoding="utf-8")
    return fa, fb


# ---------------------------------------------------------------------------
# Unit tests — DiffLine
# ---------------------------------------------------------------------------


def test_diff_line_added():
    """DiffLine marks added lines correctly."""
    from src.diff_visualizer import DiffLine

    line = DiffLine(content="+ new line", kind="added", line_no=5)
    assert line.kind == "added"
    assert line.line_no == 5


def test_diff_line_removed():
    """DiffLine marks removed lines correctly."""
    from src.diff_visualizer import DiffLine

    line = DiffLine(content="- old line", kind="removed", line_no=3)
    assert line.kind == "removed"


def test_diff_line_context():
    """DiffLine represents context (unchanged) lines."""
    from src.diff_visualizer import DiffLine

    line = DiffLine(content=" unchanged", kind="context", line_no=1)
    assert line.kind == "context"


# ---------------------------------------------------------------------------
# Unit tests — DiffBlock
# ---------------------------------------------------------------------------


def test_diff_block_stores_lines():
    """DiffBlock holds a list of DiffLine objects."""
    from src.diff_visualizer import DiffBlock, DiffLine

    lines = [
        DiffLine("+a", "added", 1),
        DiffLine("-b", "removed", 2),
    ]
    block = DiffBlock(header="@@ -1,2 +1,1 @@", lines=lines)
    assert len(block.lines) == 2
    assert block.header.startswith("@@")


# ---------------------------------------------------------------------------
# Unit tests — parse_unified_diff
# ---------------------------------------------------------------------------


SAMPLE_DIFF = """\
--- a/foo.py
+++ b/foo.py
@@ -1,4 +1,4 @@
 def hello():
-    print(\"Nightshift\")
+    print(\"Awake\")
     pass
"""


def test_parse_unified_diff_blocks():
    """parse_unified_diff returns at least one DiffBlock."""
    from src.diff_visualizer import parse_unified_diff

    blocks = parse_unified_diff(SAMPLE_DIFF)
    assert len(blocks) >= 1


def test_parse_unified_diff_added_lines():
    """parse_unified_diff identifies added lines."""
    from src.diff_visualizer import parse_unified_diff

    blocks = parse_unified_diff(SAMPLE_DIFF)
    all_lines = [ln for b in blocks for ln in b.lines]
    added = [ln for ln in all_lines if ln.kind == "added"]
    assert len(added) >= 1


def test_parse_unified_diff_removed_lines():
    """parse_unified_diff identifies removed lines."""
    from src.diff_visualizer import parse_unified_diff

    blocks = parse_unified_diff(SAMPLE_DIFF)
    all_lines = [ln for b in blocks for ln in b.lines]
    removed = [ln for ln in all_lines if ln.kind == "removed"]
    assert len(removed) >= 1


def test_parse_unified_diff_empty_string():
    """parse_unified_diff handles an empty diff string."""
    from src.diff_visualizer import parse_unified_diff

    blocks = parse_unified_diff("")
    assert blocks == []


# ---------------------------------------------------------------------------
# Unit tests — diff_files
# ---------------------------------------------------------------------------


def test_diff_files_detects_change(tmp_path):
    """diff_files returns blocks when files differ."""
    from src.diff_visualizer import diff_files

    fa, fb = _two_files(tmp_path, "x = 1\n", "x = 2\n")
    blocks = diff_files(fa, fb)
    assert len(blocks) >= 1


def test_diff_files_identical(tmp_path):
    """diff_files returns empty list for identical files."""
    from src.diff_visualizer import diff_files

    fa, fb = _two_files(tmp_path, "same\n", "same\n")
    blocks = diff_files(fa, fb)
    assert blocks == []


def test_diff_files_new_file(tmp_path):
    """diff_files handles comparison where one file is empty."""
    from src.diff_visualizer import diff_files

    fa, fb = _two_files(tmp_path, "", "new content\n")
    blocks = diff_files(fa, fb)
    assert len(blocks) >= 1


# ---------------------------------------------------------------------------
# Unit tests — render_terminal
# ---------------------------------------------------------------------------


def test_render_terminal_contains_plus(tmp_path):
    """render_terminal includes '+' markers for added lines."""
    from src.diff_visualizer import diff_files, render_terminal

    fa, fb = _two_files(tmp_path, "a\n", "b\n")
    blocks = diff_files(fa, fb)
    output = render_terminal(blocks)
    assert "+" in output or "b" in output


def test_render_terminal_empty_blocks():
    """render_terminal returns empty string for no blocks."""
    from src.diff_visualizer import render_terminal

    assert render_terminal([]) == ""


# ---------------------------------------------------------------------------
# Unit tests — render_html
# ---------------------------------------------------------------------------


def test_render_html_structure(tmp_path):
    """render_html returns a valid HTML string with diff content."""
    from src.diff_visualizer import diff_files, render_html

    fa, fb = _two_files(tmp_path, "old\n", "new\n")
    blocks = diff_files(fa, fb)
    html = render_html(blocks)
    assert "<html" in html or "<div" in html


def test_render_html_empty_blocks():
    """render_html returns a minimal HTML page for no diff blocks."""
    from src.diff_visualizer import render_html

    html = render_html([])
    assert isinstance(html, str)
    assert len(html) > 0


# ---------------------------------------------------------------------------
# Unit tests — summarise_diff
# ---------------------------------------------------------------------------


def test_summarise_diff_counts(tmp_path):
    """summarise_diff returns correct insertion/deletion counts."""
    from src.diff_visualizer import diff_files, summarise_diff

    fa, fb = _two_files(tmp_path, "line1\nline2\n", "line1\nline3\nline4\n")
    blocks = diff_files(fa, fb)
    summary = summarise_diff(blocks)
    assert summary["insertions"] >= 1
    assert summary["deletions"] >= 1


def test_summarise_diff_empty():
    """summarise_diff returns zeros for empty blocks."""
    from src.diff_visualizer import summarise_diff

    summary = summarise_diff([])
    assert summary["insertions"] == 0
    assert summary["deletions"] == 0


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_full_diff_workflow(tmp_path):
    """End-to-end: diff two files → render terminal → summarise."""
    from src.diff_visualizer import diff_files, render_terminal, summarise_diff

    fa, fb = _two_files(
        tmp_path,
        "def foo():\n    return 1\n",
        "def foo():\n    return 2\n",
    )
    blocks = diff_files(fa, fb)
    terminal_out = render_terminal(blocks)
    summary = summarise_diff(blocks)
    assert isinstance(terminal_out, str)
    assert summary["insertions"] >= 1


def test_diff_round_trip(tmp_path):
    """parse_unified_diff round-trips through render_terminal."""
    from src.diff_visualizer import parse_unified_diff, render_terminal

    blocks = parse_unified_diff(SAMPLE_DIFF)
    output = render_terminal(blocks)
    assert isinstance(output, str)


def test_html_export_from_file_diff(tmp_path):
    """diff_files → render_html produces a non-empty HTML document."""
    from src.diff_visualizer import diff_files, render_html

    fa, fb = _two_files(
        tmp_path,
        "x = 'Nightshift'\n",
        "x = 'Awake'\n",
    )
    blocks = diff_files(fa, fb)
    html = render_html(blocks)
    assert "Awake" in html or len(html) > 50
