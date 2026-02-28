"""Tests for src/cli.py — the unified Nightshift CLI entry point."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cli import build_parser, main, _print_header, _print_ok, _print_warn, _print_info, REPO_ROOT


class TestBuildParser:
    def test_parser_returns_parser(self):
        parser = build_parser()
        assert parser is not None

    def test_parser_requires_command(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_health_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["health"])
        assert args.command == "health"

    def test_stats_subcommand(self):
        args = build_parser().parse_args(["stats"])
        assert args.command == "stats"

    def test_diff_subcommand(self):
        args = build_parser().parse_args(["diff"])
        assert args.command == "diff"

    def test_diff_session_default(self):
        args = build_parser().parse_args(["diff"])
        assert args.session == 4

    def test_diff_session_custom(self):
        args = build_parser().parse_args(["diff", "--session", "7"])
        assert args.session == 7

    def test_json_flag(self):
        args = build_parser().parse_args(["health", "--json"])
        assert args.json is True

    def test_changelog_write_flag(self):
        args = build_parser().parse_args(["changelog", "--write"])
        assert args.write is True

    def test_repo_flag(self):
        args = build_parser().parse_args(["--repo", "/tmp/myrepo", "health"])
        assert args.repo == "/tmp/myrepo"

    def test_all_subcommands_registered(self):
        parser = build_parser()
        for cmd in ["health", "stats", "diff", "changelog", "coverage", "score",
                    "arch", "refactor", "replay", "plan", "triage", "depgraph",
                    "todos", "doctor", "run", "timeline", "coupling", "complexity"]:
            args = parser.parse_args([cmd])
            assert args.command == cmd

    def test_run_session_default(self):
        args = build_parser().parse_args(["run"])
        assert args.session == 4

    def test_refactor_apply_flag(self):
        args = build_parser().parse_args(["refactor", "--apply"])
        assert args.apply is True

    def test_todos_session_flag(self):
        args = build_parser().parse_args(["todos", "--session", "5"])
        assert args.session == 5

    def test_todos_threshold_flag(self):
        args = build_parser().parse_args(["todos", "--threshold", "3"])
        assert args.threshold == 3


class TestMain:
    def test_main_health_calls_health_cmd(self, tmp_path):
        mock_report = MagicMock()
        mock_report.to_markdown.return_value = "# Health\n"
        mock_report.overall_health_score = 85.0
        with patch("src.health.generate_health_report", return_value=mock_report):
            result = main(["--repo", str(tmp_path), "health"])
        assert result == 0

    def test_main_health_json_output(self, tmp_path, capsys):
        mock_report = MagicMock()
        mock_report.to_dict.return_value = {"score": 80}
        with patch("src.health.generate_health_report", return_value=mock_report):
            result = main(["--repo", str(tmp_path), "health", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "score" in data

    def test_main_stats_calls_stats_cmd(self, tmp_path):
        mock_stats = MagicMock()
        mock_stats.readme_table.return_value = "| stats |"
        mock_stats.sessions = []
        with patch("src.stats.compute_stats", return_value=mock_stats):
            result = main(["--repo", str(tmp_path), "stats"])
        assert result == 0

    def test_main_changelog_write(self, tmp_path):
        mock_cl = MagicMock()
        with patch("src.changelog.generate_changelog", return_value=mock_cl), \
             patch("src.changelog.save_changelog"):
            result = main(["--repo", str(tmp_path), "changelog", "--write"])
        assert result == 0

    def test_main_coverage_missing_file(self, tmp_path):
        result = main(["--repo", str(tmp_path), "coverage"])
        assert result == 1

    def test_main_score_missing_file(self, tmp_path):
        result = main(["--repo", str(tmp_path), "score"])
        assert result == 1

    def test_main_diff(self, tmp_path):
        mock_diff = MagicMock()
        with patch("src.diff_visualizer.build_session_diff", return_value=mock_diff), \
             patch("src.diff_visualizer.render_session_diff", return_value="# diff\n"):
            result = main(["--repo", str(tmp_path), "diff"])
        assert result == 0


class TestHelpers:
    def test_print_header_outputs(self, capsys):
        _print_header("Test Title")
        captured = capsys.readouterr()
        assert "Test Title" in captured.out

    def test_print_ok_outputs(self, capsys):
        _print_ok("Done!")
        assert "Done!" in capsys.readouterr().out

    def test_print_warn_outputs(self, capsys):
        _print_warn("Warning!")
        assert "Warning!" in capsys.readouterr().out

    def test_print_info_outputs(self, capsys):
        _print_info("Info message")
        assert "Info message" in capsys.readouterr().out


class TestReplaySubcommand:
    def test_replay_parses_session(self):
        args = build_parser().parse_args(["replay", "--session", "5"])
        assert args.session == 5

    def test_replay_parses_no_session(self):
        args = build_parser().parse_args(["replay"])
        assert args.session is None

    def test_replay_all_sessions(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text("# Log\n\n## Session 1 — Feb 1, 2026\n\n- task\n", encoding="utf-8")
        mock_replays = [MagicMock(session_number=1, date="Feb 1", task_count=1, pr_count=0)]
        with patch("src.session_replay.replay_all", return_value=mock_replays):
            result = main(["--repo", str(tmp_path), "replay"])
        assert result == 0

    def test_replay_specific_session_not_found(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text("", encoding="utf-8")
        with patch("src.session_replay.replay", return_value=None):
            result = main(["--repo", str(tmp_path), "replay", "--session", "99"])
        assert result == 1


class TestPlanSubcommand:
    def test_plan_parses_session(self):
        args = build_parser().parse_args(["plan", "--session", "3"])
        assert args.session == 3

    def test_plan_runs(self, tmp_path):
        mock_plan = MagicMock()
        mock_plan.to_markdown.return_value = "# Plan\n"
        mock_brain = MagicMock()
        mock_brain.plan.return_value = mock_plan
        with patch("src.brain.Brain", return_value=mock_brain):
            result = main(["--repo", str(tmp_path), "plan", "--session", "1"])
        assert result == 0


class TestTriageSubcommand:
    def test_triage_missing_file(self, tmp_path):
        result = main(["--repo", str(tmp_path), "triage"])
        assert result == 1

    def test_triage_with_issues_file(self, tmp_path):
        issues_path = tmp_path / "docs" / "issues.json"
        issues_path.parent.mkdir()
        issues_path.write_text("[]", encoding="utf-8")
        with patch("src.issue_triage.load_issues", return_value=[]), \
             patch("src.issue_triage.triage_issues", return_value=[]), \
             patch("src.issue_triage.render_triage_report", return_value="# Triage"):
            result = main(["--repo", str(tmp_path), "triage"])
        assert result == 0


class TestDepgraphSubcommand:
    def test_depgraph_parses(self):
        args = build_parser().parse_args(["depgraph"])
        assert args.command == "depgraph"

    def test_depgraph_runs(self, tmp_path):
        (tmp_path / "src").mkdir()
        mock_graph = MagicMock()
        mock_graph.find_cycles.return_value = []
        with patch("src.dep_graph.build_dep_graph", return_value=mock_graph), \
             patch("src.dep_graph.render_dep_graph", return_value="# graph"):
            result = main(["--repo", str(tmp_path), "depgraph"])
        assert result == 0


class TestTodosSubcommand:
    def test_todos_parses(self):
        args = build_parser().parse_args(["todos"])
        assert args.command == "todos"

    def test_todos_runs(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        with patch("src.todo_hunter.hunt", return_value=[]), \
             patch("src.todo_hunter.render_todo_report", return_value="# todos"):
            result = main(["--repo", str(tmp_path), "todos"])
        assert result == 0


class TestDoctorSubcommand:
    def test_doctor_parses(self):
        args = build_parser().parse_args(["doctor"])
        assert args.command == "doctor"

    def test_doctor_healthy(self, tmp_path):
        mock_report = MagicMock()
        mock_report.grade = "A"
        mock_report.fail_count = 0
        with patch("src.doctor.diagnose", return_value=mock_report), \
             patch("src.doctor.render_report", return_value="# healthy"):
            result = main(["--repo", str(tmp_path), "doctor"])
        assert result == 0

    def test_doctor_critical(self, tmp_path):
        mock_report = MagicMock()
        mock_report.grade = "F"
        mock_report.fail_count = 3
        with patch("src.doctor.diagnose", return_value=mock_report), \
             patch("src.doctor.render_report", return_value="# critical"):
            result = main(["--repo", str(tmp_path), "doctor"])
        assert result == 1

    def test_doctor_write(self, tmp_path):
        mock_report = MagicMock()
        mock_report.grade = "B"
        mock_report.fail_count = 0
        with patch("src.doctor.diagnose", return_value=mock_report), \
             patch("src.doctor.render_report", return_value="# doc"), \
             patch("src.doctor.save_report"):
            result = main(["--repo", str(tmp_path), "doctor", "--write"])
        assert result == 0


class TestRefactorSubcommand:
    def test_refactor_parses(self):
        args = build_parser().parse_args(["refactor"])
        assert args.command == "refactor"

    def test_refactor_runs(self, tmp_path):
        mock_engine = MagicMock()
        mock_report = MagicMock()
        mock_report.to_markdown.return_value = ""
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


class TestTimelineSubcommand:
    def test_timeline_parses(self):
        args = build_parser().parse_args(["timeline"])
        assert args.command == "timeline"

    def test_timeline_json_flag(self):
        args = build_parser().parse_args(["timeline", "--json"])
        assert args.json is True

    def test_timeline_write_flag(self):
        args = build_parser().parse_args(["timeline", "--write"])
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
            "# Nightshift Log\n\n## Session 1 — Feb 27, 2026\n\n- ✅ Something\n",
            encoding="utf-8",
        )
        result = main(["--repo", str(tmp_path), "timeline", "--json"])
        assert result == 0
        captured = capsys.readouterr()
        import re
        m = re.search(r'(\{.*\})', captured.out, re.DOTALL)
        assert m is not None
        data = json.loads(m.group(1))
        assert "sessions" in data

    def test_timeline_write_creates_file(self, tmp_path):
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
            "# Nightshift Log\n\n## Session 1 — Feb 27, 2026\n\n- ✅ Something\n",
            encoding="utf-8",
        )
        result = main(["--repo", str(tmp_path), "timeline", "--write"])
        assert result == 0
        assert (tmp_path / "docs" / "timeline.md").exists()


class TestCouplingSubcommand:
    def test_coupling_parses(self):
        args = build_parser().parse_args(["coupling"])
        assert args.command == "coupling"

    def test_coupling_json_flag(self):
        args = build_parser().parse_args(["coupling", "--json"])
        assert args.json is True

    def test_coupling_write_flag(self):
        args = build_parser().parse_args(["coupling", "--write"])
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
    def test_complexity_parses(self):
        args = build_parser().parse_args(["complexity"])
        assert args.command == "complexity"

    def test_complexity_default_session(self):
        args = build_parser().parse_args(["complexity"])
        assert args.session == 11

    def test_complexity_custom_session(self):
        args = build_parser().parse_args(["complexity", "--session", "7"])
        assert args.session == 7

    def test_complexity_json_flag(self):
        args = build_parser().parse_args(["complexity", "--json"])
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
    def test_export_parses_coupling(self):
        args = build_parser().parse_args(["export", "coupling"])
        assert args.command == "export"
        assert args.analysis == "coupling"

    def test_export_parses_complexity(self):
        args = build_parser().parse_args(["export", "complexity"])
        assert args.analysis == "complexity"

    def test_export_parses_timeline(self):
        args = build_parser().parse_args(["export", "timeline"])
        assert args.analysis == "timeline"

    def test_export_default_formats(self):
        args = build_parser().parse_args(["export", "coupling"])
        assert "json" in args.formats

    def test_export_custom_formats(self):
        args = build_parser().parse_args(["export", "coupling", "--formats", "json,html"])
        assert args.formats == "json,html"

    def test_export_coupling_creates_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod_a.py").write_text("def foo(): return 1\n")
        result = main([
            "--repo", str(tmp_path), "export", "coupling",
            "--output", str(tmp_path / "out"),
        ])
        assert result == 0
        out_dir = tmp_path / "out"
        assert (out_dir / "coupling-report.json").exists()
        assert (out_dir / "coupling-report.html").exists()
        assert (out_dir / "coupling-report.md").exists()

    def test_export_timeline_creates_files(self, tmp_path):
        (tmp_path / "NIGHTSHIFT_LOG.md").write_text(
            "# Nightshift Log\n\n## Session 1 — Feb 27, 2026\n\n- ✅ Something → PR #1\n",
            encoding="utf-8",
        )
        result = main([
            "--repo", str(tmp_path), "export", "timeline",
            "--output", str(tmp_path / "out"),
            "--formats", "json",
        ])
        assert result == 0
        assert (tmp_path / "out" / "timeline-report.json").exists()

    def test_export_invalid_analysis_returns_1(self, tmp_path):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["export", "not_real"])
