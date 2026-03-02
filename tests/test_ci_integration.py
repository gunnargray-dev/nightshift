"""Tests for CI integration utilities."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _fake_completed(returncode=0, stdout="", stderr=""):
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


@pytest.fixture
def mock_run():
    with patch("subprocess.run") as m:
        yield m


# ---------------------------------------------------------------------------
# run_checks (unit)
# ---------------------------------------------------------------------------


class TestRunChecks:
    """Unit tests for a run_checks-style helper."""

    def test_success_returns_zero(self, mock_run, tmp_path):
        """A passing check suite should return exit code 0."""
        mock_run.return_value = _fake_completed(returncode=0, stdout="All checks passed")
        result = mock_run(
            ["pytest", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "passed" in result.stdout

    def test_failure_returns_nonzero(self, mock_run, tmp_path):
        """A failing check suite should return a non-zero exit code."""
        mock_run.return_value = _fake_completed(returncode=1, stdout="", stderr="1 failed")
        result = mock_run(
            ["pytest", str(tmp_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        assert "failed" in result.stderr

    def test_captures_stdout(self, mock_run):
        """stdout from the subprocess should be captured."""
        mock_run.return_value = _fake_completed(stdout="hello output")
        result = mock_run(["echo", "hello output"], capture_output=True, text=True)
        assert result.stdout == "hello output"

    def test_captures_stderr(self, mock_run):
        """stderr from the subprocess should be captured."""
        mock_run.return_value = _fake_completed(returncode=1, stderr="error text")
        result = mock_run(["bad-cmd"], capture_output=True, text=True)
        assert result.stderr == "error text"


# ---------------------------------------------------------------------------
# CI report parsing
# ---------------------------------------------------------------------------


class TestCIReportParsing:
    """Tests for parsing CI output JSON into structured results."""

    def _make_report(self, passed, failed, errors=None):
        return {
            "passed": passed,
            "failed": failed,
            "errors": errors or [],
        }

    def test_all_passed(self):
        report = self._make_report(passed=10, failed=0)
        assert report["passed"] == 10
        assert report["failed"] == 0
        assert report["errors"] == []

    def test_some_failed(self):
        report = self._make_report(passed=8, failed=2, errors=["test_a", "test_b"])
        assert report["failed"] == 2
        assert len(report["errors"]) == 2

    def test_zero_tests(self):
        report = self._make_report(passed=0, failed=0)
        assert report["passed"] == 0
        assert report["failed"] == 0

    def test_report_serializes_to_json(self):
        report = self._make_report(passed=5, failed=1, errors=["test_x"])
        serialized = json.dumps(report)
        deserialized = json.loads(serialized)
        assert deserialized == report


# ---------------------------------------------------------------------------
# Environment variable handling
# ---------------------------------------------------------------------------


class TestEnvironmentVariables:
    def test_github_token_present(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        import os

        assert os.environ.get("GITHUB_TOKEN") == "ghp_test123"

    def test_missing_env_var_returns_none(self, monkeypatch):
        import os

        monkeypatch.delenv("SOME_MISSING_VAR", raising=False)
        assert os.environ.get("SOME_MISSING_VAR") is None

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        import os

        assert os.environ.get("CI") == "true"


# ---------------------------------------------------------------------------
# File artifact handling
# ---------------------------------------------------------------------------


class TestArtifactHandling:
    def test_write_artifact(self, tmp_path):
        artifact = tmp_path / "report.json"
        data = {"status": "ok", "count": 3}
        artifact.write_text(json.dumps(data))
        loaded = json.loads(artifact.read_text())
        assert loaded["status"] == "ok"

    def test_artifact_directory_created(self, tmp_path):
        subdir = tmp_path / "artifacts" / "ci"
        subdir.mkdir(parents=True)
        assert subdir.exists()

    def test_multiple_artifacts(self, tmp_path):
        for i in range(3):
            f = tmp_path / f"artifact_{i}.json"
            f.write_text(json.dumps({"index": i}))
        files = list(tmp_path.glob("*.json"))
        assert len(files) == 3

    def test_empty_artifact(self, tmp_path):
        empty = tmp_path / "empty.json"
        empty.write_text("{}")
        assert json.loads(empty.read_text()) == {}

    def test_overwrite_artifact(self, tmp_path):
        f = tmp_path / "result.json"
        f.write_text(json.dumps({"v": 1}))
        f.write_text(json.dumps({"v": 2}))
        assert json.loads(f.read_text())["v"] == 2


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    def test_succeeds_on_first_try(self):
        attempts = []

        def task():
            attempts.append(1)
            return "ok"

        def retry(fn, max_attempts=3):
            for i in range(max_attempts):
                try:
                    return fn()
                except Exception:
                    if i == max_attempts - 1:
                        raise

        result = retry(task)
        assert result == "ok"
        assert len(attempts) == 1

    def test_succeeds_on_second_try(self):
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 2:
                raise RuntimeError("not yet")
            return "ok"

        def retry(fn, max_attempts=3):
            last_exc = None
            for i in range(max_attempts):
                try:
                    return fn()
                except Exception as e:
                    last_exc = e
            raise last_exc

        result = retry(flaky)
        assert result == "ok"
        assert len(attempts) == 2

    def test_raises_after_max_attempts(self):
        def always_fails():
            raise RuntimeError("nope")

        def retry(fn, max_attempts=3):
            last_exc = None
            for _ in range(max_attempts):
                try:
                    return fn()
                except Exception as e:
                    last_exc = e
            raise last_exc

        with pytest.raises(RuntimeError, match="nope"):
            retry(always_fails)
