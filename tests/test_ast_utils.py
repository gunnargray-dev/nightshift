"""Tests for src._ast_utils."""

from __future__ import annotations

from pathlib import Path

from src._ast_utils import parse_file


def test_parse_valid_file(tmp_path: Path):
    f = tmp_path / "valid.py"
    f.write_text("x = 1\n")
    tree = parse_file(f)
    assert tree is not None


def test_parse_syntax_error(tmp_path: Path):
    f = tmp_path / "bad.py"
    f.write_text("def f(\n")
    tree = parse_file(f)
    assert tree is None


def test_parse_nonascii(tmp_path: Path):
    f = tmp_path / "utf8.py"
    f.write_text("# \u00e9\nx = 1\n", encoding="utf-8")
    tree = parse_file(f)
    assert tree is not None
