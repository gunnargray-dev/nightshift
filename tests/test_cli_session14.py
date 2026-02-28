"""CLI tests for the Session 14 subcommands: story, maturity, teach, dna."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.cli import build_parser, cmd_story, cmd_maturity, cmd_teach, cmd_dna

# ---------------------------------------------------------------------------
# Minimal log / repo fixture
# ---------------------------------------------------------------------------

SAMPLE_LOG = """\
# Nightshift Log

---

## Session 1 — February 27, 2026

**Tasks completed:**

- ✅ **Stats engine** → [PR #1](https://github.com/gunnargray-dev/nightshift/pull/1) — `src/stats.py`.

**Stats snapshot:**

- Total PRs: 1
- Lines changed: ~500
- Test suite: 50 tests

**Notes:** Session 1 theme: foundation.

---
"""

SAMPLE_SRC = '''\
"""A sample module."""
from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass


@dataclass
class Result:
    """A result."""
    score: float = 0.0

    def to_markdown(self) -> str:
        """Render."""
        return f"score: {self.score}"

    def to_dict(self) -> dict:
        """Serialize."""
        return {"score": self.score}


def analyze(repo_path: Path) -> Result:
    """Analyze."""
    return Result()


def save_result(result: Result, out: Path) -> None:
    """Save."""
    out.write_text(result.to_markdown())
'''

SAMPLE_TEST = """\
def test_one(): assert True
def test_two(): assert True
def test_three(): assert True
"""


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "NIGHTSHIFT_LOG.md").write_text(SAMPLE_LOG)
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "sample.py").write_text(SAMPLE_SRC)
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text(SAMPLE_TEST)
    return tmp_path


def _make_args(repo: Path, **kwargs):
    """Create a minimal argparse.Namespace-like object."""
    import argparse
    defaults = {
        "repo": str(repo),
        "write": False,
        "json": False,
    }
    defaults.update(kwargs)
    ns = argparse.Namespace(**defaults)
    return ns


# ---------------------------------------------------------------------------
# story subcommand
# ---------------------------------------------------------------------------


def test_cmd_story_prints_markdown(repo: Path, capsys):
    args = _make_args(repo)
    rc = cmd_story(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Chapter" in out or "Story" in out


def test_cmd_story_json_output(repo: Path, capsys):
    args = _make_args(repo, json=True)
    rc = cmd_story(args)
    assert rc == 0
    out = capsys.readouterr().out
    json_start = out.find("{")
    assert json_start != -1, "No JSON found in output"
    data = json.loads(out[json_start:])
    assert "chapters" in data


def test_cmd_story_write(repo: Path):
    args = _make_args(repo, write=True)
    rc = cmd_story(args)
    assert rc == 0
    out_md = repo / "docs" / "story.md"
    assert out_md.exists()


def test_cmd_story_write_json_sidecar(repo: Path):
    args = _make_args(repo, write=True)
    cmd_story(args)
    assert (repo / "docs" / "story.json").exists()


# ---------------------------------------------------------------------------
# maturity subcommand
# ---------------------------------------------------------------------------


def test_cmd_maturity_prints_markdown(repo: Path, capsys):
    args = _make_args(repo)
    rc = cmd_maturity(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Maturity" in out or "Module" in out or "sample" in out


def test_cmd_maturity_json_output(repo: Path, capsys):
    args = _make_args(repo, json=True)
    rc = cmd_maturity(args)
    assert rc == 0
    out = capsys.readouterr().out
    json_start = out.find("{")
    assert json_start != -1
    data = json.loads(out[json_start:])
    assert "modules" in data


def test_cmd_maturity_write(repo: Path):
    args = _make_args(repo, write=True)
    rc = cmd_maturity(args)
    assert rc == 0
    assert (repo / "docs" / "maturity_report.md").exists()


def test_cmd_maturity_write_json(repo: Path):
    args = _make_args(repo, write=True)
    cmd_maturity(args)
    assert (repo / "docs" / "maturity_report.json").exists()


# ---------------------------------------------------------------------------
# teach subcommand
# ---------------------------------------------------------------------------


def test_cmd_teach_prints_tutorial(repo: Path, capsys):
    args = _make_args(repo, module="sample")
    rc = cmd_teach(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Tutorial" in out or "sample" in out


def test_cmd_teach_json_output(repo: Path, capsys):
    args = _make_args(repo, module="sample", json=True)
    rc = cmd_teach(args)
    assert rc == 0
    out = capsys.readouterr().out
    json_start = out.find("{")
    assert json_start != -1
    data = json.loads(out[json_start:])
    assert "module_name" in data


def test_cmd_teach_write(repo: Path):
    args = _make_args(repo, module="sample", write=True)
    rc = cmd_teach(args)
    assert rc == 0
    assert (repo / "docs" / "tutorials" / "sample.md").exists()


def test_cmd_teach_missing_module(repo: Path, capsys):
    args = _make_args(repo, module="nonexistent_xyz")
    rc = cmd_teach(args)
    assert rc == 1


def test_cmd_teach_list(repo: Path, capsys):
    args = _make_args(repo, module="list")
    rc = cmd_teach(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "sample" in out


# ---------------------------------------------------------------------------
# dna subcommand
# ---------------------------------------------------------------------------


def test_cmd_dna_prints_fingerprint(repo: Path, capsys):
    args = _make_args(repo)
    rc = cmd_dna(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "DNA" in out or "Fingerprint" in out


def test_cmd_dna_json_output(repo: Path, capsys):
    args = _make_args(repo, json=True)
    rc = cmd_dna(args)
    assert rc == 0
    out = capsys.readouterr().out
    json_start = out.find("{")
    assert json_start != -1
    data = json.loads(out[json_start:])
    assert "hex_digest" in data
    assert "channels" in data


def test_cmd_dna_write(repo: Path):
    args = _make_args(repo, write=True)
    rc = cmd_dna(args)
    assert rc == 0
    assert (repo / "docs" / "dna.md").exists()


def test_cmd_dna_write_json_sidecar(repo: Path):
    args = _make_args(repo, write=True)
    cmd_dna(args)
    assert (repo / "docs" / "dna.json").exists()


# ---------------------------------------------------------------------------
# Argument parser: confirm Session 14 commands registered
# ---------------------------------------------------------------------------


def test_parser_has_story_command():
    p = build_parser()
    subparsers = p._subparsers._actions[-1].choices
    assert "story" in subparsers


def test_parser_has_maturity_command():
    p = build_parser()
    subparsers = p._subparsers._actions[-1].choices
    assert "maturity" in subparsers


def test_parser_has_teach_command():
    p = build_parser()
    subparsers = p._subparsers._actions[-1].choices
    assert "teach" in subparsers


def test_parser_has_dna_command():
    p = build_parser()
    subparsers = p._subparsers._actions[-1].choices
    assert "dna" in subparsers


def test_parser_total_subcommand_count():
    p = build_parser()
    subparsers = p._subparsers._actions[-1].choices
    assert len(subparsers) >= 31  # 27 existing + 4 new
