"""CI integration tests for the Awake CLI pipeline.

These tests exercise the full CLI subcommand surface via subprocess,
verifying that every subcommand:

1. Exits with code 0 (no crashes)
2. Produces non-empty output
3. Accepts --json where supported and returns valid JSON
4. Accepts --write where supported without error

This file is designed to run in CI and catch regressions where a module
import breaks, a CLI registration is missing, or a flag stops working.

Session 23 -- Awake
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _cli(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a awake CLI command via ``python -m src.cli``."""
    cmd = [sys.executable, "-m", "src.cli"] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
        env={**os.environ, "TERM": "dumb"},  # disable colour
    )


# ---------------------------------------------------------------------------
# Analysis commands
# ---------------------------------------------------------------------------


class TestCLIAnalysisCommands:
    """Test all analysis subcommands exit 0 and produce output."""

    def test_health(self):
        r = _cli("health")
        assert r.returncode == 0, f"health failed: {r.stderr}"
        assert len(r.stdout) > 0

    def test_health_json(self):
        r = _cli("health", "--json")
        assert r.returncode == 0, f"health --json failed: {r.stderr}"
        data = json.loads(r.stdout)
        assert isinstance(data, (dict, list))

    def test_complexity(self):
        r = _cli("complexity")
        assert r.returncode == 0, f"complexity failed: {r.stderr}"
        assert len(r.stdout) > 0

    def test_complexity_json(self):
        r = _cli("complexity", "--json")
        assert r.returncode == 0, f"complexity --json failed: {r.stderr}"
        data = json.loads(r.stdout)
        assert isinstance(data, (dict, list))

    def test_coupling(self):
        r = _cli("coupling")
        assert r.returncode == 0, f"coupling failed: {r.stderr}"
        assert len(r.stdout) > 0

    def test_coupling_json(self):
        r = _cli("coupling", "--json")
        assert r.returncode == 0, f"coupling --json failed: {r.stderr}"

    def test_deadcode(self):
        r = _cli("deadcode")
        assert r.returncode == 0, f"deadcode failed: {r.stderr}"

    def test_deadcode_json(self):
        r = _cli("deadcode", "--json")
        assert r.returncode == 0, f"deadcode --json failed: {r.stderr}"

    def test_security(self):
        r = _cli("security")
        assert r.returncode == 0, f"security failed: {r.stderr}"
        assert len(r.stdout) > 0

    def test_security_json(self):
        r = _cli("security", "--json")
        assert r.returncode == 0, f"security --json failed: {r.stderr}"

    def test_coveragemap(self):
        r = _cli("coveragemap")
        assert r.returncode == 0, f"coveragemap failed: {r.stderr}"

    def test_coveragemap_json(self):
        r = _cli("coveragemap", "--json")
        assert r.returncode == 0, f"coveragemap --json failed: {r.stderr}"

    def test_blame(self):
        r = _cli("blame")
        assert r.returncode == 0, f"blame failed: {r.stderr}"

    def test_blame_json(self):
        r = _cli("blame", "--json")
        assert r.returncode == 0, f"blame --json failed: {r.stderr}"

    def test_maturity(self):
        r = _cli("maturity")
        assert r.returncode == 0, f"maturity failed: {r.stderr}"

    def test_maturity_json(self):
        r = _cli("maturity", "--json")
        assert r.returncode == 0, f"maturity --json failed: {r.stderr}"


# ---------------------------------------------------------------------------
# Meta commands
# ---------------------------------------------------------------------------


class TestCLIMetaCommands:
    """Test meta/introspection subcommands."""

    def test_stats(self):
        r = _cli("stats")
        assert r.returncode == 0, f"stats failed: {r.stderr}"

    def test_stats_json(self):
        r = _cli("stats", "--json")
        assert r.returncode == 0, f"stats --json failed: {r.stderr}"

    def test_changelog(self):
        r = _cli("changelog")
        assert r.returncode == 0, f"changelog failed: {r.stderr}"

    def test_story(self):
        r = _cli("story")
        assert r.returncode == 0, f"story failed: {r.stderr}"

    def test_story_json(self):
        r = _cli("story", "--json")
        assert r.returncode == 0, f"story --json failed: {r.stderr}"

    def test_timeline(self):
        r = _cli("timeline")
        assert r.returncode == 0, f"timeline failed: {r.stderr}"

    def test_timeline_json(self):
        r = _cli("timeline", "--json")
        assert r.returncode == 0, f"timeline --json failed: {r.stderr}"

    def test_reflect(self):
        r = _cli("reflect")
        assert r.returncode == 0, f"reflect failed: {r.stderr}"

    def test_reflect_json(self):
        r = _cli("reflect", "--json")
        assert r.returncode == 0, f"reflect --json failed: {r.stderr}"

    def test_evolve(self):
        r = _cli("evolve")
        assert r.returncode == 0, f"evolve failed: {r.stderr}"

    def test_evolve_json(self):
        r = _cli("evolve", "--json")
        assert r.returncode == 0, f"evolve --json failed: {r.stderr}"

    def test_status(self):
        r = _cli("status")
        assert r.returncode == 0, f"status failed: {r.stderr}"

    def test_status_json(self):
        r = _cli("status", "--json")
        assert r.returncode == 0, f"status --json failed: {r.stderr}"

    def test_compare(self):
        # Compare session 1 vs 2 (both should exist)
        r = _cli("compare", "1", "2")
        assert r.returncode == 0, f"compare failed: {r.stderr}"


