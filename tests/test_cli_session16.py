"""Tests for Session 16 CLI subcommands — audit, semver, init, predict."""

from __future__ import annotations

import json
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(args: list[str]) -> tuple[int, str]:
    """Run nightshift CLI and capture stdout."""
    import io
    from src.cli import build_parser, main

    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        parser = build_parser()
        parsed = parser.parse_args(args)
        rc = parsed.func(parsed)
    except SystemExit as e:
        rc = int(str(e))
    finally:
        sys.stdout = old_stdout
    return rc, captured.getvalue()


# ---------------------------------------------------------------------------
# nightshift audit
# ---------------------------------------------------------------------------

class TestCLIAudit:
    def test_audit_json_output(self, tmp_path):
        mock_report = MagicMock()
        mock_report.to_json.return_value = json.dumps({
            "overall_grade": "B",
            "overall_score": 78.5,
            "overall_status": "healthy",
            "sections": [],
        })
        mock_report.overall_grade = "B"
        mock_report.overall_score = 78.5
        mock_report.overall_status = "healthy"

        with patch("src.audit.run_audit", return_value=mock_report):
            rc, output = _run(["--repo", str(tmp_path), "audit", "--json"])

        assert rc == 0
        parsed = json.loads(output)
        assert parsed["overall_grade"] == "B"

    def test_audit_markdown_output(self, tmp_path):
        mock_report = MagicMock()
        mock_report.to_json.return_value = "{}"
        mock_report.to_markdown.return_value = "# Nightshift Comprehensive Audit\n"
        mock_report.overall_grade = "B"
        mock_report.overall_score = 78.5
        mock_report.overall_status = "healthy"

        with patch("src.audit.run_audit", return_value=mock_report):
            rc, output = _run(["--repo", str(tmp_path), "audit"])

        assert rc == 0
        assert "Audit" in output or "healthy" in output

    def test_audit_write_flag(self, tmp_path):
        mock_report = MagicMock()
        mock_report.to_markdown.return_value = "# Audit\n"
        mock_report.to_json.return_value = "{}"
        mock_report.overall_grade = "A"
        mock_report.overall_score = 92.0
        mock_report.overall_status = "healthy"

        with patch("src.audit.run_audit", return_value=mock_report), \
             patch("src.audit.save_audit_report") as mock_save:
            rc, _ = _run(["--repo", str(tmp_path), "audit", "--write"])

        assert rc == 0
        mock_save.assert_called_once()

    def test_audit_is_registered_in_parser(self):
        from src.cli import build_parser
        parser = build_parser()
        # If 'audit' is not registered, parse_args would raise SystemExit(2)
        try:
            args = parser.parse_args(["audit", "--help"])
        except SystemExit as e:
            # --help exits with 0
            assert str(e) == "0"


# ---------------------------------------------------------------------------
# nightshift semver
# ---------------------------------------------------------------------------

class TestCLISemver:
    def _mock_bump(self):
        bump = MagicMock()
        bump.current_version = "0.1.0"
        bump.next_version = "0.2.0"
        bump.bump_type = "minor"
        bump.to_json.return_value = json.dumps({
            "current_version": "0.1.0",
            "next_version": "0.2.0",
            "bump_type": "minor",
            "commits": [],
        })
        bump.to_markdown.return_value = "# Semantic Version Analysis\n"
        return bump

    def test_semver_json_output(self, tmp_path):
        mock_bump = self._mock_bump()
        with patch("src.semver.analyze_semver", return_value=mock_bump):
            rc, output = _run(["--repo", str(tmp_path), "semver", "--json"])

        assert rc == 0
        parsed = json.loads(output)
        assert parsed["bump_type"] == "minor"

    def test_semver_markdown_output(self, tmp_path):
        mock_bump = self._mock_bump()
        with patch("src.semver.analyze_semver", return_value=mock_bump):
            rc, output = _run(["--repo", str(tmp_path), "semver"])

        assert rc == 0

    def test_semver_apply_flag(self, tmp_path):
        mock_bump = self._mock_bump()
        with patch("src.semver.analyze_semver", return_value=mock_bump), \
             patch("src.semver.apply_version_bump", return_value=True) as mock_apply:
            rc, _ = _run(["--repo", str(tmp_path), "semver", "--apply"])

        assert rc == 0
        mock_apply.assert_called_once()

    def test_semver_apply_with_changelog(self, tmp_path):
        mock_bump = self._mock_bump()
        with patch("src.semver.analyze_semver", return_value=mock_bump), \
             patch("src.semver.apply_version_bump", return_value=True), \
             patch("src.semver.prepend_changelog_entry") as mock_prepend:
            rc, _ = _run(["--repo", str(tmp_path), "semver", "--apply", "--changelog"])

        assert rc == 0
        mock_prepend.assert_called_once()

    def test_semver_is_registered_in_parser(self):
        from src.cli import build_parser
        parser = build_parser()
        try:
            parser.parse_args(["semver", "--help"])
        except SystemExit as e:
            assert str(e) == "0"


