"""Tests for src/brain.py — 37 tests."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.brain import (
    Brain,
    SessionPlan,
    TaskCandidate,
    ScoreBreakdown,
    _score_roadmap_alignment,
    _score_issue_urgency,
    _score_complexity_fit,
    _score_cross_module_synergy,
    _score_health_improvement,
    save_plan,
    save_plan_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_ROADMAP = """
# Awake Roadmap

## Active Sprint

## Backlog

- [ ] **Contribution guide** — CONTRIBUTING.md for humans who want to open issues
- [ ] **Overnight dashboard** — Deployed web page showing real-time repo evolution
- [ ] **Issue auto-triage** — Read open issues and prioritize them for the next session
- [ ] **Session replay** — Re-run any prior session's PRs as a dry-run

## Completed

- [x] **Initial scaffold** — README, rules, roadmap (Session 0)
"""

SAMPLE_TRIAGE = {
    "issues": [
        {
            "number": 1,
            "title": "Dashboard not loading",
            "body": "The dashboard crashes on mobile",
            "labels": ["bug", "human-priority"],
            "comment_count": 5,
            "priority": 1,
        },
        {
            "number": 2,
            "title": "Add dark mode toggle",
            "body": "Would be nice to have dark mode",
            "labels": ["enhancement"],
            "comment_count": 0,
            "priority": 4,
        },
    ]
}


@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal repo structure for testing."""
    (tmp_path / "ROADMAP.md").write_text(SAMPLE_ROADMAP)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "triage.json").write_text(json.dumps(SAMPLE_TRIAGE))
    return tmp_path


# ---------------------------------------------------------------------------
# ScoreBreakdown
# ---------------------------------------------------------------------------

class TestScoreBreakdown:
    def test_total_sums_components(self):
        b = ScoreBreakdown(
            issue_urgency=10,
            roadmap_alignment=20,
            health_improvement=5,
            complexity_fit=8,
            cross_module_synergy=6,
        )
        assert b.total == 49

    def test_to_dict_has_all_keys(self):
        b = ScoreBreakdown()
        d = b.to_dict()
        assert "issue_urgency" in d
        assert "roadmap_alignment" in d
        assert "total" in d

    def test_default_total_is_zero(self):
        assert ScoreBreakdown().total == 0.0


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

class TestScoreRoadmapAlignment:
    def test_backlog_item_scores_high(self):
        score = _score_roadmap_alignment("Overnight dashboard", "web page", SAMPLE_ROADMAP)
        assert score > 0

    def test_completed_item_scores_lower(self):
        score = _score_roadmap_alignment("Initial scaffold", "", SAMPLE_ROADMAP)
        assert score <= 10

    def test_irrelevant_task_scores_low(self):
        score = _score_roadmap_alignment("Paint the fence blue", "not in roadmap", SAMPLE_ROADMAP)
        assert score == 0.0

    def test_max_capped_at_25(self):
        score = _score_roadmap_alignment("dashboard triage replay contributing", "dashboard", SAMPLE_ROADMAP)
        assert score <= 25.0


class TestScoreIssueUrgency:
    def test_empty_issues_returns_zero(self):
        assert _score_issue_urgency([]) == 0.0

    def test_human_priority_label_boosts_score(self):
        score = _score_issue_urgency([{"priority": 3, "labels": ["human-priority"], "comment_count": 0}])
        assert score >= 15

    def test_p1_scores_higher_than_p5(self):
        p1 = _score_issue_urgency([{"priority": 1, "labels": [], "comment_count": 0}])
        p5 = _score_issue_urgency([{"priority": 5, "labels": [], "comment_count": 0}])
        assert p1 > p5

    def test_max_capped_at_35(self):
        score = _score_issue_urgency([
            {"priority": 1, "labels": ["human-priority"], "comment_count": 10},
            {"priority": 1, "labels": ["human-priority"], "comment_count": 10},
        ])
        assert score <= 35.0

    def test_many_comments_boost(self):
        no_comments = _score_issue_urgency([{"priority": 3, "labels": [], "comment_count": 0}])
        many_comments = _score_issue_urgency([{"priority": 3, "labels": [], "comment_count": 5}])
        assert many_comments > no_comments


class TestScoreComplexityFit:
    def test_single_pr_scores_max(self):
        assert _score_complexity_fit("any", 1) == 10.0

    def test_two_prs_scores_well(self):
        assert _score_complexity_fit("any", 2) == 8.0

    def test_many_prs_scores_low(self):
        assert _score_complexity_fit("any", 10) == 2.0


class TestScoreCrossModuleSynergy:
    def test_no_modules_scores_zero(self):
        assert _score_cross_module_synergy([]) == 0.0

    def test_one_module_scores_low(self):
        assert _score_cross_module_synergy(["src/cli.py"]) == 3.0

    def test_four_modules_scores_max(self):
        assert _score_cross_module_synergy(["a", "b", "c", "d"]) == 10.0

    def test_two_modules_scores_mid(self):
        assert _score_cross_module_synergy(["a", "b"]) == 6.0


