"""Tests for src/cli.py — the unified Nightshift CLI entry point."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cli import build_parser, main, _print_header, _print_ok, _print_warn, _print_info, REPO_ROOT


# ---------------------------------------------------------------------------
# Parser tests
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


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    """Tests for internal print helpers."""

    def test_print_header_does_not_raise(self, capsys):
        _print_header("Test Title")
        out = capsys.readouterr().out
        assert "Test Title" in out
        assert "Nightshift" in out

    def test_print_ok(self, capsys):
        _print_ok("all good")
        out = capsys.readouterr().out
        assert "all good" in out

    def test_print_warn(self, capsys):
        _print_warn("watch out")
        out = capsys.readouterr().out
        assert "watch out" in out

    def test_print_info(self, capsys):
        _print_info("some info")
        out = capsys.readouterr().out
        assert "some info" in out


# ---------------------------------------------------------------------------
# main() integration tests (with mocked module calls)
# ---------------------------------------------------------------------------


class TestMainHealth:
    """Integration tests for `nightshift health`."""

    def test_health_calls_generate_report(self, tmp_path):
        mock_report = MagicMock()
        mock_report.to_markdown.return_value = "# Health\n"
        mock_report.overall_health_score = 95.0
        mock_report.to_dict.return_value = {"score": 95}

        with patch("src.cli.cmd_health") as mock_cmd:
            mock_cmd.return_value = 0
            result = main(["health"])
            assert mock_cmd.called or result == 0

    def test_health_json_output(self, tmp_path, capsys):
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"overall_health_score": 90.0, "files": []}
        mock_report.overall_health_score = 90.0

        with patch("src.health.generate_health_report", return_value=mock_report):
            result = main(["--repo", str(tmp_path), "health", "--json"])
        captured = capsys.readouterr()
        assert result == 0
        json_start = captured.out.find("{")
        assert json_start != -1, "No JSON found in output"
        data = json.loads(captured.out[json_start:])
        assert "overall_health_score" in data


class TestMainStats:
    """Integration tests for `nightshift stats`."""

    def test_stats_renders_table(self, tmp_path, capsys):
        mock_stats = MagicMock()
        mock_stats.readme_table.return_value = "| Metric | Count |\n|--------|-------|\n| Nights active | 3 |"
        mock_stats.sessions = []
        mock_stats.to_dict.return_value = {}

        with patch("src.stats.compute_stats", return_value=mock_stats):
            result = main(["--repo", str(tmp_path), "stats"])
        assert result == 0
        out = capsys.readouterr().out
        assert "Metric" in out or "nights" in out.lower()

    def test_stats_json_flag(self, tmp_path, capsys):
        mock_stats = MagicMock()
        mock_stats.to_dict.return_value = {"nights_active": 3, "total_prs": 9}
        mock_stats.sessions = []

        with patch("src.stats.compute_stats", return_value=mock_stats):
            result = main(["--repo", str(tmp_path), "stats", "--json"])
        assert result == 0
        out = capsys.readouterr().out
        json_start = out.find("{")
        assert json_start != -1, "No JSON found in output"
        data = json.loads(out[json_start:])
        assert "nights_active" in data


class TestMainChangelog:
    """Integration tests for `nightshift changelog`."""

    def test_changelog_prints_markdown(self, tmp_path, capsys):
        mock_cl = MagicMock()
        mock_cl.to_markdown.return_value = "# Changelog\n"
        mock_cl.to_dict.return_value = {}

        with patch("src.changelog.generate_changelog", return_value=mock_cl):
            result = main(["--repo", str(tmp_path), "changelog"])
        assert result == 0

    def test_changelog_write_saves_file(self, tmp_path):
        mock_cl = MagicMock()
        mock_cl.to_markdown.return_value = "# Changelog\n"

        with patch("src.changelog.generate_changelog", return_value=mock_cl), \
             patch("src.changelog.save_changelog") as mock_save:
            result = main(["--repo", str(tmp_path), "changelog", "--write"])
        assert result == 0
        mock_save.assert_called_once()


class TestMainCoverage:
    """Integration tests for `nightshift coverage`."""

    def test_coverage_missing_history_returns_1(self, tmp_path):
        result = main(["--repo", str(tmp_path), "coverage"])
        assert result == 1

    def test_coverage_reads_history(self, tmp_path, capsys):
        history_dir = tmp_path / "docs"
        history_dir.mkdir()
        history_file = history_dir / "coverage_history.json"
        history_file.write_text(
            '{"snapshots": [{"session": 1, "timestamp": "2026-02-27", "total_coverage": 85.0, '
            '"files": {}, "lines_covered": 100, "lines_total": 118, "missing_lines": 18}]}',
            encoding="utf-8",
        )

        from src.coverage_tracker import CoverageHistory
        with patch("src.coverage_tracker.CoverageHistory.from_dict") as mock_from:
            mock_hist = MagicMock()
            mock_hist.to_markdown.return_value = "| Session | Coverage |"
            mock_hist.latest.return_value = None
            mock_from.return_value = mock_hist
            result = main(["--repo", str(tmp_path), "coverage"])
        assert result == 0


class TestMainArch:
    """Integration tests for `nightshift arch`."""

    def test_arch_prints_doc(self, tmp_path, capsys):
        with patch("src.arch_generator.generate_architecture_doc", return_value="# Architecture\n"):
            result = main(["--repo", str(tmp_path), "arch"])
        assert result == 0
        out = capsys.readouterr().out
        assert "Architecture" in out

    def test_arch_write_saves_file(self, tmp_path):
        (tmp_path / "docs").mkdir()
        with patch("src.arch_generator.generate_architecture_doc", return_value="# Architecture\n"), \
             patch("src.arch_generator.save_architecture_doc") as mock_save:
            result = main(["--repo", str(tmp_path), "arch", "--write"])
        assert result == 0
        mock_save.assert_called_once()


class TestMainRefactor:
    """Integration tests for `nightshift refactor`."""

    def test_refactor_prints_report(self, tmp_path, capsys):
        mock_engine = MagicMock()
        mock_report = MagicMock()
        mock_report.to_markdown.return_value = "# Refactor Report\n"
        mock_report.to_dict.return_value = {}
        mock_engine.analyze.return_value = mock_report

        with patch("src.refactor.RefactorEngine", return_value=mock_engine):
            result = main(["--repo", str(tmp_path), "refactor"])
        assert result == 0

    def test_refactor_apply_calls_engine(self, tmp_path):
        mock_engine = MagicMock()
        mock_report = MagicMock()
        mock_engine.analyze.return_value = mock_report
        mock_engine.apply_safe_fixes.return_value = 3

        with patch("src.refactor.RefactorEngine", return_value=mock_engine):
            result = main(["--repo", str(tmp_path), "refactor", "--apply"])
        assert result == 0
        mock_engine.apply_safe_fixes.assert_called_once_with(mock_report)


class TestMainRun:
    """Integration tests for `nightshift run` (full pipeline)."""

    def test_run_succeeds_with_mocks(self, tmp_path):
        mock_report = MagicMock()
        mock_report.overall_health_score = 88.0
        mock_report.to_markdown.return_value = ""
        mock_stats = MagicMock()
        mock_stats.nights_active = 4
        mock_stats.total_prs = 13
        mock_cl = MagicMock()
        mock_cl.sections = []
        mock_cl.total_commits = lambda: 0
        with patch("src.health.generate_health_report", return_value=mock_report), \
             patch("src.health.save_health_report"), \
             patch("src.stats.compute_stats", return_value=mock_stats), \
             patch("src.stats.update_readme_stats", return_value="# README"), \
             patch("src.changelog.generate_changelog", return_value=mock_cl), \
             patch("src.changelog.save_changelog"), \
             patch("src.arch_generator.generate_architecture_doc", return_value="# arch"), \
             patch("src.arch_generator.save_architecture_doc"), \
             patch("src.refactor.RefactorEngine"):
            (tmp_path / "README.md").write_text("# test", encoding="utf-8")
            result = main(["--repo", str(tmp_path), "run", "--session", "4"])
        assert result == 0

    def test_run_handles_partial_failures(self, tmp_path):
        with patch("src.health.generate_health_report", side_effect=RuntimeError("health broken")), \
             patch("src.stats.compute_stats", side_effect=RuntimeError("stats broken")), \
             patch("src.changelog.generate_changelog", side_effect=RuntimeError("changelog broken")):
            result = main(["--repo", str(tmp_path), "run"])
        assert result == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_keyboard_interrupt_returns_130(self):
        with patch("src.cli.cmd_health", side_effect=KeyboardInterrupt):
            result = main(["health"])
        assert result == 130

    def test_unknown_exception_returns_1(self, tmp_path):
        with patch("src.health.generate_health_report", side_effect=ValueError("oops")):
            result = main(["--repo", str(tmp_path), "health"])
        assert result == 1

    def test_repo_root_detected(self):
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
                return
        import re
        m = re.search(r'(\{.*\})', captured.out, re.DOTALL)
        assert m is not None, f"No JSON found in output: {captured.out!r}"
        data = json.loads(m.group(1))
        assert "sessions" in data

    def test_timeline_write_creates_file(self, tmp_path):
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
            "# Nightshift Log\n\n## Session 1 — Feb 27, 2026\n\n"
            "- ✅ Something\n",
            encoding="utf-8",
        )
        result = main(["--repo", str(tmp_path), "timeline", "--write"])
        assert result == 0
        assert (tmp_path / "docs" / "timeline.md").exists()


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

    def test_coupling_renders_output(self, tmp_path, capsys):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod_a.py").write_text("def foo(): return 1\n")
        (src / "mod_b.py").write_text("from src.mod_a import foo\ndef bar(): return foo()\n")
        result = main(["--repo", str(tmp_path), "coupling"])
        assert result == 0
        captured = capsys.readouterr()
        assert "mod_a" in captured.out or "Coupling" in captured.out

    def test_coupling_write_creates_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod_a.py").write_text("def foo(): return 1\n")
        result = main(["--repo", str(tmp_path), "coupling", "--write"])
        assert result == 0
        assert (tmp_path / "docs" / "coupling_report.md").exists()


class TestComplexitySubcommand:
    """Tests for nightshift complexity."""

    def test_complexity_parses(self):
        parser = build_parser()
        args = parser.parse_args(["complexity"])
        assert args.command == "complexity"

    def test_complexity_default_session(self):
        parser = build_parser()
        args = parser.parse_args(["complexity"])
        assert args.session == 11

    def test_complexity_custom_session(self):
        parser = build_parser()
        args = parser.parse_args(["complexity", "--session", "7"])
        assert args.session == 7

    def test_complexity_json_flag(self):
        parser = build_parser()
        args = parser.parse_args(["complexity", "--json"])
        assert args.json is True

    def test_complexity_renders_output(self, tmp_path, capsys):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text(
            "def simple(x):\n    return x + 1\n\n"
            "def branchy(x):\n    if x > 0:\n        return x\n    return 0\n"
        )
        result = main(["--repo", str(tmp_path), "complexity"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Complexity" in captured.out or "mod" in captured.out

    def test_complexity_write_creates_file(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def foo(): return 1\n")
        result = main(["--repo", str(tmp_path), "complexity", "--write"])
        assert result == 0
        assert (tmp_path / "docs" / "complexity_report.md").exists()

    def test_complexity_history_updated(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def foo(): return 1\n")
        result = main(["--repo", str(tmp_path), "complexity", "--write"])
        assert result == 0
        history_path = tmp_path / "docs" / "complexity_history.json"
        assert history_path.exists()


class TestExportSubcommand:
    """Tests for nightshift export."""

    def test_export_parses_coupling(self):
        parser = build_parser()
        args = parser.parse_args(["export", "coupling"])
        assert args.command == "export"
        assert args.analysis == "coupling"

    def test_export_parses_complexity(self):
        parser = build_parser()
        args = parser.parse_args(["export", "complexity"])
        assert args.analysis == "complexity"

    def test_export_parses_timeline(self):
        parser = build_parser()
        args = parser.parse_args(["export", "timeline"])
        assert args.analysis == "timeline"

    def test_export_default_formats(self):
        parser = build_parser()
        args = parser.parse_args(["export", "coupling"])
        assert "json" in args.formats

    def test_export_custom_formats(self):
        parser = build_parser()
        args = parser.parse_args(["export", "coupling", "--formats", "json,html"])
        assert args.formats == "json,html"

    def test_export_coupling_creates_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod_a.py").write_text("def foo(): return 1\n")
        result = main([
            "--repo", str(tmp_path),
            "export", "coupling",
            "--output", str(tmp_path / "out"),
        ])
        assert result == 0
        out_dir = tmp_path / "out"
        assert (out_dir / "coupling-report.json").exists()
        assert (out_dir / "coupling-report.html").exists()
        assert (out_dir / "coupling-report.md").exists()

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
