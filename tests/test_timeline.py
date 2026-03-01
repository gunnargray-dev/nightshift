"""Tests for src/timeline.py"""
from __future__ import annotations
import json
import textwrap
from pathlib import Path
import pytest
from src.timeline import (
    SessionNode, Timeline, build_timeline, render_timeline, save_timeline,
    _parse_log, _shorten_date,
)

SAMPLE_LOG = textwrap.dedent("""\
    # Awake Log

    ## Session 1 — February 27, 2026

    **Operator:** Computer

    - ✅ Stats → PR #1 — src/stats.py
    - ✅ Logger → PR #1 — src/session_logger.py
    - ✅ CI → PR #3 — .github/workflows/ci.yml

    ## Session 2 — February 27, 2026

    - ✅ Health monitor → PR #4 — src/health.py
    - ✅ Changelog → PR #5 — src/changelog.py

    ## Session 3 — February 28, 2026

    - ✅ README updater → PR #6 — src/readme_updater.py
    - ✅ PR scorer → PR #7 — src/pr_scorer.py
    - ✅ Diff visualizer → PR #8 — src/diff_visualizer.py
"""
)

@pytest.fixture
def log_file(tmp_path):
    log = tmp_path / "AWAKE_LOG.md"
    log.write_text(SAMPLE_LOG, encoding="utf-8")
    return log

@pytest.fixture
def empty_log(tmp_path):
    log = tmp_path / "AWAKE_LOG.md"
    log.write_text("# Awake Log\n\nNo sessions yet.\n", encoding="utf-8")
    return log

class TestShortenDate:
    def test_february(self):
        assert "Feb" in _shorten_date("February 27, 2026")
        assert "27" in _shorten_date("February 27, 2026")
    def test_january(self):
        assert "Jan" in _shorten_date("January 1, 2026")
    def test_already_short(self):
        assert len(_shorten_date("Feb 27")) <= 8
    def test_unknown_format(self):
        assert len(_shorten_date("2026-02-27")) <= 8

class TestParseLog:
    def test_returns_list(self, log_file):
        assert isinstance(_parse_log(log_file), list)
    def test_correct_session_count(self, log_file):
        assert len(_parse_log(log_file)) == 3
    def test_session_numbers(self, log_file):
        assert [n.session_number for n in _parse_log(log_file)] == [1, 2, 3]
    def test_dates_parsed(self, log_file):
        for node in _parse_log(log_file):
            assert node.date != ""
    def test_pr_counts_extracted(self, log_file):
        assert _parse_log(log_file)[0].pr_count >= 2
    def test_cumulative_prs_monotonic(self, log_file):
        nodes = _parse_log(log_file)
        for i in range(1, len(nodes)):
            assert nodes[i].cumulative_prs >= nodes[i-1].cumulative_prs
    def test_missing_log_returns_empty(self, tmp_path):
        assert _parse_log(tmp_path / "nonexistent.md") == []
    def test_empty_log_returns_empty(self, empty_log):
        assert _parse_log(empty_log) == []

class TestSessionNode:
    def test_to_dict(self):
        node = SessionNode(session_number=1, date="Feb 27, 2026", pr_count=3, task_count=2)
        d = node.to_dict()
        assert d["session_number"] == 1
        assert d["pr_count"] == 3
    def test_defaults(self):
        node = SessionNode(session_number=5, date="", pr_count=0, task_count=0)
        assert node.tasks == []
        assert node.cumulative_prs == 0

class TestTimeline:
    def test_to_dict(self, log_file):
        d = build_timeline(log_path=log_file).to_dict()
        assert "sessions" in d and "total_prs" in d
    def test_total_sessions(self, log_file):
        assert build_timeline(log_path=log_file).total_sessions == 3
    def test_total_prs_positive(self, log_file):
        assert build_timeline(log_path=log_file).total_prs > 0
    def test_first_and_latest_dates_set(self, log_file):
        tl = build_timeline(log_path=log_file)
        assert tl.first_session_date != "" and tl.latest_session_date != ""
    def test_to_json(self, log_file):
        assert "sessions" in json.loads(build_timeline(log_path=log_file).to_json())
    def test_empty_timeline(self, empty_log):
        tl = build_timeline(log_path=empty_log)
        assert tl.total_sessions == 0 and tl.total_prs == 0

class TestBuildTimeline:
    def test_with_explicit_log_path(self, log_file):
        assert len(build_timeline(log_path=log_file).sessions) == 3
    def test_with_repo_path(self, log_file):
        assert len(build_timeline(repo_path=log_file.parent).sessions) == 3
    def test_missing_log_returns_empty_timeline(self, tmp_path):
        assert build_timeline(log_path=tmp_path / "nonexistent.md").total_sessions == 0

class TestRenderTimeline:
    def test_returns_string(self, log_file):
        assert isinstance(render_timeline(build_timeline(log_path=log_file)), str)
    def test_contains_header(self, log_file):
        md = render_timeline(build_timeline(log_path=log_file))
        assert "Awake" in md and "Timeline" in md
    def test_contains_session_sections(self, log_file):
        md = render_timeline(build_timeline(log_path=log_file))
        assert "Session 1" in md and "Session 2" in md and "Session 3" in md
    def test_contains_session_details_header(self, log_file):
        assert "Session Details" in render_timeline(build_timeline(log_path=log_file))
    def test_contains_ascii_block(self, log_file):
        assert "```" in render_timeline(build_timeline(log_path=log_file))
    def test_empty_timeline_handled(self, empty_log):
        assert "No sessions" in render_timeline(build_timeline(log_path=empty_log))
    def test_to_markdown_delegates_to_render(self, log_file):
        tl = build_timeline(log_path=log_file)
        assert tl.to_markdown() == render_timeline(tl)

class TestSaveTimeline:
    def test_creates_md_file(self, log_file, tmp_path):
        out = tmp_path / "timeline.md"
        save_timeline(build_timeline(log_path=log_file), out)
        assert out.exists() and "Session" in out.read_text()
    def test_creates_json_sidecar(self, log_file, tmp_path):
        out = tmp_path / "timeline.md"
        save_timeline(build_timeline(log_path=log_file), out)
        assert "sessions" in json.loads((tmp_path / "timeline.json").read_text())
    def test_creates_parent_dirs(self, log_file, tmp_path):
        out = tmp_path / "sub" / "timeline.md"
        save_timeline(build_timeline(log_path=log_file), out)
        assert out.exists()

class TestIntegration:
    def test_full_pipeline(self, log_file, tmp_path):
        tl = build_timeline(log_path=log_file)
        assert tl.total_sessions == 3
        assert len(tl.to_markdown()) > 100
        out = tmp_path / "timeline.md"
        save_timeline(tl, out)
        assert out.exists()
    def test_real_repo_log(self):
        repo_root = Path(__file__).resolve().parent.parent
        log_path = repo_root / "AWAKE_LOG.md"
        if not log_path.exists():
            pytest.skip("AWAKE_LOG.md not found")
        tl = build_timeline(log_path=log_path)
        assert tl.total_sessions >= 1
        assert "Session" in tl.to_markdown()