class TestScoreHealthImprovement:
    def test_no_data_returns_neutral(self):
        assert _score_health_improvement(["src/foo.py"], {}) == 5.0

    def test_low_health_scores_high(self):
        health = {"src/foo.py": 60}
        score = _score_health_improvement(["src/foo.py"], health)
        assert score == 20.0

    def test_high_health_scores_low(self):
        health = {"src/foo.py": 95}
        score = _score_health_improvement(["src/foo.py"], health)
        assert score == 5.0


# ---------------------------------------------------------------------------
# Brain.plan
# ---------------------------------------------------------------------------

class TestBrainPlan:
    def test_plan_returns_session_plan(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        plan = brain.plan(session_number=5)
        assert isinstance(plan, SessionPlan)
        assert plan.session_number == 5

    def test_plan_extracts_backlog_items(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        plan = brain.plan(session_number=5)
        titles = [t.title for t in plan.all_candidates]
        assert any("dashboard" in t.lower() or "triage" in t.lower() or "replay" in t.lower()
                   for t in titles)

    def test_top_tasks_limited_by_max(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        plan = brain.plan(session_number=5, max_tasks=2)
        assert len(plan.top_tasks) <= 2

    def test_top_tasks_sorted_by_score(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        plan = brain.plan(session_number=5)
        scores = [t.score for t in plan.top_tasks]
        assert scores == sorted(scores, reverse=True)

    def test_issue_candidates_included(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        plan = brain.plan(session_number=5)
        issue_sources = [t for t in plan.all_candidates if t.source == "issue"]
        assert any(t for t in issue_sources if "1" in t.title)

    def test_extra_candidates_included(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        extra = TaskCandidate(
            title="Custom task",
            description="A manually injected task",
            source="generated",
            score=99.0,
            breakdown=ScoreBreakdown(complexity_fit=10),
        )
        plan = brain.plan(session_number=5, extra_candidates=[extra])
        assert any(t.title == "Custom task" for t in plan.all_candidates)

    def test_plan_with_no_roadmap(self, tmp_path):
        brain = Brain(repo_path=tmp_path)
        plan = brain.plan(session_number=1)
        assert isinstance(plan, SessionPlan)

    def test_plan_generated_at_set(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        plan = brain.plan(session_number=5)
        assert plan.generated_at != ""

    def test_p4_issue_excluded(self, tmp_repo):
        brain = Brain(repo_path=tmp_repo)
        plan = brain.plan(session_number=5)
        assert not any("dark mode" in t.title for t in plan.all_candidates)


# ---------------------------------------------------------------------------
# SessionPlan
# ---------------------------------------------------------------------------

class TestSessionPlan:
    def make_plan(self) -> SessionPlan:
        tasks = [
            TaskCandidate("Task A", "desc A", "roadmap", score=80.0),
            TaskCandidate("Task B", "desc B", "issue", score=60.0),
        ]
        return SessionPlan(
            session_number=5,
            generated_at="2026-02-27 22:00 UTC",
            all_candidates=tasks,
            top_tasks=tasks[:1],
        )

    def test_to_dict(self):
        plan = self.make_plan()
        d = plan.to_dict()
        assert d["session_number"] == 5
        assert len(d["top_tasks"]) == 1

    def test_to_markdown_has_table(self):
        plan = self.make_plan()
        md = plan.to_markdown()
        assert "| Task | Score" in md
        assert "Task A" in md

    def test_to_markdown_has_session_header(self):
        plan = self.make_plan()
        md = plan.to_markdown()
        assert "Session 5 Plan" in md


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

class TestFileIO:
    def make_plan(self, tmp_path) -> SessionPlan:
        brain = Brain(repo_path=tmp_path)
        (tmp_path / "ROADMAP.md").write_text(SAMPLE_ROADMAP)
        return brain.plan(session_number=5)

    def test_save_plan_creates_file(self, tmp_path):
        plan = self.make_plan(tmp_path)
        out = tmp_path / "docs" / "session_plan.md"
        save_plan(plan, out)
        assert out.exists()
        assert "Session 5" in out.read_text()

    def test_save_plan_json_creates_file(self, tmp_path):
        plan = self.make_plan(tmp_path)
        out = tmp_path / "docs" / "session_plan.json"
        save_plan_json(plan, out)
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["session_number"] == 5

    def test_save_plan_creates_parent_dirs(self, tmp_path):
        plan = self.make_plan(tmp_path)
        out = tmp_path / "deep" / "nested" / "plan.md"
        save_plan(plan, out)
        assert out.exists()
