"""Tests for src/dna.py — Repo DNA Fingerprint."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from src.dna import (
    DnaChannel,
    RepoDna,
    fingerprint_repo,
    save_dna_report,
    _compute_avg_complexity,
    _compute_coupling_ratio,
    _compute_docstring_coverage,
    _compute_test_depth,
    _compute_file_size_entropy,
    _compute_age_entropy,
    _compute_hex_digest,
    _normalise_complexity,
    _generate_fingerprint_narrative,
    _FILL_CHARS,
    _BAND_WIDTH,
)


# ---------------------------------------------------------------------------
# Sample sources
# ---------------------------------------------------------------------------

SIMPLE_SRC = '''\
"""A module."""

from __future__ import annotations
import ast
from pathlib import Path


def analyze(path: Path) -> dict:
    """Analyze a path."""
    if not path.exists():
        return {}
    result = {}
    for f in path.glob("*.py"):
        result[f.name] = 1
    return result


def save(data: dict, out: Path) -> None:
    """Save data."""
    out.write_text(str(data))
'''

COMPLEX_SRC = '''\
"""A complex module."""

def complex_func(x, y, z):
    """Lots of branches."""
    if x > 0:
        for i in range(y):
            if i % 2:
                try:
                    if z > i:
                        while True:
                            break
                except Exception:
                    pass
    return x


def another(a, b):
    """Another function."""
    if a:
        if b:
            return True
    return False
'''

SIMPLE_TEST = '''\
"""Tests."""

def test_one():
    assert True

def test_two():
    assert True

def test_three():
    assert True

def test_four():
    assert True
'''

SAMPLE_LOG = """\
# Nightshift Log

---

## Session 1 — February 27, 2026

`src/simple.py` introduced.

---

## Session 2 — February 28, 2026

`src/complex.py` introduced.

