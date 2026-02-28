"""Tests for the Nightshift session logger (src/session_logger.py)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from src.session_logger import (
    PRRecord,
    TaskRecord,
    SessionEntry,
    append_session_to_log,
    load_session_history,
    format_session_json,
)


# ---------------------------------------------------------------------------
# PRRecord
# ---------------------------------------------------------------------------


class TestPRRecord:
    def test_defaults(self):
        pr = PRRecord(number=1, title="Add stats", branch="nightshift/session-1-stats")
        assert pr.number == 1
        assert pr.title == "Add stats"
        assert pr.branch == "nightshift/session-1-stats"
        assert pr.url == ""
        assert pr.status == "open"

    def test_to_dict(self):
        pr = PRRecord(number=5, title="Fix logger", branch="nightshift/session-1-fix", url="https://github.com/pr/5")
        d = pr.to_dict()
        assert d["number"] == 5
        assert d["url"] == "https://github.com/pr/5"


# ---------------------------------------------------------------------------
# TaskRecord
# ---------------------------------------------------------------------------


class TestTaskRecord:
    def test_defaults(self):
        task = TaskRecord(name="stats engine", description="Computes repo statistics")
        assert task.status == "completed"
        assert task.pr is None

    def test_with_pr(self):
        pr = PRRecord(number=3, title="Add stats", branch="branch")
        task = TaskRecord(name="stats", description="desc", pr=pr)
        assert task.pr.number == 3


# ---------------------------------------------------------------------------
# SessionEntry
# ---------------------------------------------------------------------------


class TestSessionEntry:
    def test_auto_date(self):
        entry = SessionEntry(session_number=1)
        assert entry.date != ""
        assert len(entry.date) > 5

    def test_explicit_date(self):
        entry = SessionEntry(session_number=1, date="February 28, 2026")
        assert entry.date == "February 28, 2026"

    def test_to_markdown_header(self):
        entry = SessionEntry(session_number=1, date="February 28, 2026")
        md = entry.to_markdown()
        assert "## Session 1 — February 28, 2026" in md

    def test_to_markdown_with_tasks(self):
        pr = PRRecord(number=1, title="Add stats engine", branch="branch", url="https://github.com/pr/1")
        task = TaskRecord(
            name="Self-stats engine",
            description="Analyzes git history for stats",
            status="completed",
            pr=pr,
        )
        entry = SessionEntry(session_number=1, date="February 28, 2026", tasks=[task])
        md = entry.to_markdown()
        assert "✅ **Self-stats engine**" in md
        assert "PR #1" in md
        assert "Analyzes git history for stats" in md

    def test_to_markdown_partial_task(self):
        task = TaskRecord(name="CI pipeline", description="GitHub Actions", status="partial")
        entry = SessionEntry(session_number=1, date="Feb 28", tasks=[task])
        md = entry.to_markdown()
        assert "⚠️" in md

    def test_to_markdown_with_prs(self):
        pr = PRRecord(number=2, title="Add logger", branch="nightshift/session-1-logger", url="https://github.com/pr/2")
        entry = SessionEntry(session_number=1, date="Feb 28", prs=[pr])
        md = entry.to_markdown()
        assert "[#2](https://github.com/pr/2)" in md
        assert "Add logger" in md

    def test_to_markdown_with_decisions(self):
        entry = SessionEntry(
            session_number=1,
            date="Feb 28",
            decisions=["Used subprocess over gitpython to avoid dependencies"],
        )
        md = entry.to_markdown()
        assert "subprocess over gitpython" in md

    def test_to_markdown_with_stats_snapshot(self):
        entry = SessionEntry(
            session_number=1,
            date="Feb 28",
            stats_snapshot={"total_prs": 4, "total_commits": 25},
        )
        md = entry.to_markdown()
        assert "Total Prs: 4" in md
        assert "Total Commits: 25" in md

    def test_to_markdown_ends_with_separator(self):
        entry = SessionEntry(session_number=1, date="Feb 28")
        md = entry.to_markdown()
        assert "---" in md

    def test_to_dict_serializable(self):
        entry = SessionEntry(session_number=1, date="Feb 28", notes="First session!")
        d = entry.to_dict()
        json_str = json.dumps(d)
        loaded = json.loads(json_str)
        assert loaded["session_number"] == 1
        assert loaded["notes"] == "First session!"


# ---------------------------------------------------------------------------
# append_session_to_log
# ---------------------------------------------------------------------------


class TestAppendSessionToLog:
    def test_appends_to_existing_log(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text(textwrap.dedent("""\
            # Nightshift Log

            ## Session 0 — February 27, 2026 (Setup)

            **Operator:** Gunnar Gray (human)

            ---

            *Next entry will be written autonomously by Computer.*
        """))
        entry = SessionEntry(session_number=1, date="February 28, 2026", notes="Test run")
        result = append_session_to_log(log, entry)
        assert "## Session 1 — February 28, 2026" in result
        assert "Test run" in result
        assert result.count("## Session 1") == 1

    def test_creates_log_if_missing(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        assert not log.exists()
        entry = SessionEntry(session_number=1, date="Feb 28")
        result = append_session_to_log(log, entry)
        assert "## Session 1" in result
        assert log.exists()

    def test_dry_run_does_not_write(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text("# Log\n\n---\n\n")
        entry = SessionEntry(session_number=1, date="Feb 28")
        result = append_session_to_log(log, entry, dry_run=True)
        assert "## Session 1" in result
        assert log.read_text() == "# Log\n\n---\n\n"

    def test_appends_without_footer(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text("# Nightshift Log\n\n---\n\n## Session 0\n\n---\n")
        entry = SessionEntry(session_number=1, date="Feb 28")
        result = append_session_to_log(log, entry)
        assert "## Session 1" in result


# ---------------------------------------------------------------------------
# load_session_history
# ---------------------------------------------------------------------------


class TestLoadSessionHistory:
    def test_parses_session_headers(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text(textwrap.dedent("""\
            # Nightshift Log

            ## Session 0 — February 27, 2026

            ---

            ## Session 1 — February 28, 2026

            ---
        """))
        history = load_session_history(log)
        assert len(history) == 2
        assert history[0]["session"] == 0
        assert history[1]["session"] == 1
        assert history[1]["date"] == "February 28, 2026"

    def test_returns_empty_for_missing_file(self, tmp_path):
        result = load_session_history(tmp_path / "nonexistent.md")
        assert result == []

    def test_handles_empty_log(self, tmp_path):
        log = tmp_path / "NIGHTSHIFT_LOG.md"
        log.write_text("# Nightshift Log\n")
        result = load_session_history(log)
        assert result == []


# ---------------------------------------------------------------------------
# format_session_json
# ---------------------------------------------------------------------------


class TestFormatSessionJson:
    def test_returns_valid_json(self):
        entry = SessionEntry(session_number=1, date="Feb 28", notes="json test")
        result = format_session_json(entry)
        parsed = json.loads(result)
        assert parsed["session_number"] == 1
        assert parsed["notes"] == "json test"

    def test_includes_all_fields(self):
        pr = PRRecord(number=1, title="Test PR", branch="branch")
        task = TaskRecord(name="task", description="desc", pr=pr)
        entry = SessionEntry(
            session_number=2,
            date="March 1, 2026",
            tasks=[task],
            prs=[pr],
            decisions=["chose X over Y"],
        )
        result = format_session_json(entry)
        parsed = json.loads(result)
        assert len(parsed["tasks"]) == 1
        assert len(parsed["prs"]) == 1
        assert parsed["decisions"][0] == "chose X over Y"
