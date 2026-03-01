"""Tests for src/session_replay.py — 37 tests."""

from __future__ import annotations

import pytest
from pathlib import Path

from src.session_replay import (
    SessionReplay,
    ReplayedTask,
    ReplayedPR,
    replay,
    replay_all,
    compare_sessions,
    _extract_session_sections,
    _parse_session_section,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LOG = """\
# Awake Log

---

## Session 0 — February 27, 2026 (Setup)

**Operator:** Computer (autonomous)  

**Notes:** The experiment begins.

---

## Session 1 — February 27, 2026

**Operator:** Computer (autonomous)  

**Tasks completed:**

- ✅ **Self-stats engine** → [PR #1](https://github.com/gunnargray-dev/awake/pull/1) — `src/stats.py`: analyzes git history to compute commits and totals.
- ✅ **Session logger** → [PR #1](https://github.com/gunnargray-dev/awake/pull/1) — `src/session_logger.py`: structured SessionEntry dataclass.

**Pull requests:**

- [#1](https://github.com/gunnargray-dev/awake/pull/1) — [awake] feat: self-stats engine + session logger (`awake/session-1-stats-engine`))
- [#2](https://github.com/gunnargray-dev/awake/pull/2) — [awake] test: 50-test suite (`awake/session-1-test-framework`))

**Decisions & rationale:**

- Used subprocess over gitpython to keep zero runtime dependencies
- Shipped stats and logger in a single PR since they're tightly coupled

**Stats snapshot:**

- Nights active: 1
- Total PRs: 3
- Total commits: 4
- Lines changed: ~700

**Notes:** First autonomous session.

---

## Session 2 — February 27, 2026

**Operator:** Computer (autonomous)  

**Tasks completed:**

- ✅ **Code health monitor** → [PR #4](https://github.com/gunnargray-dev/awake/pull/4) — `src/health.py`: AST-based static analyzer.

**Pull requests:**

- [#4](https://github.com/gunnargray-dev/awake/pull/4) — [awake] feat: code health monitor (`awake/session-2-code-health-monitor`))

**Stats snapshot:**

- Nights active: 2
- Total PRs: 6

---
"""


@pytest.fixture
def log_file(tmp_path) -> Path:
    """Write SAMPLE_LOG to a temp file and return its path."""
    p = tmp_path / "AWAKE_LOG.md"
    p.write_text(SAMPLE_LOG)
    return p


# ---------------------------------------------------------------------------
# _extract_session_sections
# ---------------------------------------------------------------------------

class TestExtractSessionSections:
    def test_extracts_correct_count(self):
        sections = _extract_session_sections(SAMPLE_LOG)
        assert len(sections) == 3

    def test_extracts_correct_session_numbers(self):
        sections = _extract_session_sections(SAMPLE_LOG)
        assert 0 in sections
        assert 1 in sections
        assert 2 in sections

    def test_section_contains_relevant_content(self):
        sections = _extract_session_sections(SAMPLE_LOG)
        assert "Self-stats engine" in sections[1]
        assert "Code health monitor" in sections[2]

    def test_empty_log_returns_empty_dict(self):
        assert _extract_session_sections("") == {}

    def test_log_with_no_sessions_returns_empty(self):
        assert _extract_session_sections("# Just a header\n\nSome text") == {}


# ---------------------------------------------------------------------------
# _parse_session_section (Session 1)
# ---------------------------------------------------------------------------

class TestParseSessionSection:
    @pytest.fixture
    def session1(self):
        """Return the parsed Session 1 replay."""
        sections = _extract_session_sections(SAMPLE_LOG)
        return _parse_session_section(1, sections[1])

    def test_session_number(self, session1):
        assert session1.session_number == 1

    def test_date_parsed(self, session1):
        assert "February 27, 2026" in session1.date

    def test_operator_parsed(self, session1):
        assert "Computer" in session1.operator

    def test_tasks_parsed(self, session1):
        assert len(session1.tasks) == 2

    def test_task_names(self, session1):
        names = [t.name for t in session1.tasks]
        assert "Self-stats engine" in names
        assert "Session logger" in names

    def test_task_status_completed(self, session1):
        for task in session1.tasks:
            assert task.status == "completed"

    def test_task_pr_number(self, session1):
        task = session1.tasks[0]
        assert task.pr_number == 1

    def test_task_pr_url(self, session1):
        task = session1.tasks[0]
        assert "github.com" in task.pr_url

    def test_prs_parsed(self, session1):
        assert len(session1.prs) == 2

    def test_pr_number_and_url(self, session1):
        pr1 = session1.prs[0]
        assert pr1.number == 1
        assert "github.com" in pr1.url

    def test_pr_branch_parsed(self, session1):
        pr1 = session1.prs[0]
        assert "session-1" in pr1.branch

    def test_decisions_parsed(self, session1):
        assert len(session1.decisions) == 2
        assert any("subprocess" in d for d in session1.decisions)

    def test_stats_snapshot_parsed(self, session1):
        assert "nights_active" in session1.stats_snapshot
        assert session1.stats_snapshot["nights_active"] == "1"

    def test_notes_parsed(self, session1):
        assert "First autonomous session" in session1.notes


# ---------------------------------------------------------------------------
# SessionReplay properties
# ---------------------------------------------------------------------------

class TestSessionReplayProperties:
    @pytest.fixture
    def session1(self):
        """Return the parsed Session 1 replay."""
        sections = _extract_session_sections(SAMPLE_LOG)
        return _parse_session_section(1, sections[1])

    def test_task_count_only_completed(self, session1):
        assert session1.task_count == 2

    def test_pr_count(self, session1):
        assert session1.pr_count == 2

    def test_modules_added(self, session1):
        modules = session1.modules_added
        assert "src/stats.py" in modules
        assert "src/session_logger.py" in modules

    def test_narrative_contains_session_number(self, session1):
        n = session1.narrative()
        assert "Session 1" in n

    def test_narrative_contains_task_names(self, session1):
        n = session1.narrative()
        assert "Self-stats engine" in n

    def test_to_markdown_has_sections(self, session1):
        md = session1.to_markdown()
        assert "## Tasks" in md
        assert "## Pull Requests" in md
        assert "## Narrative" in md

    def test_to_dict_has_keys(self, session1):
        d = session1.to_dict()
        assert "session_number" in d
        assert "task_count" in d
        assert "pr_count" in d
        assert "modules_added" in d


# ---------------------------------------------------------------------------
# replay() and replay_all()
# ---------------------------------------------------------------------------

class TestReplay:
    def test_replay_returns_correct_session(self, log_file):
        r = replay(log_file, session_number=1)
        assert r is not None
        assert r.session_number == 1

    def test_replay_missing_session_returns_none(self, log_file):
        r = replay(log_file, session_number=99)
        assert r is None

    def test_replay_missing_file_returns_none(self, tmp_path):
        r = replay(tmp_path / "does_not_exist.md", session_number=1)
        assert r is None

    def test_replay_session_zero(self, log_file):
        r = replay(log_file, session_number=0)
        assert r is not None
        assert r.session_number == 0

    def test_replay_all_returns_all_sessions(self, log_file):
        all_r = replay_all(log_file)
        assert len(all_r) == 3

    def test_replay_all_sorted_ascending(self, log_file):
        all_r = replay_all(log_file)
        nums = [r.session_number for r in all_r]
        assert nums == sorted(nums)

    def test_replay_all_missing_file_returns_empty(self, tmp_path):
        all_r = replay_all(tmp_path / "missing.md")
        assert all_r == []


# ---------------------------------------------------------------------------
# compare_sessions()
# ---------------------------------------------------------------------------

class TestCompareSessions:
    def test_compare_returns_markdown(self, log_file):
        md = compare_sessions(log_file, 1, 2)
        assert "# Session 1 vs Session 2 Comparison" in md

    def test_compare_has_table(self, log_file):
        md = compare_sessions(log_file, 1, 2)
        assert "| Metric |" in md

    def test_compare_shows_task_counts(self, log_file):
        md = compare_sessions(log_file, 1, 2)
        assert "Tasks Completed" in md

    def test_compare_handles_missing_session(self, log_file):
        md = compare_sessions(log_file, 1, 99)
        assert "N/A" in md
