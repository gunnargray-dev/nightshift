"""Tests for src/cli.py — the unified Nightshift CLI entry point."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli import REPO_ROOT, build_parser, main


# ---------------------------------------------------------------------------
# Parser construction
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for the argument parser."""

    def test_parser_returns_parser(self):
        parser = build_parser()
        assert parser is not None

    def test_parser_requires_command(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_health_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["health"])
        assert args.command == "health"
        assert args.json is False

    def test_health_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["health", "--json"])
        assert args.json is True

    def test_stats_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["stats"])
        assert args.command == "stats"

    def test_diff_default_session(self):
        parser = build_parser()
        args = parser.parse_args(["diff"])
        assert args.session == 4

    def test_diff_custom_session(self):
        parser = build_parser()
        args = parser.parse_args(["diff", "--session", "2"])
        assert args.session == 2

    def test_changelog_write_flag(self):
        parser = build_parser()
        args = parser.parse_args(["changelog", "--write"])
        assert args.write is True

    def test_coverage_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["coverage"])
        assert args.command == "coverage"

    def test_score_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["score"])
        assert args.command == "score"

    def test_arch_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["arch"])
        assert args.command == "arch"
        assert args.write is False

    def test_arch_write_flag(self):
        parser = build_parser()
        args = parser.parse_args(["arch", "--write"])
        assert args.write is True

    def test_refactor_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["refactor"])
        assert args.command == "refactor"
        assert args.apply is False

    def test_refactor_apply_flag(self):
        parser = build_parser()
        args = parser.parse_args(["refactor", "--apply"])
        assert args.apply is True

    def test_run_subcommand_default_session(self):
        parser = build_parser()
        args = parser.parse_args(["run"])
        assert args.session == 4

    def test_run_custom_session(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--session", "3"])
        assert args.session == 3

    def test_repo_flag_global(self):
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/myrepo", "health"])
        assert args.repo == "/tmp/myrepo"

    def test_all_subcommands_have_func(self):
        """Every subcommand should bind a func callable."""
        parser = build_parser()
        for cmd in ["health", "stats", "diff", "changelog", "coverage", "score", "arch", "refactor", "run"]:
            args = parser.parse_args([cmd])
            assert callable(args.func), f"{cmd} missing func binding"

    def test_dashboard_subcommand_parses(self):
        parser = build_parser()
        args = parser.parse_args(["dashboard"])
        assert args.command == "dashboard"

    def test_dashboard_custom_port(self):
        parser = build_parser()
        args = parser.parse_args(["dashboard", "--port", "9000"])
        assert args.port == 9000

    def test_dashboard_default_port(self):
        parser = build_parser()
        args = parser.parse_args(["dashboard"])
        assert args.port == 8710


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for internal print helpers."""

    def test_print_header_outputs_bar(self, capsys):
        from src.cli import _print_header
        _print_header("Test")
        captured = capsys.readouterr()
        assert "Test" in captured.out
        assert "─" in captured.out

    def test_print_ok(self, capsys):
        from src.cli import _print_ok
        _print_ok("done")
        captured = capsys.readouterr()
        assert "done" in captured.out

    def test_print_warn(self, capsys):
        from src.cli import _print_warn
        _print_warn("caution")
        captured = capsys.readouterr()
        assert "caution" in captured.out

    def test_print_info(self, capsys):
        from src.cli import _print_info
        _print_info("note")
        captured = capsys.readouterr()
        assert "note" in captured.out

    def test_repo_returns_default(self):
        from src.cli import _repo
        assert _repo() == REPO_ROOT

    def test_repo_returns_custom_path(self, tmp_path):
        from src.cli import _repo
        assert _repo(str(tmp_path)) == tmp_path


# ---------------------------------------------------------------------------
# Subcommand: health
# ---------------------------------------------------------------------------


class TestHealthSubcommand:
    """Tests for nightshift health."""

    def test_health_runs(self, tmp_path, capsys):
        """health subcommand should call generate_health_report."""
        mock_report = MagicMock()
        mock_report.to_markdown.return_value = "# Health"
        mock_report.overall_health_score = 85
        with patch("src.health.generate_health_report", return_value=mock_report):
            result = main(["--repo", str(tmp_path), "health"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Health" in captured.out

    def test_health_json(self, tmp_path, capsys):
        """health --json should emit JSON."""
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"score": 90}
        with patch("src.health.generate_health_report", return_value=mock_report):
            result = main(["--repo", str(tmp_path), "health", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        # Extract JSON object from output (header may precede it)
        lines = captured.out.strip().split("\n")
        json_lines = [l for l in lines if l.strip().startswith("{")]
        assert json_lines, f"No JSON found in output: {captured.out!r}"


# ---------------------------------------------------------------------------
# Subcommand: stats
# ---------------------------------------------------------------------------


class TestStatsSubcommand:
    """Tests for nightshift stats."""

    def test_stats_runs(self, tmp_path, capsys):
        mock_stats = MagicMock()
        mock_stats.readme_table.return_value = "| Stat | Value |"
        mock_stats.sessions = [1, 2, 3]
        with patch("src.stats.compute_stats", return_value=mock_stats):
            result = main(["--repo", str(tmp_path), "stats"])
        assert result == 0

    def test_stats_json(self, tmp_path, capsys):
        mock_stats = MagicMock()
        mock_stats.to_dict.return_value = {"nights": 3}
        with patch("src.stats.compute_stats", return_value=mock_stats):
            result = main(["--repo", str(tmp_path), "stats", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        lines = [l for l in captured.out.split("\n") if l.strip().startswith("{")]
        assert lines


# ---------------------------------------------------------------------------
# Subcommand: changelog
# ---------------------------------------------------------------------------


class TestChangelogSubcommand:
    """Tests for nightshift changelog."""

    def test_changelog_runs(self, tmp_path, capsys):
        mock_cl = MagicMock()
        mock_cl.to_markdown.return_value = "## Changelog"
        with patch("src.changelog.generate_changelog", return_value=mock_cl):
            result = main(["--repo", str(tmp_path), "changelog"])
        assert result == 0

    def test_changelog_write(self, tmp_path):
        mock_cl = MagicMock()
        with patch("src.changelog.generate_changelog", return_value=mock_cl), \
             patch("src.changelog.save_changelog") as mock_save:
            result = main(["--repo", str(tmp_path), "changelog", "--write"])
        assert result == 0
        mock_save.assert_called_once()


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


class TestRunSubcommand:
    """Tests for nightshift run (full pipeline)."""

    def test_run_succeeds(self, tmp_path, capsys):
        """Full pipeline should succeed when all modules are mocked."""
        mock_report = MagicMock()
        mock_report.overall_health_score = 80
        mock_stats = MagicMock()
        mock_stats.nights_active = 3
        mock_stats.total_prs = 5
        mock_cl = MagicMock()
        mock_cl.sections = []
        mock_ref = MagicMock()
        mock_ref.total_suggestions = 0
        mock_ref.to_markdown.return_value = ""
        readme = tmp_path / "README.md"
        readme.write_text("# Test\n", encoding="utf-8")
        with patch("src.health.generate_health_report", return_value=mock_report), \
             patch("src.health.save_health_report"), \
             patch("src.stats.compute_stats", return_value=mock_stats), \
             patch("src.stats.update_readme_stats", return_value="# updated"), \
             patch("src.changelog.generate_changelog", return_value=mock_cl), \
             patch("src.changelog.save_changelog"), \
             patch("src.refactor.RefactorEngine", return_value=MagicMock(analyze=lambda: mock_ref)):
            result = main(["--repo", str(tmp_path), "run"])
        assert result == 0

    def test_run_partial_failure_returns_1(self, tmp_path, capsys):
        """Pipeline should complete even if one module fails, returning exit 1."""
        with patch("src.health.generate_health_report", side_effect=RuntimeError("fail")):
            result = main(["--repo", str(tmp_path), "run"])
        assert result == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_keyboard_interrupt_returns_130(self):
        with patch("src.cli.cmd_health", side_effect=KeyboardInterrupt):
            result = main(["health"])
        assert result == 130

    def test_unknown_exception_returns_1(self, tmp_path):
        with patch("src.health.generate_health_report", side_effect=ValueError("oops")):
            result = main(["--repo", str(tmp_path), "health"])
        assert result == 1

    def test_repo_root_detected(self):
        """REPO_ROOT should be a valid path."""
        assert isinstance(REPO_ROOT, Path)



# ---------------------------------------------------------------------------
# New subcommands: timeline, coupling, complexity, export
# ---------------------------------------------------------------------------


class TestTimelineSubcommand:
    """Tests for nightshift timeline."""

    def test_timeline_parses(self):
        parser = build_parser()
        args = parser.parse_args(["timeline"])
        assert args.command == "timeline"

    def test_timeline_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["timeline", "--json"])
        assert args.json is True

    def test_timeline_write_flag(self):
        parser = build_parser()
        args = parser.parse_args(["timeline", "--write"])
        assert args.write is True

    def test_timeline_renders_output(self, tmp_path, capsys):
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
            "# Nightshift Log\n\n## Session 1 — February 27, 2026\n\n"
            "**Operator:** Computer\n\n- ✅ Stats → PR #1 — src/stats.py\n",
            encoding="utf-8",
        )
        result = main(["--repo", str(tmp_path), "timeline"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Session" in captured.out

    def test_timeline_json_output(self, tmp_path, capsys):
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
            "# Nightshift Log\n\n## Session 1 — Feb 27, 2026\n\n"
            "- ✅ Something\n",
            encoding="utf-8",
        )
        result = main(["--repo", str(tmp_path), "timeline", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        for line in captured.out.split("\n"):
            if line.strip().startswith("{"):
                data = json.loads(captured.out[captured.out.index("{"):])
                assert "sessions" in data
                break


class TestCouplingSubcommand:
    """Tests for nightshift coupling."""

    def test_coupling_parses(self):
        parser = build_parser()
        args = parser.parse_args(["coupling"])
        assert args.command == "coupling"

    def test_coupling_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["coupling", "--json"])
        assert args.json is True

    def test_coupling_write_flag(self):
        parser = build_parser()
        args = parser.parse_args(["coupling", "--write"])
        assert args.write is True

    def test_coupling_renders(self, tmp_path, capsys):
        mock_report = MagicMock()
        mock_report.violations = []
        mock_report.to_dict.return_value = {"modules": []}
        with patch("src.coupling.build_coupling_report", return_value=mock_report), \
             patch("src.coupling.render_coupling_report", return_value="## Coupling"):
            result = main(["--repo", str(tmp_path), "coupling"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Coupling" in captured.out


class TestComplexitySubcommand:
    """Tests for nightshift complexity."""

    def test_complexity_parses(self):
        parser = build_parser()
        args = parser.parse_args(["complexity"])
        assert args.command == "complexity"
        assert args.threshold == 10

    def test_complexity_custom_threshold(self):
        parser = build_parser()
        args = parser.parse_args(["complexity", "--threshold", "5"])
        assert args.threshold == 5

    def test_complexity_renders(self, tmp_path, capsys):
        mock_report = MagicMock()
        mock_report.functions = []
        with patch("src.complexity.build_complexity_report", return_value=mock_report), \
             patch("src.complexity.render_complexity_report", return_value="## Complexity"):
            result = main(["--repo", str(tmp_path), "complexity"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Complexity" in captured.out


class TestExportSubcommand:
    """Tests for nightshift export."""

    def test_export_parses(self):
        parser = build_parser()
        args = parser.parse_args(["export"])
        assert args.command == "export"
        assert args.format == "markdown"

    def test_export_json_format(self):
        parser = build_parser()
        args = parser.parse_args(["export", "--format", "json"])
        assert args.format == "json"

    def test_export_html_format(self):
        parser = build_parser()
        args = parser.parse_args(["export", "--format", "html"])
        assert args.format == "html"

    def test_export_invalid_format_raises(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["export", "--format", "pdf"])

    def test_export_renders(self, tmp_path, capsys):
        mock_bundle = MagicMock()
        with patch("src.exporter.build_export_bundle", return_value=mock_bundle), \
             patch("src.exporter.render_export", return_value="# Export"):
            result = main(["--repo", str(tmp_path), "export"])
        assert result == 0

    def test_export_to_file(self, tmp_path):
        mock_bundle = MagicMock()
        out_file = tmp_path / "export.md"
        with patch("src.exporter.build_export_bundle", return_value=mock_bundle), \
             patch("src.exporter.render_export", return_value="# Export"):
            result = main([
                "--repo", str(tmp_path),
                "export",
                "--out", str(out_file),
            ])
        assert result == 0
        assert out_file.exists()
        assert out_file.read_text() == "# Export"

    def test_export_timeline_creates_files(self, tmp_path):
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
            "# Nightshift Log\n\n## Session 1 — Feb 27, 2026\n\n"
            "- ✅ Something → PR #1\n",
            encoding="utf-8",
        )
        result = main([
            "--repo", str(tmp_path),
            "export", "timeline",
            "--output", str(tmp_path / "out"),
            "--formats", "json",
        ])
        assert result == 0
        assert (tmp_path / "out" / "timeline-report.json").exists()

    def test_export_invalid_analysis_returns_1(self, tmp_path):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["export", "not_real"])

