"""Tests for src/config.py — Nightshift Config System."""

from __future__ import annotations

from pathlib import Path
import json
import pytest

from src.config import (
    load_config,
    save_default_config,
    NightshiftConfig,
    OutputConfig,
    ComplexityConfig,
    CouplingConfig,
    HealthConfig,
    CoverageConfig,
    TodosConfig,
    ExportConfig,
    SessionConfig,
    _parse_toml,
    _parse_toml_value,
    _merge_dict,
    DEFAULTS,
)


class TestParseTomlValue:
    def test_string_double_quoted(self):
        assert _parse_toml_value('"hello"') == "hello"

    def test_string_single_quoted(self):
        assert _parse_toml_value("'world'") == "world"

    def test_true(self):
        assert _parse_toml_value("true") is True

    def test_false(self):
        assert _parse_toml_value("false") is False

    def test_integer(self):
        assert _parse_toml_value("42") == 42

    def test_float(self):
        assert _parse_toml_value("0.8") == pytest.approx(0.8)

    def test_list_of_strings(self):
        result = _parse_toml_value('["json", "html"]')
        assert result == ["json", "html"]

    def test_empty_list(self):
        assert _parse_toml_value("[]") == []

    def test_bare_string_fallback(self):
        assert _parse_toml_value("markdown") == "markdown"


class TestParseToml:
    def test_simple_section(self):
        toml = "[output]\nformat = \"markdown\"\ncolor = true\n"
        result = _parse_toml(toml)
        assert result["output"]["format"] == "markdown"
        assert result["output"]["color"] is True

    def test_multiple_sections(self):
        toml = "[a]\nx = 1\n[b]\ny = 2\n"
        result = _parse_toml(toml)
        assert result["a"]["x"] == 1
        assert result["b"]["y"] == 2

    def test_comments_ignored(self):
        toml = "# comment\n[output]\n# another\ncolor = false\n"
        result = _parse_toml(toml)
        assert result["output"]["color"] is False

    def test_list_value(self):
        toml = '[export]\ndefault_formats = ["json", "html"]\n'
        result = _parse_toml(toml)
        assert result["export"]["default_formats"] == ["json", "html"]

    def test_float_value(self):
        toml = "[coupling]\ninstability_warn = 0.75\n"
        result = _parse_toml(toml)
        assert result["coupling"]["instability_warn"] == pytest.approx(0.75)

    def test_empty_string(self):
        result = _parse_toml("")
        assert result == {}


class TestMergeDict:
    def test_simple_merge(self):
        assert _merge_dict({"a": 1, "b": 2}, {"b": 99}) == {"a": 1, "b": 99}

    def test_nested_merge(self):
        result = _merge_dict({"s": {"a": 1, "b": 2}}, {"s": {"b": 99}})
        assert result["s"]["a"] == 1
        assert result["s"]["b"] == 99

    def test_does_not_mutate_base(self):
        base = {"a": 1}
        _merge_dict(base, {"a": 2})
        assert base["a"] == 1


class TestNightshiftConfigDefaults:
    def test_returns_config_instance(self):
        assert isinstance(NightshiftConfig.defaults(), NightshiftConfig)

    def test_output_defaults(self):
        cfg = NightshiftConfig.defaults()
        assert cfg.output.format == "markdown"
        assert cfg.output.color is True

    def test_complexity_defaults(self):
        cfg = NightshiftConfig.defaults()
        assert cfg.complexity.hot_spot_threshold == 10
        assert cfg.complexity.critical_threshold == 20

    def test_coupling_defaults(self):
        assert NightshiftConfig.defaults().coupling.instability_warn == pytest.approx(0.8)

    def test_health_defaults(self):
        cfg = NightshiftConfig.defaults()
        assert cfg.health.min_score == 60

    def test_session_defaults(self):
        assert NightshiftConfig.defaults().session.current == 12

    def test_source_is_none(self):
        assert NightshiftConfig.defaults()._source is None


class TestNightshiftConfigToDict:
    def test_returns_dict(self):
        assert isinstance(NightshiftConfig.defaults().to_dict(), dict)

    def test_contains_all_sections(self):
        d = NightshiftConfig.defaults().to_dict()
        for section in ["output", "complexity", "coupling", "health", "coverage", "todos", "export", "session"]:
            assert section in d

    def test_no_source_in_dict(self):
        assert "_source" not in NightshiftConfig.defaults().to_dict()

    def test_json_serializable(self):
        assert isinstance(json.dumps(NightshiftConfig.defaults().to_dict()), str)


class TestNightshiftConfigToToml:
    def test_returns_string(self):
        assert isinstance(NightshiftConfig.defaults().to_toml(), str)

    def test_contains_sections(self):
        toml = NightshiftConfig.defaults().to_toml()
        assert "[output]" in toml
        assert "[complexity]" in toml

    def test_roundtrip(self):
        cfg = NightshiftConfig.defaults()
        parsed = _parse_toml(cfg.to_toml())
        assert parsed["output"]["format"] == "markdown"
        assert parsed["complexity"]["hot_spot_threshold"] == 10


class TestNightshiftConfigToMarkdown:
    def test_returns_string(self):
        assert isinstance(NightshiftConfig.defaults().to_markdown(), str)

    def test_contains_heading(self):
        assert "# Nightshift Configuration" in NightshiftConfig.defaults().to_markdown()

    def test_contains_table_markup(self):
        assert "| Key | Value |" in NightshiftConfig.defaults().to_markdown()


class TestLoadConfig:
    def test_loads_defaults_when_no_file(self, tmp_path):
        cfg = load_config(tmp_path)
        assert isinstance(cfg, NightshiftConfig)
        assert cfg._source is None

    def test_loads_from_file(self, tmp_path):
        (tmp_path / "nightshift.toml").write_text('[output]\nformat = "json"\n')
        cfg = load_config(tmp_path)
        assert cfg.output.format == "json"
        assert cfg._source == tmp_path / "nightshift.toml"

    def test_partial_override_keeps_defaults(self, tmp_path):
        (tmp_path / "nightshift.toml").write_text("[complexity]\nhot_spot_threshold = 15\n")
        cfg = load_config(tmp_path)
        assert cfg.complexity.hot_spot_threshold == 15
        assert cfg.complexity.critical_threshold == 20

    def test_handles_invalid_toml_gracefully(self, tmp_path):
        (tmp_path / "nightshift.toml").write_text("NOT VALID TOML !!@#$")
        cfg = load_config(tmp_path)
        assert isinstance(cfg, NightshiftConfig)

    def test_missing_repo_path_uses_cwd(self):
        assert isinstance(load_config(None), NightshiftConfig)

    def test_coupling_override(self, tmp_path):
        (tmp_path / "nightshift.toml").write_text("[coupling]\ninstability_warn = 0.5\n")
        cfg = load_config(tmp_path)
        assert cfg.coupling.instability_warn == pytest.approx(0.5)


class TestSaveDefaultConfig:
    def test_writes_file(self, tmp_path):
        path = save_default_config(tmp_path)
        assert path.exists()
        assert path.name == "nightshift.toml"

    def test_written_content_parseable(self, tmp_path):
        save_default_config(tmp_path)
        parsed = _parse_toml((tmp_path / "nightshift.toml").read_text())
        assert "output" in parsed

    def test_returns_path(self, tmp_path):
        assert isinstance(save_default_config(tmp_path), Path)

    def test_loadable_after_write(self, tmp_path):
        save_default_config(tmp_path)
        cfg = load_config(tmp_path)
        assert cfg._source is not None
