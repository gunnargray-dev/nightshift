"""Tests for src/story.py — Repo Story generator."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.story import (
    SessionChapter,
    RepoStory,
    generate_story,
    save_story,
    _split_sessions,
    _extract_features,
    _extract_decisions,
    _extract_theme,
    _generate_chapter_narrative,
    _build_prologue,
    _build_epilogue,
    _parse_int,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_LOG = """\
# Awake Log

Maintained autonomously.

---

## Session 1 — February 27, 2026

**Operator:** Computer (autonomous)  

**Tasks completed:**

- ✅ **Self-stats engine** → [PR #1](https://github.com/gunnargray-dev/awake/pull/1) — `src/stats.py`: analyzes git history.
- ✅ **Session logger** → [PR #1](https://github.com/gunnargray-dev/awake/pull/1) — `src/session_logger.py`: structured entries.

**Pull requests:**

- [#1](https://github.com/gunnargray-dev/awake/pull/1) — feat: stats engine

**Decisions & rationale:**

- Used subprocess over gitpython to keep zero runtime dependencies.
- Kept CI workflow minimal for session 1.

**Stats snapshot:**

- Total PRs: 3
- Lines changed: ~700

**Notes:** First autonomous session.

---

## Session 2 — February 27, 2026

**Operator:** Computer (autonomous)  

**Tasks completed:**

- ✅ **Code health monitor** → [PR #4](https://github.com/gunnargray-dev/awake/pull/4) — `src/health.py`: AST-based analyzer.
- ✅ **Changelog generator** → [PR #5](https://github.com/gunnargray-dev/awake/pull/5) — `src/changelog.py`: git history.

**Decisions & rationale:**

- Health scoring is AST-based to enable robust long-term extension.

**Stats snapshot:**

- Total PRs: 6
- Lines changed: ~1800
- Test suite: 150 tests

**Notes:** Session 2 theme: instrumentation. The system can now measure itself.

---

## Session 3 — February 28, 2026

**Operator:** Computer (autonomous)  

**Tasks completed:**

- ✅ **README auto-updater** → [PR #7](https://github.com/gunnargray-dev/awake/pull/7) — `src/readme_updater.py`: dynamic README.
- ✅ **Session diff visualizer** → [PR #8](https://github.com/gunnargray-dev/awake/pull/8) — `src/diff_visualizer.py`.
- ✅ **PR quality scorer** → [PR #9](https://github.com/gunnargray-dev/awake/pull/9) — `src/pr_scorer.py`.

**Decisions & rationale:**

- README is generated from repo state to stay accurate.

**Stats snapshot:**

- Total PRs: 9
- Lines changed: ~3000
- Test suite: 300 tests

**Notes:** Session 3 theme: automation.

---
"""


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    p = tmp_path / "AWAKE_LOG.md"
    p.write_text(SAMPLE_LOG, encoding="utf-8")
    return p


@pytest.fixture()
def repo_with_log(tmp_path: Path, log_file: Path) -> Path:
    """A tmp repo root with a AWAKE_LOG.md."""
    return tmp_path


# ---------------------------------------------------------------------------
# _parse_int
# ---------------------------------------------------------------------------


def test_parse_int_plain():
    assert _parse_int("123") == 123


def test_parse_int_with_tilde():
    assert _parse_int("~700") == 700


def test_parse_int_with_comma():
    assert _parse_int("1,200") == 1200


def test_parse_int_empty():
    assert _parse_int("") == 0


def test_parse_int_non_numeric():
    assert _parse_int("abc") == 0


# ---------------------------------------------------------------------------
# _split_sessions
# ---------------------------------------------------------------------------


def test_split_sessions_count():
    sections = _split_sessions(SAMPLE_LOG)
    assert len(sections) == 3


def test_split_sessions_numbers():
    sections = _split_sessions(SAMPLE_LOG)
    assert [s[0] for s in sections] == [1, 2, 3]


def test_split_sessions_dates():
    sections = _split_sessions(SAMPLE_LOG)
    assert sections[0][1] == "February 27, 2026"
    assert sections[2][1] == "February 28, 2026"


def test_split_sessions_content_not_empty():
    sections = _split_sessions(SAMPLE_LOG)
    for _, _, text in sections:
        assert len(text) > 10


def test_split_sessions_empty_log():
    assert _split_sessions("# Awake Log\n\nNo sessions yet.\n") == []


# ---------------------------------------------------------------------------
# _extract_features
# ---------------------------------------------------------------------------


def test_extract_features_session1():
    sections = _split_sessions(SAMPLE_LOG)
    features = _extract_features(sections[0][2])
    assert "Self-stats engine" in features
    assert "Session logger" in features


def test_extract_features_session3():
    sections = _split_sessions(SAMPLE_LOG)
    features = _extract_features(sections[2][2])
    assert len(features) == 3


def test_extract_features_no_tasks():
    section = "## Session 1 — Feb 1, 2026\n\nNo tasks listed.\n"
    assert _extract_features(section) == []


# ---------------------------------------------------------------------------
# _extract_decisions
# ---------------------------------------------------------------------------


def test_extract_decisions_nonempty():
    sections = _split_sessions(SAMPLE_LOG)
    decisions = _extract_decisions(sections[0][2])
    assert len(decisions) >= 1
    assert any("subprocess" in d or "gitpython" in d for d in decisions)


def test_extract_decisions_empty_section():
    assert _extract_decisions("## Session 1 — Feb 1, 2026\n") == []


# ---------------------------------------------------------------------------
# _extract_theme
# ---------------------------------------------------------------------------


def test_extract_theme_from_notes():
    sections = _split_sessions(SAMPLE_LOG)
    theme = _extract_theme(sections[1][2], ["Code health monitor"])
    assert "Instrumentation" in theme or "instrumentation" in theme.lower()


def test_extract_theme_fallback_to_feature():
    theme = _extract_theme("## Session 99 — Jan 1, 2025\n", ["My Feature"])
    assert theme == "My Feature"


def test_extract_theme_fallback_default():
    theme = _extract_theme("## Session 99 — Jan 1, 2025\n", [])
    assert "Advances" in theme or "Session" in theme


# ---------------------------------------------------------------------------
# _generate_chapter_narrative
# ---------------------------------------------------------------------------


def test_narrative_contains_feature():
    narrative = _generate_chapter_narrative(
        session_number=1,
        date="February 27, 2026",
        theme="Foundation",
        features=["Self-stats engine", "Session logger"],
        decisions=["Used subprocess over gitpython."],
        pr_count=3,
        lines_changed=700,
        test_count_delta=50,
    )
    assert "Self-stats engine" in narrative or "Session logger" in narrative


def test_narrative_single_feature():
    narrative = _generate_chapter_narrative(
        session_number=2,
        date="February 27, 2026",
        theme="Health",
        features=["Health monitor"],
        decisions=[],
        pr_count=1,
        lines_changed=500,
        test_count_delta=0,
    )
    assert "Health monitor" in narrative


def test_narrative_no_features():
    narrative = _generate_chapter_narrative(
        session_number=5,
        date="Feb 1, 2026",
        theme="Misc",
        features=[],
        decisions=[],
        pr_count=0,
        lines_changed=0,
        test_count_delta=0,
    )
    assert len(narrative) > 10


def test_narrative_many_features():
    features = ["A", "B", "C", "D", "E"]
    narrative = _generate_chapter_narrative(
        session_number=10,
        date="Feb 10, 2026",
        theme="Big session",
        features=features,
        decisions=[],
        pr_count=5,
        lines_changed=2000,
        test_count_delta=100,
    )
    assert str(len(features)) in narrative


# ---------------------------------------------------------------------------
# _build_prologue / _build_epilogue
# ---------------------------------------------------------------------------


def test_prologue_contains_repo_name():
    prologue = _build_prologue("Awake", 13, 35)
    assert "Awake" in prologue


def test_prologue_mentions_sessions():
    prologue = _build_prologue("Awake", 13, 35)
    assert "13" in prologue


def test_epilogue_contains_stats():
    chapters = [
        SessionChapter(1, "Feb 1", "Foundation", ["A", "B"], 3, 50, 700, []),
        SessionChapter(2, "Feb 2", "Health", ["C"], 1, 30, 400, []),
    ]
    epilogue = _build_epilogue("Awake", chapters, 1200, 35)
    assert "1,200" in epilogue or "1200" in epilogue


def test_epilogue_story_arc():
    chapters = [SessionChapter(1, "Feb 1", "Foundation", [], 0, 0, 0, [])]
    epilogue = _build_epilogue("Awake", chapters, 500, 10)
    assert "session" in epilogue.lower()


# ---------------------------------------------------------------------------
# generate_story
# ---------------------------------------------------------------------------


def test_generate_story_session_count(repo_with_log: Path):
    story = generate_story(repo_with_log)
    assert story.total_sessions == 3


def test_generate_story_chapter_order(repo_with_log: Path):
    story = generate_story(repo_with_log)
    numbers = [c.session_number for c in story.chapters]
    assert numbers == sorted(numbers)


def test_generate_story_chapters_have_narrative(repo_with_log: Path):
    story = generate_story(repo_with_log)
    for chapter in story.chapters:
        assert len(chapter.narrative) > 20


def test_generate_story_has_prologue(repo_with_log: Path):
    story = generate_story(repo_with_log)
    assert len(story.prologue) > 50


def test_generate_story_has_epilogue(repo_with_log: Path):
    story = generate_story(repo_with_log)
    assert len(story.epilogue) > 50


def test_generate_story_no_log(tmp_path: Path):
    story = generate_story(tmp_path)
    assert story.total_sessions == 0
    assert "No session history" in story.prologue


def test_generate_story_pr_counts(repo_with_log: Path):
    story = generate_story(repo_with_log)
    # Total PRs should reflect last cumulative snapshot
    assert story.total_prs >= 3


def test_generate_story_test_counts(repo_with_log: Path):
    story = generate_story(repo_with_log)
    assert story.total_tests >= 0


# ---------------------------------------------------------------------------
# RepoStory.to_markdown
# ---------------------------------------------------------------------------


def test_to_markdown_has_title(repo_with_log: Path):
    story = generate_story(repo_with_log)
    md = story.to_markdown()
    assert "# " in md
    assert "Story" in md or "awake" in md.lower()


def test_to_markdown_has_all_chapters(repo_with_log: Path):
    story = generate_story(repo_with_log)
    md = story.to_markdown()
    for i in range(1, 4):
        assert f"Chapter {i}" in md


def test_to_markdown_has_stats_table(repo_with_log: Path):
    story = generate_story(repo_with_log)
    md = story.to_markdown()
    assert "By the Numbers" in md


def test_to_markdown_features_listed(repo_with_log: Path):
    story = generate_story(repo_with_log)
    md = story.to_markdown()
    assert "Self-stats engine" in md or "stats engine" in md.lower()


def test_to_json_valid(repo_with_log: Path):
    story = generate_story(repo_with_log)
    data = json.loads(story.to_json())
    assert "chapters" in data
    assert "total_sessions" in data
    assert data["total_sessions"] == 3


def test_to_json_chapters_have_fields(repo_with_log: Path):
    story = generate_story(repo_with_log)
    data = json.loads(story.to_json())
    for chap in data["chapters"]:
        assert "session_number" in chap
        assert "narrative" in chap
        assert "theme" in chap


# ---------------------------------------------------------------------------
# SessionChapter
# ---------------------------------------------------------------------------


def test_session_chapter_to_dict():
    chap = SessionChapter(
        session_number=1,
        date="Feb 1, 2026",
        theme="Foundation",
        features=["A"],
        pr_count=3,
        test_count=50,
        lines_changed=700,
        decisions=["Used subprocess."],
        narrative="The first session.",
    )
    d = chap.to_dict()
    assert d["session_number"] == 1
    assert d["theme"] == "Foundation"
    assert d["narrative"] == "The first session."


# ---------------------------------------------------------------------------
# save_story
# ---------------------------------------------------------------------------


def test_save_story_writes_md(tmp_path: Path, repo_with_log: Path):
    story = generate_story(repo_with_log)
    out = tmp_path / "docs" / "story.md"
    save_story(story, out)
    assert out.exists()
    content = out.read_text()
    assert "Chapter" in content


def test_save_story_writes_json_sidecar(tmp_path: Path, repo_with_log: Path):
    story = generate_story(repo_with_log)
    out = tmp_path / "docs" / "story.md"
    save_story(story, out)
    json_out = out.with_suffix(".json")
    assert json_out.exists()
    data = json.loads(json_out.read_text())
    assert "chapters" in data


def test_save_story_creates_parent_dir(tmp_path: Path, repo_with_log: Path):
    story = generate_story(repo_with_log)
    out = tmp_path / "new_dir" / "story.md"
    save_story(story, out)
    assert out.parent.exists()
