"""Tests for CLI Session 15 subcommands: benchmark, gitstats, badges."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.cli import build_parser, cmd_benchmark, cmd_gitstats, cmd_badges
from src.benchmark import BenchmarkReport, BenchmarkResult
from src.gitstats import GitStatsReport, ContributorStats
from src.badges import BadgeBlock, Badge


class TestParserRegistration:
    def test_benchmark_subcommand_registered(self):
        parser = build_parser()
        args = parser.parse_args(["benchmark", "--json"])
        assert args.command == "benchmark"
        assert args.json is True

    def test_gitstats_subcommand_registered(self):
        parser = build_parser()
        args = parser.parse_args(["gitstats", "--json"])
        assert args.command == "gitstats"
        assert args.json is True

    def test_badges_subcommand_registered(self):
        parser = build_parser()
        args = parser.parse_args(["badges", "--json"])
        assert args.command == "badges"
        assert args.json is True

    def test_benchmark_write_flag(self):
        parser = build_parser()
        args = parser.parse_args(["benchmark", "--write"])
        assert args.write is True

    def test_benchmark_no_persist_flag(self):
        parser = build_parser()
        args = parser.parse_args(["benchmark", "--no-persist"])
        assert args.no_persist is True

    def test_benchmark_session_flag(self):
        parser = build_parser()
        args = parser.parse_args(["benchmark", "--session", "15"])
        assert args.session == 15

    def test_gitstats_write_flag(self):
        parser = build_parser()
        args = parser.parse_args(["gitstats", "--write"])
        assert args.write is True

    def test_badges_inject_flag(self):
        parser = build_parser()
        args = parser.parse_args(["badges", "--inject"])
        assert args.inject is True

    def test_badges_write_flag(self):
        parser = build_parser()
        args = parser.parse_args(["badges", "--write"])
        assert args.write is True


def _make_benchmark_args(json=False, write=False, no_persist=False, session=15):
    args = MagicMock()
    args.json = json
    args.write = write
    args.no_persist = no_persist
    args.session = session
    args.repo = None
    return args


class TestCmdBenchmark:
    def test_json_output(self, tmp_path, capsys):
        report = BenchmarkReport(
            results=[BenchmarkResult(module="health", elapsed_ms=100.0, status="ok")],
            total_ms=100.0, session=15,
        )
        with patch("src.benchmark.run_benchmarks", return_value=report):
            args = _make_benchmark_args(json=True)
            rc = cmd_benchmark(args)
        assert rc == 0
        captured = capsys.readouterr()
        out = captured.out
        json_start = next((i for i, c in enumerate(out) if c in ('{', '[')), None)
        assert json_start is not None
        data = json.loads(out[json_start:])
        assert data["session"] == 15

    def test_write_output(self, tmp_path, capsys):
        report = BenchmarkReport(results=[], total_ms=0.0, session=15)
        with patch("src.benchmark.run_benchmarks", return_value=report), \
             patch("src.benchmark.save_benchmark_report") as mock_save, \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_benchmark_args(write=True)
            rc = cmd_benchmark(args)
        assert rc == 0

    def test_default_markdown_output(self, tmp_path, capsys):
        report = BenchmarkReport(results=[], total_ms=0.0, session=15)
        with patch("src.benchmark.run_benchmarks", return_value=report), \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_benchmark_args()
            rc = cmd_benchmark(args)
        assert rc == 0
        captured = capsys.readouterr()
        assert "Benchmark" in captured.out


def _make_gitstats_args(json=False, write=False):
    args = MagicMock()
    args.json = json
    args.write = write
    args.repo = None
    return args


class TestCmdGitstats:
    def test_json_output(self, tmp_path, capsys):
        report = GitStatsReport(total_commits=50, active_days=10)
        with patch("src.gitstats.compute_git_stats", return_value=report):
            args = _make_gitstats_args(json=True)
            rc = cmd_gitstats(args)
        assert rc == 0
        captured = capsys.readouterr()
        out = captured.out
        json_start = next((i for i, c in enumerate(out) if c in ('{', '[')), None)
        assert json_start is not None
        data = json.loads(out[json_start:])
        assert data["total_commits"] == 50

    def test_write_output(self, tmp_path, capsys):
        report = GitStatsReport(total_commits=10)
        with patch("src.gitstats.compute_git_stats", return_value=report), \
             patch("src.gitstats.save_git_stats_report") as mock_save, \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_gitstats_args(write=True)
            rc = cmd_gitstats(args)
        assert rc == 0

    def test_default_markdown_output(self, tmp_path, capsys):
        report = GitStatsReport(total_commits=25, active_days=8, churn_rate_per_day=100.0)
        with patch("src.gitstats.compute_git_stats", return_value=report), \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_gitstats_args()
            rc = cmd_gitstats(args)
        assert rc == 0
        captured = capsys.readouterr()
        assert "Git Statistics" in captured.out


def _make_badges_args(json=False, write=False, inject=False):
    args = MagicMock()
    args.json = json
    args.write = write
    args.inject = inject
    args.repo = None
    return args


class TestCmdBadges:
    def test_json_output(self, tmp_path, capsys):
        block = BadgeBlock(
            badges=[Badge(label="sessions", message="15", color="blueviolet")],
            generated_at="2026-02-28",
        )
        with patch("src.badges.generate_badges", return_value=block):
            args = _make_badges_args(json=True)
            rc = cmd_badges(args)
        assert rc == 0
        captured = capsys.readouterr()
        out = captured.out
        json_start = next((i for i, c in enumerate(out) if c in ('{', '[')), None)
        assert json_start is not None
        data = json.loads(out[json_start:])
        assert "badges" in data

    def test_write_output(self, tmp_path, capsys):
        block = BadgeBlock(badges=[Badge(label="tests", message="1500", color="brightgreen")])
        with patch("src.badges.generate_badges", return_value=block), \
             patch("src.badges.save_badges_report") as mock_save, \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_badges_args(write=True)
            rc = cmd_badges(args)
        assert rc == 0

    def test_inject_output(self, tmp_path, capsys):
        block = BadgeBlock(badges=[Badge(label="sessions", message="15", color="blueviolet")])
        with patch("src.badges.generate_badges", return_value=block), \
             patch("src.badges.write_badges_to_readme", return_value=True) as mock_inject, \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_badges_args(inject=True)
            rc = cmd_badges(args)
        assert rc == 0

    def test_inject_failure_warn(self, tmp_path, capsys):
        block = BadgeBlock(badges=[])
        with patch("src.badges.generate_badges", return_value=block), \
             patch("src.badges.write_badges_to_readme", return_value=False), \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_badges_args(inject=True)
            rc = cmd_badges(args)
        assert rc == 0

    def test_default_markdown_output(self, tmp_path, capsys):
        block = BadgeBlock(
            badges=[Badge(label="sessions", message="15", color="blueviolet")],
        )
        with patch("src.badges.generate_badges", return_value=block), \
             patch("src.cli._repo", return_value=tmp_path):
            args = _make_badges_args()
            rc = cmd_badges(args)
        assert rc == 0
        captured = capsys.readouterr()
        assert "img.shields.io" in captured.out
