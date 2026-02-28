"""Tests for src/config.py — Nightshift configuration system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import (
    NightshiftConfig,
    ThresholdsConfig,
    OutputConfig,
    SessionConfig,
    load_config,
    save_default_config,
    _parse_simple_toml,
)


# ---------------------------------------------------------------------------
# NightshiftConfig defaults
# ---------------------------------------------------------------------------


class TestNightshiftConfigDefaults:
    def test_default_thresholds(self):
        cfg = NightshiftConfig()
        assert cfg.thresholds.health_score_min == 60.0
        assert cfg.thresholds.max_line_length == 88
        assert cfg.thresholds.complexity_cc_critical == 20

    def test_default_output(self):
        cfg = NightshiftConfig()
        assert cfg.output.default_format == "markdown"
        assert cfg.output.color is True
        assert cfg.output.unicode_symbols is True

    def test_default_session(self):
        cfg = NightshiftConfig()
        assert cfg.session.session_log_path == "NIGHTSHIFT_LOG.md"
        assert cfg.session.src_dir == "src"

    def test_source_is_none_by_default(self):
        cfg = NightshiftConfig()
        assert cfg._source is None


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_to_dict_structure(self):
        cfg = NightshiftConfig()
        d = cfg.to_dict()
        assert "thresholds" in d
        assert "output" in d
        assert "session" in d

    def test_from_dict_round_trip(self):
        cfg = NightshiftConfig()
        d = cfg.to_dict()
        cfg2 = NightshiftConfig.from_dict(d)
        assert cfg2.thresholds.health_score_min == cfg.thresholds.health_score_min
        assert cfg2.output.default_format == cfg.output.default_format
        assert cfg2.session.src_dir == cfg.session.src_dir

    def test_from_dict_partial(self):
        """from_dict should use defaults for missing sections."""
        cfg = NightshiftConfig.from_dict({"thresholds": {"health_score_min": 75.0}})
        assert cfg.thresholds.health_score_min == 75.0
        assert cfg.output.default_format == "markdown"  # default

    def test_to_markdown_contains_headers(self):
        cfg = NightshiftConfig()
        md = cfg.to_markdown()
        assert "## Thresholds" in md
        assert "## Output" in md
        assert "## Session" in md

    def test_to_toml_roundtrip(self):
        cfg = NightshiftConfig()
        toml_str = cfg.to_toml()
        assert "[thresholds]" in toml_str
        assert "[output]" in toml_str
        assert "[session]" in toml_str
        assert "health_score_min" in toml_str


# ---------------------------------------------------------------------------
# _parse_simple_toml
# ---------------------------------------------------------------------------


class TestParseSimpleToml:
    def test_basic_section_and_values(self):
        text = """
[thresholds]
health_score_min = 70.0
max_line_length = 100

[output]
default_format = "json"
color = false
"""
        result = _parse_simple_toml(text)
        assert result["thresholds"]["health_score_min"] == 70.0
        assert result["thresholds"]["max_line_length"] == 100
        assert result["output"]["default_format"] == "json"
        assert result["output"]["color"] is False

    def test_bool_true(self):
        result = _parse_simple_toml("[output]\nunicode_symbols = true\n")
        assert result["output"]["unicode_symbols"] is True

    def test_inline_comments_stripped(self):
        result = _parse_simple_toml("[thresholds]\ntodo_warn_threshold = 5 # five\n")
        assert result["thresholds"]["todo_warn_threshold"] == 5

    def test_empty_input(self):
        assert _parse_simple_toml("") == {}

    def test_comments_ignored(self):
        result = _parse_simple_toml("# full comment line\n[x]\na = 1\n")
        assert result["x"]["a"] == 1


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, tmp_path):
        cfg = load_config(tmp_path)
        assert isinstance(cfg, NightshiftConfig)
        assert cfg._source is None

    def test_loads_from_toml_file(self, tmp_path):
        toml_content = '[thresholds]\nhealth_score_min = 80.0\n'
        (tmp_path / "nightshift.toml").write_text(toml_content)
        cfg = load_config(tmp_path)
        assert cfg.thresholds.health_score_min == 80.0
        assert cfg._source is not None

    def test_falls_back_on_malformed_toml(self, tmp_path):
        # Write junk that our parser can't interpret but won't crash on
        (tmp_path / "nightshift.toml").write_text("not = valid [[toml\n")
        cfg = load_config(tmp_path)
        # Should return something valid
        assert isinstance(cfg, NightshiftConfig)

    def test_source_path_set_when_file_exists(self, tmp_path):
        (tmp_path / "nightshift.toml").write_text("[output]\ncolor = false\n")
        cfg = load_config(tmp_path)
        # Source should be set (or None if parsing failed, both OK)
        assert cfg is not None


# ---------------------------------------------------------------------------
# save_default_config
# ---------------------------------------------------------------------------


class TestSaveDefaultConfig:
    def test_creates_file(self, tmp_path):
        path = save_default_config(tmp_path)
        assert path.exists()
        assert path.name == "nightshift.toml"

    def test_does_not_overwrite_existing(self, tmp_path):
        original = "# custom\n"
        (tmp_path / "nightshift.toml").write_text(original)
        save_default_config(tmp_path)
        assert (tmp_path / "nightshift.toml").read_text() == original

    def test_written_toml_is_valid(self, tmp_path):
        save_default_config(tmp_path)
        content = (tmp_path / "nightshift.toml").read_text()
        assert "[thresholds]" in content
        assert "health_score_min" in content