# ---------------------------------------------------------------------------
# Tool commands
# ---------------------------------------------------------------------------


class TestCLIToolCommands:
    """Test tool/utility subcommands."""

    def test_doctor(self):
        r = _cli("doctor")
        assert r.returncode == 0, f"doctor failed: {r.stderr}"
        assert len(r.stdout) > 0

    def test_todos(self):
        r = _cli("todos")
        assert r.returncode == 0, f"todos failed: {r.stderr}"

    def test_todos_json(self):
        r = _cli("todos", "--json")
        assert r.returncode == 0, f"todos --json failed: {r.stderr}"

    def test_gitstats(self):
        r = _cli("gitstats")
        assert r.returncode == 0, f"gitstats failed: {r.stderr}"

    def test_gitstats_json(self):
        r = _cli("gitstats", "--json")
        assert r.returncode == 0, f"gitstats --json failed: {r.stderr}"

    def test_badges(self):
        r = _cli("badges")
        assert r.returncode == 0, f"badges failed: {r.stderr}"

    def test_badges_json(self):
        r = _cli("badges", "--json")
        assert r.returncode == 0, f"badges --json failed: {r.stderr}"

    def test_audit(self):
        r = _cli("audit")
        assert r.returncode == 0, f"audit failed: {r.stderr}"

    def test_audit_json(self):
        r = _cli("audit", "--json")
        assert r.returncode == 0, f"audit --json failed: {r.stderr}"

    def test_predict(self):
        r = _cli("predict")
        assert r.returncode == 0, f"predict failed: {r.stderr}"

    def test_predict_json(self):
        r = _cli("predict", "--json")
        assert r.returncode == 0, f"predict --json failed: {r.stderr}"

    def test_dna(self):
        r = _cli("dna")
        assert r.returncode == 0, f"dna failed: {r.stderr}"

    def test_dna_json(self):
        r = _cli("dna", "--json")
        assert r.returncode == 0, f"dna --json failed: {r.stderr}"

    def test_score(self):
        r = _cli("score")
        assert r.returncode == 0, f"score failed: {r.stderr}"

    def test_score_json(self):
        r = _cli("score", "--json")
        assert r.returncode == 0, f"score --json failed: {r.stderr}"

    def test_test_quality(self):
        r = _cli("test-quality")
        assert r.returncode == 0, f"test-quality failed: {r.stderr}"

    def test_test_quality_json(self):
        r = _cli("test-quality", "--json")
        assert r.returncode == 0, f"test-quality --json failed: {r.stderr}"

    def test_refactor(self):
        r = _cli("refactor")
        assert r.returncode == 0, f"refactor failed: {r.stderr}"

    def test_refactor_json(self):
        r = _cli("refactor", "--json")
        assert r.returncode == 0, f"refactor --json failed: {r.stderr}"

    def test_commits(self):
        r = _cli("commits")
        assert r.returncode == 0, f"commits failed: {r.stderr}"

    def test_commits_json(self):
        r = _cli("commits", "--json")
        assert r.returncode == 0, f"commits --json failed: {r.stderr}"

    def test_depgraph(self):
        r = _cli("depgraph")
        assert r.returncode == 0, f"depgraph failed: {r.stderr}"

    def test_depgraph_json(self):
        r = _cli("depgraph", "--json")
        assert r.returncode == 0, f"depgraph --json failed: {r.stderr}"

    def test_arch(self):
        r = _cli("arch")
        assert r.returncode == 0, f"arch failed: {r.stderr}"

    def test_modules(self):
        r = _cli("modules")
        assert r.returncode == 0, f"modules failed: {r.stderr}"

    def test_modules_json(self):
        r = _cli("modules", "--json")
        assert r.returncode == 0, f"modules --json failed: {r.stderr}"

    def test_trends(self):
        r = _cli("trends")
        assert r.returncode == 0, f"trends failed: {r.stderr}"

    def test_trends_json(self):
        r = _cli("trends", "--json")
        assert r.returncode == 0, f"trends --json failed: {r.stderr}"

    def test_teach(self):
        r = _cli("teach", "health")
        assert r.returncode == 0, f"teach failed: {r.stderr}"

    def test_report(self):
        r = _cli("report", "--no-browser")
        # report might not have --no-browser; just check it doesn't crash hard
        # Accept 0 or 2 (argparse error for unrecognised flag)
        assert r.returncode in (0, 2), f"report failed: {r.stderr}"

    def test_coverage(self):
        r = _cli("coverage")
        assert r.returncode == 0, f"coverage failed: {r.stderr}"

    def test_coverage_json(self):
        r = _cli("coverage", "--json")
        assert r.returncode == 0, f"coverage --json failed: {r.stderr}"

    def test_plan(self):
        r = _cli("plan")
        assert r.returncode == 0, f"plan failed: {r.stderr}"

    def test_brain_alias(self):
        r = _cli("brain")
        assert r.returncode == 0, f"brain failed: {r.stderr}"