# ---------------------------------------------------------------------------
# nightshift init
# ---------------------------------------------------------------------------

class TestCLIInit:
    def _mock_result(self, created=None, skipped=None):
        from src.init_cmd import InitResult
        r = InitResult(repo_path="/tmp/test")
        r.created = created or ["nightshift.toml", "CHANGELOG.md"]
        r.skipped = skipped or []
        return r

    def test_init_creates_files(self, tmp_path):
        with patch("src.init_cmd.bootstrap", return_value=self._mock_result()) as mock_boot:
            rc, output = _run(["--repo", str(tmp_path), "init"])

        assert rc == 0
        mock_boot.assert_called_once()

    def test_init_json_output(self, tmp_path):
        mock_result = self._mock_result()
        with patch("src.init_cmd.bootstrap", return_value=mock_result):
            rc, output = _run(["--repo", str(tmp_path), "init", "--json"])

        assert rc == 0
        parsed = json.loads(output)
        assert "created" in parsed
        assert "total_created" in parsed

    def test_init_force_flag(self, tmp_path):
        with patch("src.init_cmd.bootstrap", return_value=self._mock_result()) as mock_boot:
            rc, _ = _run(["--repo", str(tmp_path), "init", "--force"])

        assert rc == 0
        call_kwargs = mock_boot.call_args
        assert call_kwargs[1].get("force") is True or (
            len(call_kwargs[0]) > 1 and call_kwargs[0][1] is True
        )

    def test_init_src_flag(self, tmp_path):
        with patch("src.init_cmd.bootstrap", return_value=self._mock_result()) as mock_boot:
            rc, _ = _run(["--repo", str(tmp_path), "init", "--src"])

        assert rc == 0

    def test_init_is_registered_in_parser(self):
        from src.cli import build_parser
        parser = build_parser()
        try:
            parser.parse_args(["init", "--help"])
        except SystemExit as e:
            assert str(e) == "0"


# ---------------------------------------------------------------------------
# nightshift predict
# ---------------------------------------------------------------------------

class TestCLIPredict:
    def _mock_report(self):
        report = MagicMock()
        report.next_session = 16
        report.session_count = 15
        report.items = []
        report.to_json.return_value = json.dumps({
            "next_session": 16,
            "items": [],
            "signals_used": ["Coverage"],
            "session_count": 15,
        })
        report.to_markdown.return_value = "# Predictive Session Planner\n"
        return report

    def test_predict_json_output(self, tmp_path):
        mock_report = self._mock_report()
        with patch("src.predict.predict_next_session", return_value=mock_report):
            rc, output = _run(["--repo", str(tmp_path), "predict", "--json"])

        assert rc == 0
        parsed = json.loads(output)
        assert parsed["next_session"] == 16

    def test_predict_markdown_output(self, tmp_path):
        mock_report = self._mock_report()
        with patch("src.predict.predict_next_session", return_value=mock_report):
            rc, output = _run(["--repo", str(tmp_path), "predict"])

        assert rc == 0

    def test_predict_write_flag(self, tmp_path):
        mock_report = self._mock_report()
        with patch("src.predict.predict_next_session", return_value=mock_report), \
             patch("src.predict.save_prediction_report") as mock_save:
            rc, _ = _run(["--repo", str(tmp_path), "predict", "--write"])

        assert rc == 0
        mock_save.assert_called_once()

    def test_predict_is_registered_in_parser(self):
        from src.cli import build_parser
        parser = build_parser()
        try:
            parser.parse_args(["predict", "--help"])
        except SystemExit as e:
            assert str(e) == "0"

    def test_total_subcommands_grew(self):
        """Session 16 adds 4 new subcommands — total should be at least 38."""
        from src.cli import build_parser
        parser = build_parser()
        # Count registered subcommands
        subparsers_action = None
        for action in parser._actions:
            if hasattr(action, '_name_parser_map'):
                subparsers_action = action
                break
        if subparsers_action:
            count = len(subparsers_action._name_parser_map)
            assert count >= 38, f"Expected ≥38 subcommands, found {count}"
