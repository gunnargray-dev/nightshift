"""
Tests for insights.py — Session insights engine.

Covers:
- Log parsing (headers, stats, PR counts, tasks)
- Per-session derived metrics (modules added, tests added)
- Velocity calculations
- Streak detection
- Insight generation
- Report serialization (markdown, json, dict)
- Edge cases: empty log, single session, missing stats, zero values
"""

from __future__ import annotations

import json
import re
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from insights import (
    Insight,
    InsightsReport,
    SessionRecord,
    Streak,
    VelocityStats,
    _compute_per_session_modules,
    _compute_per_session_tests,
    _compute_velocity,
    _confidence_bar,
    _detect_streaks,
    _generate_insights,
    _parse_sessions,
    generate_insights,
    save_insights_report,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

MINIMAL_LOG = """
## Session 1 -- Stats + Tests (2026-02-27)

**Operator:** Computer

### Tasks Completed
- Done Built `src/stats.py`
- Done Wrote 50 tests

### PRs
- PR #2 -- Stats engine
- PR #3 -- Test framework

### Stats
| Metric | Value |
|--------|-------|
| Source modules | 8 |
| Tests | 50 |
| PRs opened | 2 |
"""

MULTI_SESSION_LOG = """
## Session 0 -- Repo Scaffold (2026-02-27)

**Operator:** Computer

### Tasks Completed
- Done Created repo scaffold

### PR
- PR #1 -- Session 0: Scaffold

### Stats
| Metric | Value |
|--------|-------|
| Source modules | 4 |
| Tests | 0 |
| PRs opened | 1 |

---

## Session 1 -- Stats + Tests + CI (2026-02-27)

**Operator:** Computer

### Tasks Completed
- Done Built `src/stats.py` to compute repo evolution stats
- Done Wrote 50 tests

### PRs
- PR #2 -- Stats engine
- PR #3 -- Session logger
- PR #4 -- Test framework
- PR #5 -- CI pipeline

### Stats
| Metric | Value |
|--------|-------|
| Source modules | 8 |
| Tests | 50 |
| PRs opened | 4 |

---

## Session 5 -- Brain + Issues + Dashboard (2026-02-27)

**Operator:** Computer

### Tasks Completed
- Done Built `src/issue_triage.py` issue classification engine
- Done Built `src/brain.py` task prioritization engine
- Done Built `src/dashboard.py` terminal dashboard
- Done Built `src/session_replay.py` replay engine
- Done Built `src/teach.py` tutorial generator
- Done Built `src/dna.py` repo fingerprint
- Done Built `src/maturity.py` maturity scoring
- Done Built `src/story.py` repo narrative generator
- Done Built `src/coverage_map.py` coverage heat map
- Done Built `src/security.py` security audit
- Done Built `src/dead_code.py` dead code detector
- Done Built `src/blame.py` blame attribution
- Done Built `src/coverage_tracker.py` analyzer

### PRs
- PR #15 -- Issue triage module
- PR #16 -- Brain module
- PR #17 -- Dashboard module
- PR #18 -- Session replay module
- PR #19 -- Web dashboard
- PR #20 -- Teach module
- PR #21 -- DNA fingerprint
- PR #22 -- Maturity scoring
- PR #23 -- Story generator
- PR #24 -- Coverage map
- PR #25 -- Security audit
- PR #26 -- Dead code detector
- PR #27 -- Blame attribution
- PR #28 -- Contributing guide

### Stats
| Metric | Value |
|--------|-------|
| Source modules | 26 |
| Tests | 1,260 |
| PRs opened | 14 |

---

## Session 10 -- Fixes + Doctor (2026-02-28)

**Operator:** Computer

### Tasks Completed
- Done Fixed session_replay branch regex bug
- Done Built `src/dep_graph.py` dependency graph visualizer
- Done Built `src/todo_hunter.py` stale TODO hunter
- Done Built `src/doctor.py` full diagnostic module

### PRs
- PR #29 -- Fix branch parsing bug
- PR #30 -- Dependency graph
- PR #31 -- TODO hunter
- PR #32 -- Doctor module

### Stats
| Metric | Value |
|--------|-------|
| Source modules | 30 |
| Tests | 1,622 |
| PRs opened | 4 |
"""


def _make_records(specs: list[dict]) -> list[SessionRecord]:
    """Build SessionRecord list from compact spec dicts."""
    return [
        SessionRecord(
            number=s["number"],
            date=s.get("date", "2026-02-27"),
            title=s.get("title", "Test Session"),
            prs=s.get("prs", 0),
            modules=s.get("modules", 0),
            tests=s.get("tests", 0),
            tasks=s.get("tasks", []),
            pr_titles=s.get("pr_titles", []),
        )
        for s in specs
    ]


# ---------------------------------------------------------------------------
# 1. _parse_sessions — basic parsing
# ---------------------------------------------------------------------------

class TestParseSessionsBasic:
    def test_parses_single_session(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert len(records) == 1

    def test_parses_session_number(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert records[0].number == 1

    def test_parses_session_date(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert records[0].date == "2026-02-27"

    def test_parses_session_title(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert "Stats" in records[0].title

    def test_parses_pr_count_from_stats_table(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert records[0].prs == 2

    def test_parses_module_count(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert records[0].modules == 8

    def test_parses_test_count(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert records[0].tests == 50

    def test_parses_tasks(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert len(records[0].tasks) >= 1

    def test_parses_pr_titles(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert len(records[0].pr_titles) >= 1

    def test_empty_log_returns_empty_list(self):
        records = _parse_sessions("")
        assert records == []

    def test_log_without_session_headers_returns_empty(self):
        records = _parse_sessions("This is just some text.\nNo session headers here.")
        assert records == []

    def test_multi_session_log_parses_all(self):
        records = _parse_sessions(MULTI_SESSION_LOG)
        assert len(records) == 4

    def test_multi_session_session_numbers_correct(self):
        records = _parse_sessions(MULTI_SESSION_LOG)
        numbers = {r.number for r in records}
        assert 0 in numbers
        assert 1 in numbers
        assert 5 in numbers
        assert 10 in numbers

    def test_comma_separated_test_count_parsed(self):
        """Tests like '1,260' should parse to 1260."""
        records = _parse_sessions(MULTI_SESSION_LOG)
        session5 = next(r for r in records if r.number == 5)
        assert session5.tests == 1260

    def test_session5_has_14_prs(self):
        records = _parse_sessions(MULTI_SESSION_LOG)
        session5 = next(r for r in records if r.number == 5)
        assert session5.prs == 14


# ---------------------------------------------------------------------------
# 2. _compute_per_session_modules / _compute_per_session_tests
# ---------------------------------------------------------------------------

class TestDerivedMetrics:
    def test_first_session_modules_equals_cumulative(self):
        records = _make_records([
            {"number": 0, "modules": 4},
        ])
        result = _compute_per_session_modules(records)
        assert result[0] == 4

    def test_delta_modules_computed_correctly(self):
        records = _make_records([
            {"number": 0, "modules": 4},
            {"number": 1, "modules": 8},
            {"number": 5, "modules": 26},
        ])
        result = _compute_per_session_modules(records)
        assert result[1] == 4     # 8 - 4
        assert result[5] == 18    # 26 - 8

    def test_zero_modules_session_produces_zero_delta(self):
        records = _make_records([
            {"number": 0, "modules": 0},
            {"number": 1, "modules": 0},
        ])
        result = _compute_per_session_modules(records)
        assert result[0] == 0
        assert result[1] == 0

    def test_test_delta_computed_correctly(self):
        records = _make_records([
            {"number": 0, "tests": 0},
            {"number": 1, "tests": 50},
            {"number": 5, "tests": 1260},
        ])
        result = _compute_per_session_tests(records)
        assert result[0] == 0
        assert result[1] == 50
        assert result[5] == 1210  # 1260 - 50

    def test_no_negative_deltas(self):
        """If cumulative count decreases (data issue), delta should be 0 not negative."""
        records = _make_records([
            {"number": 1, "modules": 10},
            {"number": 2, "modules": 8},  # regression in the data
        ])
        result = _compute_per_session_modules(records)
        assert result[2] >= 0


# ---------------------------------------------------------------------------
# 3. VelocityStats / _compute_velocity
# ---------------------------------------------------------------------------

class TestComputeVelocity:
    def test_empty_records_returns_zero_velocity(self):
        vel = _compute_velocity([], {}, {})
        assert vel.prs_per_session == 0.0
        assert vel.tests_per_session == 0.0
        assert vel.modules_per_session == 0.0
        assert vel.peak_session == 0
        assert vel.peak_prs == 0

    def test_prs_per_session_average(self):
        records = _make_records([
            {"number": 1, "prs": 4},
            {"number": 2, "prs": 3},
            {"number": 3, "prs": 5},
        ])
        vel = _compute_velocity(records, {1: 2, 2: 2, 3: 3}, {1: 50, 2: 60, 3: 70})
        assert abs(vel.prs_per_session - 4.0) < 0.01

    def test_peak_session_is_session_with_most_prs(self):
        records = _make_records([
            {"number": 1, "prs": 3},
            {"number": 5, "prs": 14},
            {"number": 10, "prs": 4},
        ])
        vel = _compute_velocity(records, {}, {})
        assert vel.peak_session == 5
        assert vel.peak_prs == 14

    def test_velocity_is_velocity_dataclass(self):
        records = _make_records([{"number": 1, "prs": 2}])
        vel = _compute_velocity(records, {1: 3}, {1: 100})
        assert isinstance(vel, VelocityStats)

    def test_modules_per_session_computed(self):
        records = _make_records([
            {"number": 1, "prs": 2},
            {"number": 2, "prs": 2},
        ])
        pm = {1: 4, 2: 6}
        vel = _compute_velocity(records, pm, {1: 50, 2: 60})
        assert abs(vel.modules_per_session - 5.0) < 0.01


# ---------------------------------------------------------------------------
# 4. Streak detection
# ---------------------------------------------------------------------------

class TestDetectStreaks:
    def test_empty_records_returns_no_streaks(self):
        streaks = _detect_streaks([], {}, {})
        assert streaks == []

    def test_most_productive_streak_detected(self):
        records = _make_records([
            {"number": 1, "prs": 3},
            {"number": 5, "prs": 14},
            {"number": 10, "prs": 4},
        ])
        streaks = _detect_streaks(records, {}, {})
        kinds = [s.kind for s in streaks]
        assert "most_productive" in kinds

    def test_most_productive_streak_has_correct_session(self):
        records = _make_records([
            {"number": 1, "prs": 3},
            {"number": 5, "prs": 14},
        ])
        streaks = _detect_streaks(records, {}, {})
        mp = next(s for s in streaks if s.kind == "most_productive")
        assert 5 in mp.sessions
        assert mp.metric_value == 14.0

    def test_feature_burst_detected_for_high_module_sessions(self):
        pm = {1: 3, 2: 4, 3: 5}
        records = _make_records([
            {"number": 1, "prs": 3},
            {"number": 2, "prs": 3},
            {"number": 3, "prs": 3},
        ])
        streaks = _detect_streaks(records, pm, {})
        kinds = [s.kind for s in streaks]
        assert "feature_burst" in kinds

    def test_test_growth_streak_detected(self):
        records = _make_records([
            {"number": 1, "prs": 2},
            {"number": 2, "prs": 3},
            {"number": 3, "prs": 4},
        ])
        pt = {1: 50, 2: 100, 3: 200}
        streaks = _detect_streaks(records, {}, pt)
        kinds = [s.kind for s in streaks]
        assert "test_growth" in kinds

    def test_consistency_streak_detected(self):
        records = _make_records([
            {"number": 1, "prs": 2},
            {"number": 2, "prs": 3},
            {"number": 3, "prs": 4},
            {"number": 4, "prs": 1},
        ])
        streaks = _detect_streaks(records, {}, {})
        kinds = [s.kind for s in streaks]
        assert "consistency" in kinds

    def test_streak_metric_value_is_float(self):
        records = _make_records([{"number": 5, "prs": 14}])
        streaks = _detect_streaks(records, {}, {})
        for s in streaks:
            assert isinstance(s.metric_value, float)

    def test_streak_sessions_is_list(self):
        records = _make_records([{"number": 5, "prs": 14}])
        streaks = _detect_streaks(records, {}, {})
        for s in streaks:
            assert isinstance(s.sessions, list)


# ---------------------------------------------------------------------------
# 5. Insight generation
# ---------------------------------------------------------------------------

class TestGenerateInsights:
    def test_empty_records_returns_empty_insights(self):
        insights = _generate_insights([], {}, {})
        assert insights == []

    def test_insights_is_list_of_insight_objects(self):
        records = _make_records([
            {"number": 1, "prs": 4, "tasks": ["Built stats analyzer"]},
            {"number": 5, "prs": 14, "tasks": ["Built brain analysis module", "Built coverage tracker"]},
        ])
        pm = {1: 8, 5: 18}
        pt = {1: 50, 5: 1210}
        insights = _generate_insights(records, pm, pt)
        assert isinstance(insights, list)
        for ins in insights:
            assert isinstance(ins, Insight)

    def test_peak_pr_session_produces_milestone_insight(self):
        records = _make_records([
            {"number": 1, "prs": 3},
            {"number": 5, "prs": 14},
        ])
        pm = {1: 4, 5: 18}
        pt = {1: 50, 5: 1210}
        insights = _generate_insights(records, pm, pt)
        milestone_titles = [i.title for i in insights if i.category == "milestone"]
        assert any("14" in t for t in milestone_titles)

    def test_insight_confidence_in_valid_range(self):
        records = _make_records([
            {"number": 1, "prs": 4},
            {"number": 5, "prs": 14},
        ])
        insights = _generate_insights(records, {1: 4, 5: 18}, {1: 50, 5: 1210})
        for ins in insights:
            assert 0.0 <= ins.confidence <= 1.0

    def test_insight_sessions_involved_is_list_of_ints(self):
        records = _make_records([
            {"number": 1, "prs": 4, "tasks": ["Built analyzer"]},
            {"number": 2, "prs": 3, "tasks": ["Built coverage tracker"]},
        ])
        insights = _generate_insights(records, {1: 4, 2: 3}, {1: 50, 2: 60})
        for ins in insights:
            assert isinstance(ins.sessions_involved, list)
            for s in ins.sessions_involved:
                assert isinstance(s, int)

    def test_test_acceleration_insight_with_many_sessions(self):
        """Should generate a test-acceleration insight when late > early."""
        records = _make_records([
            {"number": 1, "prs": 3},
            {"number": 2, "prs": 3},
            {"number": 3, "prs": 4},
            {"number": 10, "prs": 4},
            {"number": 11, "prs": 4},
            {"number": 12, "prs": 4},
        ])
        pt = {1: 50, 2: 60, 3: 70, 10: 200, 11: 220, 12: 250}
        insights = _generate_insights(records, {}, pt)
        productivity_insights = [i for i in insights if i.category == "productivity"]
        assert len(productivity_insights) >= 1

    def test_analysis_pattern_insight_generated_for_analysis_tasks(self):
        """Heavy analysis task list should trigger the pattern insight."""
        tasks = [
            "Built coverage analyzer",
            "Built health scorer",
            "Built audit tracker",
            "Built stats visualizer",
            "Built quality inspector",
            "Built security checker",
        ]
        records = _make_records([
            {"number": 1, "prs": 3, "tasks": tasks[:3]},
            {"number": 2, "prs": 3, "tasks": tasks[3:]},
        ])
        insights = _generate_insights(records, {1: 3, 2: 3}, {1: 50, 2: 60})
        pattern_insights = [i for i in insights if i.category == "pattern"]
        assert len(pattern_insights) >= 1

    def test_zero_pr_sessions_trigger_anomaly(self):
        records = _make_records([
            {"number": 1, "prs": 4},
            {"number": 2, "prs": 0},   # no PRs
            {"number": 3, "prs": 3},
        ])
        insights = _generate_insights(records, {1: 4, 2: 1, 3: 3}, {1: 50, 2: 0, 3: 60})
        anomaly_insights = [i for i in insights if i.category == "anomaly"]
        assert len(anomaly_insights) >= 1

    def test_categories_are_valid_values(self):
        records = _make_records([
            {"number": 1, "prs": 4, "tasks": ["Built analyzer"]},
            {"number": 5, "prs": 14, "tasks": ["Built coverage map", "Built health tracker"]},
        ])
        insights = _generate_insights(records, {1: 4, 5: 18}, {1: 50, 5: 1210})
        valid_categories = {"productivity", "pattern", "milestone", "anomaly"}
        for ins in insights:
            assert ins.category in valid_categories


# ---------------------------------------------------------------------------
# 6. InsightsReport serialization
# ---------------------------------------------------------------------------

class TestInsightsReportSerialization:
    def _make_report(self) -> InsightsReport:
        return InsightsReport(
            sessions_analyzed=4,
            total_prs=23,
            total_modules_built=26,
            insights=[
                Insight(
                    category="milestone",
                    title="Session 5 was the peak",
                    description="14 PRs in one night.",
                    confidence=0.99,
                    sessions_involved=[5],
                ),
            ],
            streaks=[
                Streak(
                    kind="most_productive",
                    sessions=[5],
                    description="Most PRs in a single session.",
                    metric_value=14.0,
                )
            ],
            velocity=VelocityStats(
                prs_per_session=5.75,
                tests_per_session=330.0,
                modules_per_session=6.5,
                peak_session=5,
                peak_prs=14,
            ),
        )

    def test_to_dict_returns_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_required_keys(self):
        report = self._make_report()
        d = report.to_dict()
        for key in ("sessions_analyzed", "total_prs", "total_modules_built",
                    "insights", "streaks", "velocity"):
            assert key in d

    def test_to_json_is_valid_json(self):
        report = self._make_report()
        raw = report.to_json()
        parsed = json.loads(raw)
        assert parsed["sessions_analyzed"] == 4
        assert parsed["total_prs"] == 23

    def test_to_json_insights_list(self):
        report = self._make_report()
        parsed = json.loads(report.to_json())
        assert len(parsed["insights"]) == 1
        assert parsed["insights"][0]["category"] == "milestone"

    def test_to_markdown_returns_string(self):
        report = self._make_report()
        md = report.to_markdown()
        assert isinstance(md, str)
        assert len(md) > 100

    def test_to_markdown_contains_session_count(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "4" in md

    def test_to_markdown_contains_insights_section(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "Session 5 was the peak" in md

    def test_to_markdown_contains_summary_table(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "Summary" in md
        assert "Total PRs" in md or "PRs" in md

    def test_to_markdown_contains_ai_voice(self):
        """The markdown should contain self-referential AI voice language."""
        report = self._make_report()
        md = report.to_markdown()
        assert "AI" in md or "Computer" in md or "awake" in md.lower()

    def test_to_markdown_contains_streaks(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "Streak" in md or "streak" in md or "Productive" in md


# ---------------------------------------------------------------------------
# 7. generate_insights — integration with AWAKE_LOG.md
# ---------------------------------------------------------------------------

class TestGenerateInsights:
    def test_generates_report_from_real_log(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MULTI_SESSION_LOG, encoding="utf-8")
        report = generate_insights(tmp_path, log)
        assert isinstance(report, InsightsReport)
        assert report.sessions_analyzed == 4

    def test_returns_empty_report_for_missing_log(self, tmp_path):
        # No log file present — should return empty but valid report
        report = generate_insights(tmp_path)
        assert report.sessions_analyzed == 0
        assert report.total_prs == 0
        assert isinstance(report.insights, list)

    def test_returns_empty_report_for_empty_log(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text("", encoding="utf-8")
        report = generate_insights(tmp_path, log)
        assert report.sessions_analyzed == 0

    def test_peak_session_identified(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MULTI_SESSION_LOG, encoding="utf-8")
        report = generate_insights(tmp_path, log)
        assert report.velocity.peak_session == 5
        assert report.velocity.peak_prs == 14

    def test_total_prs_correct(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MULTI_SESSION_LOG, encoding="utf-8")
        report = generate_insights(tmp_path, log)
        # Session 0: 1, Session 1: 4, Session 5: 14, Session 10: 4 = 23
        assert report.total_prs == 23

    def test_insights_not_empty_for_rich_log(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MULTI_SESSION_LOG, encoding="utf-8")
        report = generate_insights(tmp_path, log)
        assert len(report.insights) > 0

    def test_streaks_not_empty_for_rich_log(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MULTI_SESSION_LOG, encoding="utf-8")
        report = generate_insights(tmp_path, log)
        assert len(report.streaks) > 0

    def test_velocity_prs_per_session_is_positive(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MULTI_SESSION_LOG, encoding="utf-8")
        report = generate_insights(tmp_path, log)
        assert report.velocity.prs_per_session > 0

    def test_default_log_path_is_awake_log(self, tmp_path):
        """When log_path is None, should look for AWAKE_LOG.md in repo_path."""
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MINIMAL_LOG, encoding="utf-8")
        report = generate_insights(tmp_path)  # no explicit log_path
        assert report.sessions_analyzed == 1


# ---------------------------------------------------------------------------
# 8. save_insights_report
# ---------------------------------------------------------------------------

class TestSaveInsightsReport:
    def test_creates_file(self, tmp_path):
        report = InsightsReport(
            sessions_analyzed=1,
            total_prs=2,
            total_modules_built=4,
            insights=[],
            streaks=[],
            velocity=VelocityStats(2.0, 50.0, 4.0, 1, 2),
        )
        out = tmp_path / "docs" / "insights.md"
        save_insights_report(report, out)
        assert out.exists()

    def test_creates_parent_directories(self, tmp_path):
        report = InsightsReport(
            sessions_analyzed=1,
            total_prs=2,
            total_modules_built=4,
            insights=[],
            streaks=[],
            velocity=VelocityStats(2.0, 50.0, 4.0, 1, 2),
        )
        out = tmp_path / "a" / "b" / "c" / "insights.md"
        save_insights_report(report, out)
        assert out.exists()

    def test_file_contains_markdown(self, tmp_path):
        report = InsightsReport(
            sessions_analyzed=3,
            total_prs=9,
            total_modules_built=12,
            insights=[],
            streaks=[],
            velocity=VelocityStats(3.0, 100.0, 4.0, 5, 14),
        )
        out = tmp_path / "insights.md"
        save_insights_report(report, out)
        content = out.read_text()
        assert "Awake" in content
        assert "#" in content  # markdown headings


# ---------------------------------------------------------------------------
# 9. _confidence_bar helper
# ---------------------------------------------------------------------------

class TestConfidenceBar:
    def test_full_confidence_all_filled(self):
        bar = _confidence_bar(1.0)
        assert "░" not in bar or bar.count("█") == 5

    def test_zero_confidence_all_empty(self):
        bar = _confidence_bar(0.0)
        assert "█" not in bar

    def test_half_confidence_mixed(self):
        bar = _confidence_bar(0.5)
        assert len(bar) == 5

    def test_confidence_bar_length_always_five(self):
        for val in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert len(_confidence_bar(val)) == 5


# ---------------------------------------------------------------------------
# 10. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_session_log(self):
        records = _parse_sessions(MINIMAL_LOG)
        assert len(records) == 1
        pm = _compute_per_session_modules(records)
        pt = _compute_per_session_tests(records)
        vel = _compute_velocity(records, pm, pt)
        insights = _generate_insights(records, pm, pt)
        streaks = _detect_streaks(records, pm, pt)
        # Should not raise; may produce limited insights
        assert isinstance(vel, VelocityStats)
        assert isinstance(insights, list)
        assert isinstance(streaks, list)

    def test_log_with_no_stats_tables(self):
        log = """
## Session 1 -- Empty Stats (2026-01-01)

**Operator:** Computer

### Tasks Completed
- Done Built something

### PRs
- PR #1 -- Something
"""
        records = _parse_sessions(log)
        assert len(records) == 1
        assert records[0].modules == 0
        assert records[0].tests == 0

    def test_report_to_dict_is_json_serializable(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text(MULTI_SESSION_LOG, encoding="utf-8")
        report = generate_insights(tmp_path, log)
        d = report.to_dict()
        # Should serialize without error
        dumped = json.dumps(d)
        assert len(dumped) > 10

    def test_insight_dataclass_to_dict(self):
        ins = Insight(
            category="pattern",
            title="Test insight",
            description="Something interesting.",
            confidence=0.8,
            sessions_involved=[1, 2, 3],
        )
        d = ins.to_dict()
        assert d["category"] == "pattern"
        assert d["confidence"] == 0.8
        assert d["sessions_involved"] == [1, 2, 3]

    def test_streak_dataclass_to_dict(self):
        streak = Streak(
            kind="most_productive",
            sessions=[5],
            description="Peak PR session.",
            metric_value=14.0,
        )
        d = streak.to_dict()
        assert d["kind"] == "most_productive"
        assert d["metric_value"] == 14.0

    def test_velocity_stats_to_dict(self):
        vel = VelocityStats(
            prs_per_session=3.5,
            tests_per_session=120.0,
            modules_per_session=4.0,
            peak_session=5,
            peak_prs=14,
        )
        d = vel.to_dict()
        assert d["prs_per_session"] == 3.5
        assert d["peak_session"] == 5
