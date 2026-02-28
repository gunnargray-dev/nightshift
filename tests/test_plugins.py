"""Tests for src/plugins.py — Plugin/Hook Architecture."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.plugins import (
    PluginDefinition,
    PluginResult,
    PluginRunReport,
    load_plugin_definitions,
    run_plugins,
    list_plugins,
    EXAMPLE_TOML_SNIPPET,
)


# ---------------------------------------------------------------------------
# PluginDefinition
# ---------------------------------------------------------------------------


def test_plugin_definition_from_dict_defaults():
    defn = PluginDefinition.from_dict({})
    assert defn.name == "unknown"
    assert defn.module == ""
    assert defn.function == ""
    assert defn.hooks == []
    assert defn.enabled is True


def test_plugin_definition_from_dict_full():
    defn = PluginDefinition.from_dict({
        "name": "my_plugin",
        "module": "scripts.check",
        "function": "run",
        "description": "desc",
        "hooks": ["pre_health"],
        "enabled": False,
    })
    assert defn.name == "my_plugin"
    assert defn.hooks == ["pre_health"]
    assert defn.enabled is False


def test_plugin_definition_to_dict_roundtrip():
    defn = PluginDefinition(name="x", module="m", function="f", hooks=["pre_run"])
    d = defn.to_dict()
    assert d["name"] == "x"
    assert d["hooks"] == ["pre_run"]


# ---------------------------------------------------------------------------
# load_plugin_definitions
# ---------------------------------------------------------------------------


def test_load_plugin_definitions_no_toml(tmp_path):
    result = load_plugin_definitions(tmp_path)
    assert result == []


def test_load_plugin_definitions_with_plugins(tmp_path):
    toml_content = """
[thresholds]
health_score_min = 60.0

[[plugins]]
name = "test_plugin"
module = "scripts.check"
function = "run"
hooks = ["pre_health"]
enabled = true
"""
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli  # type: ignore
        except ImportError:
            pytest.skip("tomllib/tomli not available")

    result = load_plugin_definitions(tmp_path)
    assert len(result) == 1
    assert result[0].name == "test_plugin"
    assert result[0].hooks == ["pre_health"]


def test_load_plugin_definitions_empty_plugins_section(tmp_path):
    toml_content = "[thresholds]\nhealth_score_min = 60.0\n"
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli  # type: ignore
        except ImportError:
            pytest.skip("tomllib/tomli not available")
    result = load_plugin_definitions(tmp_path)
    assert result == []


# ---------------------------------------------------------------------------
# run_plugins — no plugins registered
# ---------------------------------------------------------------------------


def test_run_plugins_no_toml(tmp_path):
    report = run_plugins("pre_health", repo_root=tmp_path)
    assert isinstance(report, PluginRunReport)
    assert report.plugins_run == 0
    assert report.hook == "pre_health"


def test_run_plugins_disabled_plugin(tmp_path):
    """Disabled plugins should be skipped."""
    toml_content = """
[[plugins]]
name = "disabled_plugin"
module = "nonexistent_module"
function = "run"
hooks = ["pre_health"]
enabled = false
"""
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli
        except ImportError:
            pytest.skip("tomllib/tomli not available")

    report = run_plugins("pre_health", repo_root=tmp_path)
    assert report.skipped == 1
    assert report.plugins_run == 0


def test_run_plugins_missing_module(tmp_path):
    """Plugin pointing to non-existent module should produce error result."""
    toml_content = """
[[plugins]]
name = "bad_plugin"
module = "nonexistent.module_xyz"
function = "run"
hooks = ["pre_health"]
enabled = true
"""
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli
        except ImportError:
            pytest.skip("tomllib/tomli not available")

    report = run_plugins("pre_health", repo_root=tmp_path)
    assert report.errors >= 1


def test_run_plugins_hook_not_registered(tmp_path):
    """Plugin with specific hooks shouldn't run on unregistered hook."""
    toml_content = """
[[plugins]]
name = "selective_plugin"
module = "nonexistent.module"
function = "run"
hooks = ["pre_health"]
enabled = true
"""
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli
        except ImportError:
            pytest.skip("tomllib/tomli not available")

    report = run_plugins("post_run", repo_root=tmp_path)
    # Should not run the plugin at all for this hook
    assert report.plugins_run == 0


def test_run_plugins_actual_python_plugin(tmp_path):
    """A real Python plugin file should be loaded and executed."""
    plugin_content = """
def check(ctx):
    return {"status": "ok", "message": "Plugin ran!", "data": {"repo": ctx.get("repo_path")}}
"""
    (tmp_path / "my_plugin.py").write_text(plugin_content)

    toml_content = """
[[plugins]]
name = "real_plugin"
module = "my_plugin"
function = "check"
hooks = ["pre_health"]
enabled = true
"""
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli
        except ImportError:
            pytest.skip("tomllib/tomli not available")

    report = run_plugins("pre_health", repo_root=tmp_path)
    assert report.plugins_run == 1
    assert report.ok == 1
    assert report.results[0].status == "ok"
    assert report.results[0].message == "Plugin ran!"


def test_run_plugins_plugin_returns_warning(tmp_path):
    plugin_content = """
def warn_plugin(ctx):
    return {"status": "warn", "message": "Something looks off", "data": {}}
"""
    (tmp_path / "warn_plugin.py").write_text(plugin_content)
    toml_content = """
[[plugins]]
name = "warn_plugin"
module = "warn_plugin"
function = "warn_plugin"
hooks = ["pre_health"]
enabled = true
"""
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli
        except ImportError:
            pytest.skip("tomllib/tomli not available")

    report = run_plugins("pre_health", repo_root=tmp_path)
    assert report.warnings == 1


def test_run_plugins_plugin_raises_exception(tmp_path):
    plugin_content = """
def explode(ctx):
    raise RuntimeError("Plugin exploded!")
"""
    (tmp_path / "explode_plugin.py").write_text(plugin_content)
    toml_content = """
[[plugins]]
name = "explode"
module = "explode_plugin"
function = "explode"
hooks = ["pre_health"]
enabled = true
"""
    (tmp_path / "nightshift.toml").write_text(toml_content)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli
        except ImportError:
            pytest.skip("tomllib/tomli not available")

    report = run_plugins("pre_health", repo_root=tmp_path)
    assert report.errors == 1
    assert "RuntimeError" in report.results[0].error


# ---------------------------------------------------------------------------
# PluginRunReport.to_markdown
# ---------------------------------------------------------------------------


def test_plugin_run_report_to_markdown():
    report = PluginRunReport(hook="pre_health", plugins_run=2, ok=1, warnings=1)
    report.results = [
        PluginResult(plugin_name="p1", hook="pre_health", status="ok", message="All good"),
        PluginResult(plugin_name="p2", hook="pre_health", status="warn", message="Check this"),
    ]
    md = report.to_markdown()
    assert "pre_health" in md
    assert "p1" in md
    assert "p2" in md
    assert "All good" in md


# ---------------------------------------------------------------------------
# list_plugins
# ---------------------------------------------------------------------------


def test_list_plugins_no_toml(tmp_path):
    result = list_plugins(tmp_path)
    assert "No plugins" in result


def test_example_toml_snippet_is_valid_string():
    assert isinstance(EXAMPLE_TOML_SNIPPET, str)
    assert "[[plugins]]" in EXAMPLE_TOML_SNIPPET
    assert "hooks" in EXAMPLE_TOML_SNIPPET
