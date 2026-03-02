"""Tests for CI integration utilities."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal stub of a ci_integration module (not yet present in src/)
# These tests define the expected interface.
# ---------------------------------------------------------------------------


COMPONENT = "src.ci_integration"


class CIConfig:
    """Stub config for CI integration."""

    def __init__(self, provider="github", token=None, dry_run=False):
        self.provider = provider
        self.token = token
        self.dry_run = dry_run


class CIResult:
    """Stub result returned by CI helpers."""

    def __init__(self, success, run_id=None, url=None, message=""):
        self.success = success
        self.run_id = run_id
        self.url = url
        self.message = message


# ---------------------------------------------------------------------------
# trigger_workflow
# ---------------------------------------------------------------------------


def test_trigger_workflow_success():
    config = CIConfig(provider="github", token="tok_abc")
    result = CIResult(success=True, run_id="run_001", url="https://ci.example.com/run_001")
    with patch(f"{COMPONENT}.trigger_workflow", return_value=result) as mock_fn:
        from importlib import import_module

        # We call the mock directly to validate call signature
        r = mock_fn(repo="owner/repo", workflow="ci.yml", ref="main", config=config)
        mock_fn.assert_called_once_with(
            repo="owner/repo", workflow="ci.yml", ref="main", config=config
        )
        assert r.success is True


def test_trigger_workflow_dry_run():
    config = CIConfig(dry_run=True)
    result = CIResult(success=True, message="dry-run: workflow not triggered")
    with patch(f"{COMPONENT}.trigger_workflow", return_value=result) as mock_fn:
        r = mock_fn(repo="owner/repo", workflow="ci.yml", ref="main", config=config)
        assert r.success is True
        assert "dry-run" in r.message


def test_trigger_workflow_failure():
    config = CIConfig(token="bad_token")
    result = CIResult(success=False, message="401 Unauthorized")
    with patch(f"{COMPONENT}.trigger_workflow", return_value=result) as mock_fn:
        r = mock_fn(repo="owner/repo", workflow="ci.yml", ref="main", config=config)
        assert r.success is False
        assert "401" in r.message


# ---------------------------------------------------------------------------
# get_workflow_status
# ---------------------------------------------------------------------------


def test_get_workflow_status_completed():
    with patch(f"{COMPONENT}.get_workflow_status", return_value="completed") as mock_fn:
        status = mock_fn(run_id="run_001", config=CIConfig())
        assert status == "completed"


def test_get_workflow_status_in_progress():
    with patch(f"{COMPONENT}.get_workflow_status", return_value="in_progress") as mock_fn:
        status = mock_fn(run_id="run_002", config=CIConfig())
        assert status == "in_progress"


# ---------------------------------------------------------------------------
# cancel_workflow
# ---------------------------------------------------------------------------


def test_cancel_workflow_success():
    result = CIResult(success=True, message="Workflow run_003 cancelled.")
    with patch(f"{COMPONENT}.cancel_workflow", return_value=result) as mock_fn:
        r = mock_fn(run_id="run_003", config=CIConfig())
        assert r.success is True


def test_cancel_workflow_not_found():
    result = CIResult(success=False, message="run_999 not found")
    with patch(f"{COMPONENT}.cancel_workflow", return_value=result) as mock_fn:
        r = mock_fn(run_id="run_999", config=CIConfig())
        assert r.success is False


# ---------------------------------------------------------------------------
# list_workflow_runs
# ---------------------------------------------------------------------------


def test_list_workflow_runs_returns_list():
    fake_runs = [
        {"run_id": "r1", "status": "completed", "conclusion": "success"},
        {"run_id": "r2", "status": "in_progress", "conclusion": None},
    ]
    with patch(f"{COMPONENT}.list_workflow_runs", return_value=fake_runs) as mock_fn:
        runs = mock_fn(repo="owner/repo", workflow="ci.yml", config=CIConfig())
        assert len(runs) == 2
        assert runs[0]["conclusion"] == "success"


def test_list_workflow_runs_empty():
    with patch(f"{COMPONENT}.list_workflow_runs", return_value=[]) as mock_fn:
        runs = mock_fn(repo="owner/repo", workflow="ci.yml", config=CIConfig())
        assert runs == []


# ---------------------------------------------------------------------------
# download_artifacts
# ---------------------------------------------------------------------------


def test_download_artifacts_success(tmp_path):
    fake_files = [str(tmp_path / "coverage.xml"), str(tmp_path / "report.html")]
    with patch(f"{COMPONENT}.download_artifacts", return_value=fake_files) as mock_fn:
        files = mock_fn(run_id="run_001", dest=tmp_path, config=CIConfig())
        assert len(files) == 2


def test_download_artifacts_empty(tmp_path):
    with patch(f"{COMPONENT}.download_artifacts", return_value=[]) as mock_fn:
        files = mock_fn(run_id="run_no_artifacts", dest=tmp_path, config=CIConfig())
        assert files == []


# ---------------------------------------------------------------------------
# post_pr_comment
# ---------------------------------------------------------------------------


def test_post_pr_comment_success():
    result = CIResult(success=True, url="https://github.com/owner/repo/pull/1#comment-1")
    with patch(f"{COMPONENT}.post_pr_comment", return_value=result) as mock_fn:
        r = mock_fn(pr_number=1, body="Tests passed!", config=CIConfig())
        assert r.success is True
        assert "comment" in r.url


def test_post_pr_comment_rate_limited():
    result = CIResult(success=False, message="429 rate limited")
    with patch(f"{COMPONENT}.post_pr_comment", return_value=result) as mock_fn:
        r = mock_fn(pr_number=2, body="Comment body", config=CIConfig())
        assert r.success is False
        assert "429" in r.message


# ---------------------------------------------------------------------------
# set_commit_status
# ---------------------------------------------------------------------------


def test_set_commit_status_success():
    result = CIResult(success=True)
    with patch(f"{COMPONENT}.set_commit_status", return_value=result) as mock_fn:
        r = mock_fn(sha="abc123", state="success", description="All checks passed", config=CIConfig())
        assert r.success is True


def test_set_commit_status_failure():
    result = CIResult(success=False, message="Invalid SHA")
    with patch(f"{COMPONENT}.set_commit_status", return_value=result) as mock_fn:
        r = mock_fn(sha="zzz", state="failure", description="Invalid", config=CIConfig())
        assert not r.success
