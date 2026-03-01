"""
Tests for evolve.py — Evolution proposal engine.

Session 18 — Awake
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from evolve import (
    EvolutionProposal,
    GapArea,
    EvolutionReport,
    generate_evolution,
    format_evolution,
    evolve_to_json,
    save_evolution,
    GAP_AREAS,
    PROPOSALS,
)


# ---------------------------------------------------------------------------
# generate_evolution
# ---------------------------------------------------------------------------

class TestGenerateEvolution:
    def test_generates_report(self):
        report = generate_evolution()
        assert isinstance(report, EvolutionReport)

    def test_all_proposals_present(self):
        report = generate_evolution()
        assert len(report.proposals) == len(PROPOSALS)

    def test_tier1_proposals_exist(self):
        report = generate_evolution()
        assert len(report.tier1) > 0

    def test_tier2_proposals_exist(self):
        report = generate_evolution()
        assert len(report.tier2) > 0

    def test_tier3_proposals_exist(self):
        report = generate_evolution()
        assert len(report.tier3) > 0

    def test_tiers_are_complete_partition(self):
        report = generate_evolution()
        all_in_tiers = len(report.tier1) + len(report.tier2) + len(report.tier3)
        assert all_in_tiers == len(report.proposals)

    def test_gap_areas_present(self):
        report = generate_evolution()
        assert len(report.gap_areas) > 0

    def test_summary_is_non_empty(self):
        report = generate_evolution()
        assert isinstance(report.summary, str)
        assert len(report.summary) > 10

    def test_session_set(self):
        report = generate_evolution(current_session=42)
        assert report.current_session == 42

    def test_default_session(self):
        report = generate_evolution()
        assert report.current_session == 18


# ---------------------------------------------------------------------------
# Proposal data integrity
# ---------------------------------------------------------------------------

class TestProposalIntegrity:
    def test_all_proposals_have_required_fields(self):
        for p in PROPOSALS:
            assert p.title
            assert p.description
            assert p.tier in (1, 2, 3)
            assert p.impact in ("HIGH", "MEDIUM", "LOW")
            assert p.effort in ("LOW", "MEDIUM", "HIGH")
            assert p.category
            assert p.rationale
            assert p.example_command
            assert p.session_estimate >= 1

    def test_tier1_has_low_or_medium_effort(self):
        """Tier 1 should be approachable."""
        for p in PROPOSALS:
            if p.tier == 1:
                assert p.effort in ("LOW", "MEDIUM"), (
                    f"Tier 1 proposal '{p.title}' has HIGH effort — should be Tier 2"
                )

    def test_all_tier1_have_high_impact(self):
        for p in PROPOSALS:
            if p.tier == 1:
                assert p.impact in ("HIGH", "MEDIUM")


# ---------------------------------------------------------------------------
# Gap area data integrity
# ---------------------------------------------------------------------------

class TestGapAreaIntegrity:
    def test_all_gaps_have_required_fields(self):
        for g in GAP_AREAS:
            assert g.name
            assert g.current_state
            assert g.target_state
            assert g.gap_severity in ("CRITICAL", "SIGNIFICANT", "MINOR")
            assert g.sessions_to_close >= 1

    def test_no_duplicate_gap_names(self):
        names = [g.name for g in GAP_AREAS]
        assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# format_evolution
# ---------------------------------------------------------------------------

class TestFormatEvolution:
    def test_output_is_string(self):
        report = generate_evolution()
        out = format_evolution(report)
        assert isinstance(out, str)
        assert len(out) > 100

    def test_output_contains_tiers(self):
        report = generate_evolution()
        out = format_evolution(report)
        assert "TIER 1" in out
        assert "TIER 2" in out
        assert "TIER 3" in out

    def test_output_contains_gap_analysis(self):
        report = generate_evolution()
        out = format_evolution(report)
        assert "GAP ANALYSIS" in out

    def test_output_contains_proposal_titles(self):
        report = generate_evolution()
        out = format_evolution(report)
        for p in report.tier1:
            assert p.title in out

    def test_output_contains_example_commands(self):
        report = generate_evolution()
        out = format_evolution(report)
        # At least one example command should appear
        assert "awake" in out.lower()


# ---------------------------------------------------------------------------
# evolve_to_json
# ---------------------------------------------------------------------------

class TestEvolveToJson:
    def test_valid_json(self):
        report = generate_evolution()
        data = json.loads(evolve_to_json(report))
        assert isinstance(data, dict)

    def test_json_has_all_tiers(self):
        report = generate_evolution()
        data = json.loads(evolve_to_json(report))
        assert "tier1" in data
        assert "tier2" in data
        assert "tier3" in data

    def test_json_tier_counts_match(self):
        report = generate_evolution()
        data = json.loads(evolve_to_json(report))
        assert len(data["tier1"]) == len(report.tier1)
        assert len(data["tier2"]) == len(report.tier2)

    def test_json_gap_areas_present(self):
        report = generate_evolution()
        data = json.loads(evolve_to_json(report))
        assert "gap_areas" in data
        assert len(data["gap_areas"]) > 0

    def test_json_session_present(self):
        report = generate_evolution(current_session=18)
        data = json.loads(evolve_to_json(report))
        assert data["current_session"] == 18


# ---------------------------------------------------------------------------
# save_evolution
# ---------------------------------------------------------------------------

class TestSaveEvolution:
    def test_saves_to_disk(self, tmp_path):
        report = generate_evolution()
        out = tmp_path / "docs" / "evolve.md"
        save_evolution(report, out)
        assert out.exists()

    def test_file_contains_content(self, tmp_path):
        report = generate_evolution()
        out = tmp_path / "evolve.md"
        save_evolution(report, out)
        content = out.read_text()
        assert "Evolution" in content

    def test_creates_parent_directory(self, tmp_path):
        report = generate_evolution()
        out = tmp_path / "deeply" / "nested" / "evolve.md"
        save_evolution(report, out)
        assert out.exists()
