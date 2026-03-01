"""Tests for src/ci_integration.py — Awake CI pipeline integration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_ci_config(tmp_path: Path) -> Path:
    """Write a minimal .awake_ci.json config file."""
    config = {
        "project": "Awake",
        "sessions_dir": "reports",
        "health_threshold": 70,
        "notify_on_regression": True,
        "export_formats": ["json", "markdown"],
    }
    config_path = tmp_path / ".awake_ci.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


# ---------------------------------------------------------------------------
# Unit tests — CIConfig
# ---------------------------------------------------------------------------


def test_ci_config_fields():
    """CIConfig stores all required fields."""
    from src.ci_integration import CIConfig

    cfg = CIConfig(
        project="Awake",
        sessions_dir="reports",
        health_threshold=70,
        notify_on_regression=True,
        export_formats=["json"],
    )
    assert cfg.project == "Awake"
    assert cfg.health_threshold == 70
    assert cfg.notify_on_regression is True


def test_ci_config_export_formats():
    """CIConfig accepts a list of export formats."""
    from src.ci_integration import CIConfig

    cfg = CIConfig(
        project="Awake",
        sessions_dir="reports",
        health_threshold=60,
        notify_on_regression=False,
        export_formats=["json", "markdown", "html"],
    )
    assert "markdown" in cfg.export_formats


# ---------------------------------------------------------------------------
# Unit tests — load_ci_config
# ---------------------------------------------------------------------------


def test_load_ci_config_reads_file(tmp_path):
    """load_ci_config parses a valid config file."""
    from src.ci_integration import load_ci_config

    cfg_path = _make_ci_config(tmp_path)
    cfg = load_ci_config(cfg_path)
    assert cfg.project == "Awake"
    assert cfg.health_threshold == 70


def test_load_ci_config_missing_file(tmp_path):
    """load_ci_config raises FileNotFoundError for missing file."""
    from src.ci_integration import load_ci_config

    with pytest.raises(FileNotFoundError):
        load_ci_config(tmp_path / "missing.json")


def test_load_ci_config_defaults(tmp_path):
    """load_ci_config fills in defaults for optional keys."""
    from src.ci_integration import load_ci_config

    minimal = tmp_path / ".awake_ci.json"
    minimal.write_text(json.dumps({"project": "Awake"}), encoding="utf-8")
    cfg = load_ci_config(minimal)
    assert cfg.health_threshold >= 0


# ---------------------------------------------------------------------------
# Unit tests — PipelineResult
# ---------------------------------------------------------------------------


def test_pipeline_result_passed():
    """PipelineResult.passed is True when health_score meets threshold."""
    from src.ci_integration import PipelineResult

    result = PipelineResult(
        session=1,
        health_score=80.0,
        threshold=70,
        passed=True,
        regressions=[],
        exports=[],
    )
    assert result.passed is True


def test_pipeline_result_failed():
    """PipelineResult.passed is False when health_score is below threshold."""
    from src.ci_integration import PipelineResult

    result = PipelineResult(
        session=2,
        health_score=50.0,
        threshold=70,
        passed=False,
        regressions=["health_score below threshold"],
        exports=[],
    )
    assert result.passed is False
    assert len(result.regressions) == 1


# ---------------------------------------------------------------------------
# Unit tests — run_pipeline
# ---------------------------------------------------------------------------


def test_run_pipeline_passes_above_threshold(tmp_path):
    """run_pipeline returns passed=True when health score is above threshold."""
    from src.ci_integration import run_pipeline, CIConfig

    cfg = CIConfig(
        project="Awake",
        sessions_dir=str(tmp_path),
        health_threshold=60,
        notify_on_regression=False,
        export_formats=[],
    )
    with patch("src.ci_integration.compute_health", return_value=80.0):
        result = run_pipeline(session=1, config=cfg, repo_root=tmp_path)
    assert result.passed is True


def test_run_pipeline_fails_below_threshold(tmp_path):
    """run_pipeline returns passed=False when health score is below threshold."""
    from src.ci_integration import run_pipeline, CIConfig

    cfg = CIConfig(
        project="Awake",
        sessions_dir=str(tmp_path),
        health_threshold=70,
        notify_on_regression=False,
        export_formats=[],
    )
    with patch("src.ci_integration.compute_health", return_value=50.0):
        result = run_pipeline(session=1, config=cfg, repo_root=tmp_path)
    assert result.passed is False


def test_run_pipeline_records_regressions(tmp_path):
    """run_pipeline populates regressions list on failure."""
    from src.ci_integration import run_pipeline, CIConfig

    cfg = CIConfig(
        project="Awake",
        sessions_dir=str(tmp_path),
        health_threshold=75,
        notify_on_regression=True,
        export_formats=[],
    )
    with patch("src.ci_integration.compute_health", return_value=40.0):
        result = run_pipeline(session=3, config=cfg, repo_root=tmp_path)
    assert len(result.regressions) > 0


# ---------------------------------------------------------------------------
# Unit tests — export helpers
# ---------------------------------------------------------------------------


def test_export_json_structure(tmp_path):
    """export_json writes a valid JSON file with expected keys."""
    from src.ci_integration import PipelineResult, export_json

    result = PipelineResult(
        session=1,
        health_score=75.0,
        threshold=70,
        passed=True,
        regressions=[],
        exports=[],
    )
    out_path = tmp_path / "result.json"
    export_json(result, out_path)
    data = json.loads(out_path.read_text())
    assert "session" in data
    assert "health_score" in data
    assert "passed" in data


def test_export_markdown_contains_status(tmp_path):
    """export_markdown produces a file mentioning PASSED or FAILED."""
    from src.ci_integration import PipelineResult, export_markdown

    result = PipelineResult(
        session=2,
        health_score=55.0,
        threshold=70,
        passed=False,
        regressions=["health below threshold"],
        exports=[],
    )
    out_path = tmp_path / "result.md"
    export_markdown(result, out_path)
    text = out_path.read_text()
    assert "FAILED" in text or "failed" in text.lower()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_full_pipeline_integration(tmp_path):
    """End-to-end: load config → run pipeline → check result."""
    from src.ci_integration import load_ci_config, run_pipeline

    cfg_path = _make_ci_config(tmp_path)
    cfg = load_ci_config(cfg_path)
    with patch("src.ci_integration.compute_health", return_value=85.0):
        result = run_pipeline(session=5, config=cfg, repo_root=tmp_path)
    assert result.health_score == 85.0
    assert result.passed is True


def test_pipeline_with_export_json(tmp_path):
    """run_pipeline exports JSON when configured."""
    from src.ci_integration import load_ci_config, run_pipeline

    config = {
        "project": "Awake",
        "sessions_dir": str(tmp_path),
        "health_threshold": 60,
        "notify_on_regression": False,
        "export_formats": ["json"],
    }
    cfg_path = tmp_path / ".awake_ci.json"
    cfg_path.write_text(json.dumps(config), encoding="utf-8")
    cfg = load_ci_config(cfg_path)
    with patch("src.ci_integration.compute_health", return_value=70.0):
        result = run_pipeline(session=1, config=cfg, repo_root=tmp_path)
    assert result.passed is True


def test_pipeline_notification_on_regression(tmp_path):
    """run_pipeline triggers notification when regression is detected."""
    from src.ci_integration import run_pipeline, CIConfig

    cfg = CIConfig(
        project="Awake",
        sessions_dir=str(tmp_path),
        health_threshold=80,
        notify_on_regression=True,
        export_formats=[],
    )
    with patch("src.ci_integration.compute_health", return_value=30.0), \
         patch("src.ci_integration.send_notification") as mock_notify:
        result = run_pipeline(session=2, config=cfg, repo_root=tmp_path)
    assert result.passed is False