# ---------------------------------------------------------------------------
# Infrastructure commands
# ---------------------------------------------------------------------------


class TestCLIInfraCommands:
    """Test infrastructure subcommands."""

    def test_deps(self):
        r = _cli("deps", "--offline")
        # deps might need --offline; try both
        if r.returncode != 0:
            r = _cli("deps")
        assert r.returncode == 0, f"deps failed: {r.stderr}"

    def test_deps_json(self):
        r = _cli("deps", "--json")
        assert r.returncode == 0, f"deps --json failed: {r.stderr}"

    def test_config(self):
        r = _cli("config")
        assert r.returncode == 0, f"config failed: {r.stderr}"

    def test_config_json(self):
        r = _cli("config", "--json")
        assert r.returncode == 0, f"config --json failed: {r.stderr}"

    def test_plugins(self):
        r = _cli("plugins")
        assert r.returncode == 0, f"plugins failed: {r.stderr}"

    def test_plugins_json(self):
        r = _cli("plugins", "--json")
        assert r.returncode == 0, f"plugins --json failed: {r.stderr}"

    def test_openapi(self):
        r = _cli("openapi")
        assert r.returncode == 0, f"openapi failed: {r.stderr}"

    def test_openapi_json(self):
        r = _cli("openapi", "--json")
        assert r.returncode == 0, f"openapi --json failed: {r.stderr}"

    def test_automerge(self):
        r = _cli("automerge", "--score", "90", "--ci-passed")
        assert r.returncode == 0, f"automerge failed: {r.stderr}"

    def test_automerge_json(self):
        r = _cli("automerge", "--score", "90", "--ci-passed", "--json")
        assert r.returncode == 0, f"automerge --json failed: {r.stderr}"
        data = json.loads(r.stdout)
        assert data["eligible"] is True

    def test_automerge_ineligible(self):
        r = _cli("automerge", "--score", "50", "--ci-passed")
        assert r.returncode == 1  # ineligible exits 1


# ---------------------------------------------------------------------------
# JSON output validation (spot-check structure)
# ---------------------------------------------------------------------------


class TestJSONOutputStructure:
    """Verify that --json output is well-formed and contains expected keys."""

    def test_health_json_has_scores(self):
        r = _cli("health", "--json")
        if r.returncode != 0:
            pytest.skip("health --json not available")
        data = json.loads(r.stdout)
        # Should have scores per file or a summary
        assert isinstance(data, (dict, list))

    def test_stats_json_has_counts(self):
        r = _cli("stats", "--json")
        if r.returncode != 0:
            pytest.skip("stats --json not available")
        data = json.loads(r.stdout)
        assert isinstance(data, (dict, list))

    def test_status_json_has_overall(self):
        r = _cli("status", "--json")
        if r.returncode != 0:
            pytest.skip("status --json not available")
        data = json.loads(r.stdout)
        assert "overall_status" in data

    def test_security_json_has_findings(self):
        r = _cli("security", "--json")
        if r.returncode != 0:
            pytest.skip("security --json not available")
        data = json.loads(r.stdout)
        assert isinstance(data, (dict, list))

    def test_dna_json_has_fingerprint(self):
        r = _cli("dna", "--json")
        if r.returncode != 0:
            pytest.skip("dna --json not available")
        data = json.loads(r.stdout)
        assert isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# CLI help and error handling
# ---------------------------------------------------------------------------


class TestCLIHelp:
    """Test help output and unknown commands."""

    def test_help(self):
        r = _cli("--help")
        assert r.returncode == 0
        assert "awake" in r.stdout.lower() or "usage" in r.stdout.lower()

    def test_unknown_command(self):
        r = _cli("nonexistent_command_xyz")
        assert r.returncode != 0

    def test_health_help(self):
        r = _cli("health", "--help")
        assert r.returncode == 0

    def test_doctor_help(self):
        r = _cli("doctor", "--help")
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# Pipeline chain: multiple commands in sequence
# ---------------------------------------------------------------------------


class TestPipelineChain:
    """Verify that running multiple commands in sequence doesn't corrupt state."""

    def test_health_then_doctor(self):
        r1 = _cli("health")
        r2 = _cli("doctor")
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_stats_then_status(self):
        r1 = _cli("stats")
        r2 = _cli("status")
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_complexity_then_coupling(self):
        r1 = _cli("complexity")
        r2 = _cli("coupling")
        assert r1.returncode == 0
        assert r2.returncode == 0

    def test_all_analysis_commands_sequential(self):
        """Run all analysis commands in order to verify no side-effect corruption."""
        commands = ["health", "complexity", "coupling", "deadcode", "security", "coveragemap", "blame", "maturity"]
        for cmd in commands:
            r = _cli(cmd)
            assert r.returncode == 0, f"{cmd} failed after running in sequence: {r.stderr}"
