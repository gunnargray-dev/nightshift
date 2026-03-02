"""Tests for src/audit.py — Session 16."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def _import_audit():
    from src import audit
    return audit


# ---------------------------------------------------------------------------
# Unit tests for score helpers
# ---------------------------------------------------------------------------

class TestScoreHelpers:
    def test_security_grade_to_score_a(self):
        audit = _import_audit()
        assert audit._security_grade_to_score("A") == 95.0

    def test_security_grade_to_score_f(self):
        audit = _import_audit()
        assert audit._security_grade_to_score("F") == 25.0

    def test_security_grade_to_score_unknown(self):
        audit = _import_audit()
        assert audit._security_grade_to_score("Z") == 50.0

    def test_coverage_avg_clamped_high(self):
        audit = _import_audit()
        assert audit._coverage_avg_to_score(110.0) == 100.0

    def test_coverage_avg_clamped_low(self):
        audit = _import_audit()
        assert audit._coverage_avg_to_score(-5.0) == 0.0

    def test_dead_code_to_score_zero(self):
        audit = _import_audit()
        assert audit._dead_code_to_score(0, 10) == 100.0

    def test_dead_code_to_score_high(self):
        audit = _import_audit()
        score = audit._dead_code_to_score(20, 10)
        assert score == 0.0

    def test_dead_code_no_modules(self):
        audit = _import_audit()
        assert audit._dead_code_to_score(0, 0) == 100.0

    def test_complexity_low(self):
        audit = _import_audit()
        assert audit._complexity_to_score(3.0) == 100.0

    def test_complexity_mid(self):
        audit = _import_audit()
        score = audit._complexity_to_score(10.0)
        assert 70.0 <= score <= 80.0

    def test_complexity_high(self):
        audit = _import_audit()
        score = audit._complexity_to_score(30.0)
        assert score >= 0.0

    def test_score_to_status_pass(self):
        audit = _import_audit()
        assert audit._score_to_status(85.0) == "pass"

    def test_score_to_status_warn(self):
        audit = _import_audit()
        assert audit._score_to_status(60.0) == "warn"

    def test_score_to_status_fail(self):
        audit = _import_audit()
        assert audit._score_to_status(30.0) == "fail"

    def test_grade_a(self):
        audit = _import_audit()
        assert audit._grade(92.0) == "A"

    def test_grade_b(self):
        audit = _import_audit()
        assert audit._grade(80.0) == "B"

    def test_grade_c(self):
        audit = _import_audit()
        assert audit._grade(65.0) == "C"

    def test_grade_d(self):
        audit = _import_audit()
        assert audit._grade(47.0) == "D"

    def test_grade_f(self):
        audit = _import_audit()
        assert audit._grade(20.0) == "F"

    def test_overall_status_healthy(self):
        audit = _import_audit()
        assert audit._overall_status(80.0) == "healthy"

    def test_overall_status_needs_attention(self):
        audit = _import_audit()
        assert audit._overall_status(60.0) == "needs-attention"

    def test_overall_status_critical(self):
        audit = _import_audit()
        assert audit._overall_status(30.0) == "critical"


# ---------------------------------------------------------------------------
# AuditSection tests
# ---------------------------------------------------------------------------

class TestAuditSection:
    def _make_section(self, score=80.0, weight=0.25, status="pass"):
        audit = _import_audit()
        return audit.AuditSection(
            name="Test", score=score, raw_value="80/100",
            weight=weight, status=status, summary="Test summary",
        )

    def test_weighted_contribution(self):
        s = self._make_section(score=80.0, weight=0.25)
        assert abs(s.weighted_contribution() - 20.0) < 0.001

    def test_to_dict_keys(self):
        s = self._make_section()
        d = s.to_dict()
        assert "name" in d
        assert "score" in d
        assert "weight" in d
        assert "status" in d


# ---------------------------------------------------------------------------
# AuditReport tests
# ---------------------------------------------------------------------------

class TestAuditReport:
    def _make_report(self):
        audit = _import_audit()
        sections = [
            audit.AuditSection("Health", 80.0, "80/100", 0.25, "pass", "Good"),
            audit.AuditSection("Security", 70.0, "Grade B", 0.25, "pass", "OK"),
            audit.AuditSection("Dead Code", 40.0, "5 dead", 0.20, "fail", "Issues"),
            audit.AuditSection("Coverage", 60.0, "60/100", 0.20, "warn", "Needs work"),
            audit.AuditSection("Complexity", 75.0, "avg CC 5", 0.10, "pass", "Fine"),
        ]
        return audit.AuditReport(
            sections=sections,
            overall_score=67.0,
            overall_grade="C",
            overall_status="needs-attention",
            repo_path="/tmp/test",
            generated_at="2026-01-01T00:00:00",
        )

    def test_passes_list(self):
        r = self._make_report()
        passes = r.passes
        assert len(passes) == 3

    def test_warnings_list(self):
        r = self._make_report()
        assert len(r.warnings) == 1

    def test_failures_list(self):
        r = self._make_report()
        assert len(r.failures) == 1

    def test_to_dict_has_required_keys(self):
        r = self._make_report()
        d = r.to_dict()
        assert "overall_score" in d
        assert "overall_grade" in d
        assert "sections" in d
        assert "passes" in d
        assert "warnings" in d
        assert "failures" in d

    def test_to_json_valid(self):
        r = self._make_report()
        parsed = json.loads(r.to_json())
        assert parsed["overall_grade"] == "C"

    def test_to_markdown_contains_grade(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "Grade: " in md
        assert "C" in md

    def test_to_markdown_contains_dimensions(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "Health" in md
        assert "Security" in md
        assert "Dead Code" in md

    def test_to_markdown_contains_recommendations(self):
        r = self._make_report()
        md = r.to_markdown()
        assert "Recommendations" in md

    def test_to_markdown_grade_a_no_recommendations(self):
        audit = _import_audit()
        sections = [
            audit.AuditSection("Health", 95.0, "95/100", 1.0, "pass", "Excellent"),
        ]
        report = audit.AuditReport(
            sections=sections,
            overall_score=95.0,
            overall_grade="A",
            overall_status="healthy",
            repo_path="/tmp/test",
            generated_at="2026-01-01T00:00:00",
        )
        md = report.to_markdown()
        assert "Recommendations" not in md


# ---------------------------------------------------------------------------
# Integration test: run_audit with mocked sub-modules
# ---------------------------------------------------------------------------

class TestRunAudit:
    def test_run_audit_returns_report(self, tmp_path):
        audit = _import_audit()

        src = tmp_path / "src"
        src.mkdir()
        (src / "dummy.py").write_text("def foo(): pass\n")

        mock_health = MagicMock()
        mock_health.overall_health_score = 75
        mock_health.total_functions = 10
        mock_health.total_classes = 2
        mock_health.docstring_coverage = 0.6

        mock_security = MagicMock()
        mock_security.grade = "B"
        mock_security.findings = []

        mock_dc = MagicMock()
        mock_dc.high_confidence = []
        mock_dc.items = []

        mock_cov = MagicMock()
        mock_cov.avg_score = 65.0
        mock_cov.entries = []
        mock_cov.modules_without_tests = []

        with patch("src.health.generate_health_report", return_value=mock_health), \
             patch("src.security.audit_security", return_value=mock_security), \
             patch("src.dead_code.find_dead_code", return_value=mock_dc), \
             patch("src.coverage_map.build_coverage_map", return_value=mock_cov), \
             patch("src.refactor.find_refactor_candidates", return_value=[]):
            report = audit.run_audit(tmp_path)

        assert isinstance(report, audit.AuditReport)
        assert len(report.sections) == 5
        assert report.overall_score > 0
        assert report.overall_grade in ("A", "B", "C", "D", "F")

    def test_run_audit_handles_exceptions(self, tmp_path):
        audit = _import_audit()
        src = tmp_path / "src"
        src.mkdir()

        with patch("src.health.generate_health_report", side_effect=RuntimeError("boom")), \
             patch("src.security.audit_security", side_effect=RuntimeError("boom")), \
             patch("src.dead_code.find_dead_code", side_effect=RuntimeError("boom")), \
             patch("src.coverage_map.build_coverage_map", side_effect=RuntimeError("boom")), \
             patch("src.refactor.find_refactor_candidates", side_effect=RuntimeError("boom")):
            report = audit.run_audit(tmp_path)

        assert isinstance(report, audit.AuditReport)
        assert len(report.sections) == 5
        for s in report.sections:
            assert s.status in ("warn", "fail")

    def test_save_audit_report(self, tmp_path):
        audit = _import_audit()
        sections = [
            audit.AuditSection("Health", 80.0, "80/100", 1.0, "pass", "Good"),
        ]
        report = audit.AuditReport(
            sections=sections,
            overall_score=80.0,
            overall_grade="B",
            overall_status="healthy",
            repo_path=str(tmp_path),
            generated_at="2026-01-01T00:00:00",
        )
        out = tmp_path / "docs" / "audit_report.md"
        audit.save_audit_report(report, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_overall_score_weighted_correctly(self, tmp_path):
        audit = _import_audit()

        mock_health = MagicMock()
        mock_health.overall_health_score = 100
        mock_health.total_functions = 5
        mock_health.total_classes = 1
        mock_health.overall_docstring_coverage = 1.0

        mock_security = MagicMock()
        mock_security.grade = "A"
        mock_security.findings = []

        mock_dc = MagicMock()
        mock_dc.high_confidence = []
        mock_dc.items = []

        mock_cov = MagicMock()
        mock_cov.avg_score = 100.0
        mock_cov.entries = []
        mock_cov.modules_without_tests = []

        with patch("src.health.generate_health_report", return_value=mock_health), \
             patch("src.security.audit_security", return_value=mock_security), \
             patch("src.dead_code.find_dead_code", return_value=mock_dc), \
             patch("src.coverage_map.build_coverage_map", return_value=mock_cov), \
             patch("src.refactor.find_refactor_candidates", return_value=[]):
            src = tmp_path / "src"
            src.mkdir()
            report = audit.run_audit(tmp_path)

        assert report.overall_score >= 90.0
        assert report.overall_grade == "A"