---
"""


@pytest.fixture()
def src_dir(tmp_path: Path) -> Path:
    d = tmp_path / "src"
    d.mkdir()
    (d / "__init__.py").write_text("")
    (d / "simple.py").write_text(SIMPLE_SRC)
    (d / "complex.py").write_text(COMPLEX_SRC)
    return d


@pytest.fixture()
def tests_dir(tmp_path: Path) -> Path:
    d = tmp_path / "tests"
    d.mkdir()
    (d / "test_simple.py").write_text(SIMPLE_TEST)
    return d


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "NIGHTSHIFT_LOG.md"
    p.write_text(SAMPLE_LOG)
    return p


@pytest.fixture()
def repo(tmp_path: Path, src_dir: Path, tests_dir: Path, log_file: Path) -> Path:
    return tmp_path


# ---------------------------------------------------------------------------
# _normalise_complexity
# ---------------------------------------------------------------------------


def test_normalise_complexity_min():
    assert _normalise_complexity(1.0) == 1.0


def test_normalise_complexity_high():
    assert _normalise_complexity(10.0) == 0.0


def test_normalise_complexity_clamp_above():
    assert _normalise_complexity(20.0) == 0.0


def test_normalise_complexity_mid():
    val = _normalise_complexity(5.5)
    assert 0 < val < 1.0


def test_normalise_complexity_non_negative():
    for cc in [1, 3, 5, 8, 10, 15, 20]:
        assert _normalise_complexity(cc) >= 0.0


# ---------------------------------------------------------------------------
# _compute_avg_complexity
# ---------------------------------------------------------------------------


def test_compute_avg_complexity_returns_tuple(src_dir: Path):
    avg, per_file = _compute_avg_complexity(src_dir)
    assert isinstance(avg, float)
    assert isinstance(per_file, list)


def test_compute_avg_complexity_positive(src_dir: Path):
    avg, _ = _compute_avg_complexity(src_dir)
    assert avg >= 1.0


def test_compute_avg_complexity_per_file_names(src_dir: Path):
    _, per_file = _compute_avg_complexity(src_dir)
    names = [name for name, _ in per_file]
    assert "simple" in names
    assert "complex" in names


def test_compute_avg_complexity_complex_higher(src_dir: Path):
    _, per_file = _compute_avg_complexity(src_dir)
    cc_map = dict(per_file)
    # complex.py should have higher CC than simple.py
    assert cc_map["complex"] >= cc_map["simple"]


def test_compute_avg_complexity_empty_dir(tmp_path: Path):
    empty = tmp_path / "empty_src"
    empty.mkdir()
    avg, per_file = _compute_avg_complexity(empty)
    assert avg == 1.0
    assert per_file == []


def test_compute_avg_complexity_bad_syntax(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "bad.py").write_text("def broken(: pass")
    avg, per_file = _compute_avg_complexity(d)
    assert len(per_file) == 1
    assert per_file[0][0] == "bad"


# ---------------------------------------------------------------------------
# _compute_coupling_ratio
# ---------------------------------------------------------------------------


def test_compute_coupling_ratio_range(src_dir: Path):
    ratio = _compute_coupling_ratio(src_dir)
    assert 0.0 <= ratio <= 1.0


def test_compute_coupling_ratio_no_src_imports(src_dir: Path):
    # simple.py and complex.py don't import from src.*
    ratio = _compute_coupling_ratio(src_dir)
    assert ratio == 0.0


def test_compute_coupling_ratio_with_src_imports(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "modA.py").write_text("from src.modB import something\nimport ast\n")
    ratio = _compute_coupling_ratio(d)
    assert ratio > 0.0


def test_compute_coupling_ratio_empty_dir(tmp_path: Path):
    empty = tmp_path / "src"
    empty.mkdir()
    assert _compute_coupling_ratio(empty) == 0.0


# ---------------------------------------------------------------------------
# _compute_docstring_coverage
# ---------------------------------------------------------------------------


def test_compute_docstring_coverage_range(src_dir: Path):
    cov = _compute_docstring_coverage(src_dir)
    assert 0.0 <= cov <= 1.0


def test_compute_docstring_coverage_well_documented(src_dir: Path):
    # SIMPLE_SRC has docstrings on both public functions
    cov = _compute_docstring_coverage(src_dir)
    assert cov > 0.0


def test_compute_docstring_coverage_empty_dir(tmp_path: Path):
    empty = tmp_path / "src"
    empty.mkdir()
    assert _compute_docstring_coverage(empty) == 0.0


def test_compute_docstring_coverage_no_public_functions(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "constants.py").write_text("X = 1\nY = 2\n")
    assert _compute_docstring_coverage(d) == 0.0


# ---------------------------------------------------------------------------
# _compute_test_depth
# ---------------------------------------------------------------------------


def test_compute_test_depth_range(src_dir: Path, tests_dir: Path):
    depth = _compute_test_depth(src_dir, tests_dir)
    assert 0.0 <= depth <= 1.0


def test_compute_test_depth_nonzero(src_dir: Path, tests_dir: Path):
    depth = _compute_test_depth(src_dir, tests_dir)
    assert depth > 0.0


def test_compute_test_depth_no_tests(src_dir: Path, tmp_path: Path):
    empty_tests = tmp_path / "empty_tests"
    empty_tests.mkdir()
    depth = _compute_test_depth(src_dir, empty_tests)
    assert depth == 0.0


def test_compute_test_depth_no_src_functions(tmp_path: Path, tests_dir: Path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "const.py").write_text("X = 1\n")
    depth = _compute_test_depth(d, tests_dir)
    assert depth == 0.0


# ---------------------------------------------------------------------------
# _compute_file_size_entropy
# ---------------------------------------------------------------------------


def test_file_size_entropy_range(src_dir: Path):
    entropy = _compute_file_size_entropy(src_dir)
    assert 0.0 <= entropy <= 1.0


def test_file_size_entropy_single_file(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    (d / "only.py").write_text("x = 1\n")
    entropy = _compute_file_size_entropy(d)
    assert entropy == 0.5  # single file → neutral


def test_file_size_entropy_equal_files(tmp_path: Path):
    d = tmp_path / "src"
    d.mkdir()
    content = "x = 1\n" * 50
    for i in range(4):
        (d / f"mod{i}.py").write_text(content)
    entropy = _compute_file_size_entropy(d)
    assert entropy > 0.8  # uniform distribution = high entropy


def test_file_size_entropy_empty_dir(tmp_path: Path):
    empty = tmp_path / "src"
    empty.mkdir()
    entropy = _compute_file_size_entropy(empty)
    assert entropy == 0.5  # no files → neutral


# ---------------------------------------------------------------------------
# _compute_age_entropy
# ---------------------------------------------------------------------------


def test_age_entropy_range(log_file: Path, src_dir: Path):
    entropy = _compute_age_entropy(log_file, src_dir)
    assert 0.0 <= entropy <= 1.0


def test_age_entropy_no_log(tmp_path: Path, src_dir: Path):
    missing = tmp_path / "missing.md"
    entropy = _compute_age_entropy(missing, src_dir)
    assert entropy == 0.5


def test_age_entropy_empty_dir(log_file: Path, tmp_path: Path):
    empty = tmp_path / "empty_src"
    empty.mkdir()
    entropy = _compute_age_entropy(log_file, empty)
    # All modules in one "session" → low entropy or neutral
    assert 0.0 <= entropy <= 1.0


# ---------------------------------------------------------------------------
# _compute_hex_digest
# ---------------------------------------------------------------------------


def test_hex_digest_length():
    channels = [
        DnaChannel("A ", 0.5, 0.5, "desc"),
        DnaChannel("B ", 0.3, 0.3, "desc"),
    ]
    digest = _compute_hex_digest(channels)
    assert len(digest) == 8


def test_hex_digest_uppercase():
    channels = [DnaChannel("A ", 0.5, 0.5, "desc")]
    digest = _compute_hex_digest(channels)
    assert digest == digest.upper()


def test_hex_digest_deterministic():
    channels = [DnaChannel("A ", 0.5, 0.5, "desc")]
    d1 = _compute_hex_digest(channels)
    d2 = _compute_hex_digest(channels)
    assert d1 == d2


def test_hex_digest_changes_with_values():
    ch1 = [DnaChannel("A ", 0.5, 0.5, "desc")]
    ch2 = [DnaChannel("A ", 0.9, 0.9, "desc")]
    assert _compute_hex_digest(ch1) != _compute_hex_digest(ch2)


# ---------------------------------------------------------------------------
# DnaChannel
# ---------------------------------------------------------------------------


def test_dna_channel_render_bar_full():
    ch = DnaChannel("Test ", 1.0, 1.0, "desc")
    bar = ch.render_bar(10)
    assert len(bar) == 10
    assert all(c in _FILL_CHARS for c in bar)


def test_dna_channel_render_bar_empty():
    ch = DnaChannel("Test ", 0.0, 0.0, "desc")
    bar = ch.render_bar(10)
    assert len(bar) == 10


def test_dna_channel_render_bar_half():
    ch = DnaChannel("Test ", 0.5, 0.5, "desc")
    bar = ch.render_bar(10)
    assert len(bar) == 10


def test_dna_channel_to_dict():
    ch = DnaChannel("Test ", 0.7, 0.7, "A description")
    d = ch.to_dict()
    assert d["label"] == "Test "
    assert d["value"] == 0.7
    assert d["description"] == "A description"


# ---------------------------------------------------------------------------
# fingerprint_repo
# ---------------------------------------------------------------------------


def test_fingerprint_repo_returns_dna(repo: Path):
    dna = fingerprint_repo(repo)
    assert isinstance(dna, RepoDna)


def test_fingerprint_repo_has_6_channels(repo: Path):
    dna = fingerprint_repo(repo)
    assert len(dna.channels) == 6


def test_fingerprint_repo_has_hex_digest(repo: Path):
    dna = fingerprint_repo(repo)
    assert len(dna.hex_digest) == 8


def test_fingerprint_repo_has_per_file_data(repo: Path):
    dna = fingerprint_repo(repo)
    assert len(dna.per_file_complexity) >= 1


def test_fingerprint_repo_channel_values_range(repo: Path):
    dna = fingerprint_repo(repo)
    for ch in dna.channels:
        assert 0.0 <= ch.value <= 1.0


def test_fingerprint_repo_total_modules(repo: Path):
    dna = fingerprint_repo(repo)
    assert dna.total_modules >= 1


def test_fingerprint_repo_total_lines(repo: Path):
    dna = fingerprint_repo(repo)
    assert dna.total_lines > 0


def test_fingerprint_repo_deterministic(repo: Path):
    dna1 = fingerprint_repo(repo)
    dna2 = fingerprint_repo(repo)
    assert dna1.hex_digest == dna2.hex_digest


def test_fingerprint_repo_no_src_dir(tmp_path: Path):
    dna = fingerprint_repo(tmp_path)
    assert dna.hex_digest == "00000000"
    assert dna.channels == []


# ---------------------------------------------------------------------------
# RepoDna.to_markdown
# ---------------------------------------------------------------------------


def test_to_markdown_has_title(repo: Path):
    dna = fingerprint_repo(repo)
    md = dna.to_markdown()
    assert "# Repo DNA Fingerprint" in md


def test_to_markdown_has_hex_id(repo: Path):
    dna = fingerprint_repo(repo)
    md = dna.to_markdown()
    assert dna.hex_digest in md


def test_to_markdown_has_dna_band(repo: Path):
    dna = fingerprint_repo(repo)
    md = dna.to_markdown()
    assert "DNA Band" in md


def test_to_markdown_has_channel_table(repo: Path):
    dna = fingerprint_repo(repo)
    md = dna.to_markdown()
    assert "Channel Breakdown" in md
    assert "| Channel |" in md


def test_to_markdown_has_per_file_section(repo: Path):
    dna = fingerprint_repo(repo)
    md = dna.to_markdown()
    assert "Per-File Complexity" in md


def test_to_markdown_has_narrative(repo: Path):
    dna = fingerprint_repo(repo)
    md = dna.to_markdown()
    assert "fingerprint" in md.lower()


def test_to_json_valid(repo: Path):
    dna = fingerprint_repo(repo)
    data = json.loads(dna.to_json())
    assert "hex_digest" in data
    assert "channels" in data
    assert len(data["channels"]) == 6


def test_to_json_channels_have_fields(repo: Path):
    dna = fingerprint_repo(repo)
    data = json.loads(dna.to_json())
    for ch in data["channels"]:
        assert "label" in ch
        assert "value" in ch
        assert "raw_value" in ch
        assert "description" in ch


# ---------------------------------------------------------------------------
# _generate_fingerprint_narrative
# ---------------------------------------------------------------------------


def test_fingerprint_narrative_nonempty(repo: Path):
    dna = fingerprint_repo(repo)
    narrative = _generate_fingerprint_narrative(dna)
    assert len(narrative) > 20


def test_fingerprint_narrative_contains_digest(repo: Path):
    dna = fingerprint_repo(repo)
    narrative = _generate_fingerprint_narrative(dna)
    assert dna.hex_digest in narrative


# ---------------------------------------------------------------------------
# save_dna_report
# ---------------------------------------------------------------------------


def test_save_dna_report_writes_md(tmp_path: Path, repo: Path):
    dna = fingerprint_repo(repo)
    out = tmp_path / "docs" / "dna.md"
    save_dna_report(dna, out)
    assert out.exists()
    assert "DNA" in out.read_text()


def test_save_dna_report_writes_json(tmp_path: Path, repo: Path):
    dna = fingerprint_repo(repo)
    out = tmp_path / "docs" / "dna.md"
    save_dna_report(dna, out)
    json_out = out.with_suffix(".json")
    assert json_out.exists()
    json.loads(json_out.read_text())


def test_save_dna_report_creates_dirs(tmp_path: Path, repo: Path):
    dna = fingerprint_repo(repo)
    out = tmp_path / "a" / "b" / "dna.md"
    save_dna_report(dna, out)
    assert out.exists()
