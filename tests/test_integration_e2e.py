"""
End-to-end integration tests for the Awake pipeline.

Tests the full flow:  stats → health → brain → (simulate) PR

These tests verify that the core pipeline components work together
and produce coherent output without errors.

Session 18 — Awake
"""

from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any
import pytest


# ---------------------------------------------------------------------------
# Repo root detection
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent

def _src(name: str) -> Path:
    return REPO_ROOT / "src" / name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_python_module(module_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run a Python file as a script and return CompletedProcess."""
    cmd = [sys.executable, str(module_path)] + list(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(REPO_ROOT),
    )


def _import_module(name: str) -> Any:
    """Dynamically import a src module."""
    sys.path.insert(0, str(REPO_ROOT))
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, _src(f"{name}.py"))
    if spec is None or spec.loader is None:
        pytest.skip(f"src/{name}.py not found in repo")
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec so that `from __future__ import
    # annotations` works correctly with dataclasses on Python < 3.10.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


# ---------------------------------------------------------------------------
# Session 18 new modules — basic import and run tests
# ---------------------------------------------------------------------------

class TestReflectModule:
    def test_reflect_module_importable(self):
        reflect = _import_module("reflect")
        assert hasattr(reflect, "generate_reflection")

    def test_reflect_generates_report(self):
        reflect = _import_module("reflect")
        report = reflect.generate_reflection()
        assert report.total_sessions > 0
        assert report.avg_score > 0

    def test_reflect_format_produces_output(self):
        reflect = _import_module("reflect")
        report = reflect.generate_reflection()
        text = reflect.format_reflection(report)
        assert len(text) > 200

    def test_reflect_json_roundtrip(self):
        reflect = _import_module("reflect")
        report = reflect.generate_reflection()
        json_str = reflect.reflect_to_json(report)
        data = json.loads(json_str)
        assert data["total_sessions"] == report.total_sessions


class TestEvolveModule:
    def test_evolve_module_importable(self):
        evolve = _import_module("evolve")
        assert hasattr(evolve, "generate_evolution")

    def test_evolve_generates_report(self):
        evolve = _import_module("evolve")
        report = evolve.generate_evolution()
        assert len(report.proposals) > 0
        assert len(report.gap_areas) > 0

    def test_evolve_tiers_non_empty(self):
        evolve = _import_module("evolve")
        report = evolve.generate_evolution()
        assert len(report.tier1) > 0
        assert len(report.tier2) > 0
        assert len(report.tier3) > 0

    def test_evolve_format_produces_output(self):
        evolve = _import_module("evolve")
        report = evolve.generate_evolution()
        text = evolve.format_evolution(report)
        assert "TIER 1" in text
        assert "GAP ANALYSIS" in text


class TestSessionScorerModule:
    def test_session_scorer_importable(self):
        scorer = _import_module("session_scorer")
        assert hasattr(scorer, "score_session")

    def test_score_session_18(self):
        scorer = _import_module("session_scorer")
        result = scorer.score_session(18, 4, 140, 4, 4, 4.0)
        assert 0 <= result.total <= 100
        assert result.grade in ("A+", "A", "B+", "B", "C", "D", "F")

    def test_score_all_sessions(self):
        scorer = _import_module("session_scorer")
        scores = scorer.score_all_sessions()
        assert len(scores) == len(scorer.SESSION_DATA)


class TestStatusModule:
    def test_status_module_importable(self):
        status = _import_module("status")
        assert hasattr(status, "generate_status")

    def test_status_generates_report(self):
        status = _import_module("status")
        report = status.generate_status(REPO_ROOT)
        assert isinstance(report, status.StatusReport)
        assert report.overall_status in ("GREEN", "YELLOW", "RED")

    def test_status_format(self):
        status = _import_module("status")
        report = status.generate_status(REPO_ROOT)
        text = status.format_status(report)
        assert "AWAKE STATUS" in text

    def test_status_json(self):
        status = _import_module("status")
        report = status.generate_status(REPO_ROOT)
        data = json.loads(status.status_to_json(report))
        assert "session" in data
        assert "overall_status" in data


# ---------------------------------------------------------------------------
# Pipeline integration: reflect → session_scorer consistency
# ---------------------------------------------------------------------------

class TestReflectAndScorerConsistency:
    def test_reflect_and_scorer_agree_on_session_count(self):
        reflect = _import_module("reflect")
        scorer = _import_module("session_scorer")
        reflect_report = reflect.generate_reflection()
        all_scores = scorer.score_all_sessions()
        assert reflect_report.total_sessions == len(all_scores)

    def test_top_sessions_same_in_both(self):
        reflect = _import_module("reflect")
        scorer = _import_module("session_scorer")
        reflect_report = reflect.generate_reflection()
        scorer_scores = scorer.score_all_sessions()

        # Session 17 should rank highly in both
        reflect_top = {s.session for s in reflect_report.top_sessions}
        scorer_top = {s.session for s in sorted(scorer_scores, key=lambda x: x.total, reverse=True)[:3]}

        # There should be overlap in top sessions
        assert len(reflect_top & scorer_top) >= 1


# ---------------------------------------------------------------------------
# Pipeline integration: evolve references real gap areas
# ---------------------------------------------------------------------------

class TestEvolveGapCoverage:
    def test_gap_areas_cover_known_weaknesses(self):
        evolve = _import_module("evolve")
        report = evolve.generate_evolution()
        gap_names = [g.name.lower() for g in report.gap_areas]
        combined = " ".join(gap_names)

        # These are known gaps as of session 18
        assert "multi-repo" in combined or "multi" in combined
        assert "ci" in combined or "integration" in combined

    def test_tier1_all_achievable_next_session(self):
        evolve = _import_module("evolve")
        report = evolve.generate_evolution()
        for p in report.tier1:
            assert p.session_estimate <= 2, (
                f"Tier 1 proposal '{p.title}' estimates {p.session_estimate} sessions — "
                "should be 1–2 for Tier 1"
            )


# ---------------------------------------------------------------------------
# Existing module integration: stats → health chain
# ---------------------------------------------------------------------------

class TestStatsHealthChain:
    def test_stats_module_runs_without_error(self):
        stats_path = _src("stats.py")
        if not stats_path.exists():
            pytest.skip("src/stats.py not found")
        result = _run_python_module(stats_path)
        assert result.returncode == 0, f"stats.py failed: {result.stderr}"

    def test_health_module_runs_without_error(self):
        health_path = _src("health.py")
        if not health_path.exists():
            pytest.skip("src/health.py not found")
        result = _run_python_module(health_path)
        assert result.returncode == 0, f"health.py failed: {result.stderr}"

    def test_brain_module_runs_without_error(self):
        brain_path = _src("brain.py")
        if not brain_path.exists():
            pytest.skip("src/brain.py not found")
        result = _run_python_module(brain_path)
        assert result.returncode == 0, f"brain.py failed: {result.stderr}"

    def test_audit_module_runs_without_error(self):
        audit_path = _src("audit.py")
        if not audit_path.exists():
            pytest.skip("src/audit.py not found")
        result = _run_python_module(audit_path)
        assert result.returncode == 0, f"audit.py failed: {result.stderr}"


# ---------------------------------------------------------------------------
# Error recovery: verify modules degrade gracefully on bad input
# ---------------------------------------------------------------------------

class TestErrorGraceDegradation:
    def test_reflect_handles_missing_log(self, tmp_path):
        reflect = _import_module("reflect")
        # generate_reflection with no log should use seed data without crashing
        report = reflect.generate_reflection(log_path=tmp_path / "nonexistent.md")
        assert report.total_sessions > 0

    def test_status_handles_missing_repo(self, tmp_path):
        status = _import_module("status")
        # Should not crash, should return a report with fallback values
        report = status.generate_status(tmp_path)
        assert isinstance(report, status.StatusReport)
        assert report.overall_status in ("GREEN", "YELLOW", "RED")

    def test_session_scorer_handles_zero_values(self):
        scorer = _import_module("session_scorer")
        result = scorer.score_session(99, 0, 0, 0, 0, 0.0)
        assert result.total >= 0
        assert result.grade == "F"

    def test_evolve_handles_arbitrary_session(self):
        evolve = _import_module("evolve")
        # Should work for any session number
        for session in [1, 18, 100, 999]:
            report = evolve.generate_evolution(current_session=session)
            assert report.current_session == session
