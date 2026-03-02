"""Tests for the README session-log updater."""

import pytest

from src.readme_updater import (
    SessionSummary,
    parse_session_log,
    render_session_log,
    update_readme,
    write_readme,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_readme():
    return """# My Project

Some intro text.

## Session Log

### 2025-03-01
- Added feature X
- Fixed bug Y

2 tests added, 1 PRs merged

### 2025-02-15
- Initial setup

3 tests added
"""


@pytest.fixture
def readme_no_session(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# Project\n\nNo session log yet.\n")
    return str(p)


@pytest.fixture
def readme_with_session(tmp_path, simple_readme):
    p = tmp_path / "README.md"
    p.write_text(simple_readme)
    return str(p)


# ---------------------------------------------------------------------------
# parse_session_log
# ---------------------------------------------------------------------------


class TestParseSessionLog:
    def test_parses_two_sessions(self, simple_readme):
        sessions = parse_session_log(simple_readme)
        assert len(sessions) == 2

    def test_dates_correct(self, simple_readme):
        sessions = parse_session_log(simple_readme)
        dates = {s.date for s in sessions}
        assert "2025-03-01" in dates
        assert "2025-02-15" in dates

    def test_features_extracted(self, simple_readme):
        sessions = parse_session_log(simple_readme)
        march = next(s for s in sessions if s.date == "2025-03-01")
        assert "Added feature X" in march.features
        assert "Fixed bug Y" in march.features

    def test_tests_added_parsed(self, simple_readme):
        sessions = parse_session_log(simple_readme)
        march = next(s for s in sessions if s.date == "2025-03-01")
        assert march.tests_added == 2

    def test_prs_merged_parsed(self, simple_readme):
        sessions = parse_session_log(simple_readme)
        march = next(s for s in sessions if s.date == "2025-03-01")
        assert march.prs_merged == 1

    def test_no_session_section_returns_empty(self):
        content = "# Just a readme\n\nNo sessions here.\n"
        assert parse_session_log(content) == []


# ---------------------------------------------------------------------------
# render_session_log
# ---------------------------------------------------------------------------


class TestRenderSessionLog:
    def test_newest_first(self):
        sessions = [
            SessionSummary(date="2025-01-01", features=[], tests_added=0, prs_merged=0),
            SessionSummary(date="2025-03-01", features=[], tests_added=0, prs_merged=0),
        ]
        rendered = render_session_log(sessions)
        assert rendered.index("2025-03-01") < rendered.index("2025-01-01")

    def test_contains_section_header(self):
        rendered = render_session_log([])
        assert "Session Log" in rendered

    def test_features_rendered(self):
        sessions = [
            SessionSummary(
                date="2025-06-01",
                features=["feat A", "feat B"],
                tests_added=0,
                prs_merged=0,
            )
        ]
        rendered = render_session_log(sessions)
        assert "feat A" in rendered
        assert "feat B" in rendered

    def test_meta_rendered(self):
        sessions = [
            SessionSummary(
                date="2025-06-01",
                features=[],
                tests_added=5,
                prs_merged=2,
            )
        ]
        rendered = render_session_log(sessions)
        assert "5 tests added" in rendered
        assert "2 PRs merged" in rendered

    def test_notes_rendered(self):
        sessions = [
            SessionSummary(
                date="2025-06-01",
                features=[],
                tests_added=0,
                prs_merged=0,
                notes="Experimental night",
            )
        ]
        rendered = render_session_log(sessions)
        assert "Experimental night" in rendered


# ---------------------------------------------------------------------------
# update_readme
# ---------------------------------------------------------------------------


class TestUpdateReadme:
    def test_adds_new_session_to_existing_section(self, readme_with_session):
        new_session = SessionSummary(
            date="2025-04-01",
            features=["new feature"],
            tests_added=3,
            prs_merged=1,
        )
        result = update_readme(readme_with_session, new_session)
        assert "2025-04-01" in result
        assert "new feature" in result

    def test_replaces_session_with_same_date(self, readme_with_session):
        replacement = SessionSummary(
            date="2025-03-01",
            features=["replaced feature"],
            tests_added=99,
            prs_merged=5,
        )
        result = update_readme(readme_with_session, replacement)
        assert "replaced feature" in result
        # Original feature for 2025-03-01 should be gone
        assert "Added feature X" not in result

    def test_creates_section_when_missing(self, readme_no_session):
        new_session = SessionSummary(
            date="2025-05-01",
            features=["bootstrap"],
            tests_added=1,
            prs_merged=0,
        )
        result = update_readme(readme_no_session, new_session)
        assert "Session Log" in result
        assert "bootstrap" in result

    def test_no_section_created_when_flag_false(self, readme_no_session):
        new_session = SessionSummary(
            date="2025-05-01",
            features=["x"],
            tests_added=0,
            prs_merged=0,
        )
        result = update_readme(
            readme_no_session, new_session, create_section_if_missing=False
        )
        assert "Session Log" not in result

    def test_preserves_content_before_section(self, readme_with_session):
        new_session = SessionSummary(
            date="2025-04-01",
            features=[],
            tests_added=0,
            prs_merged=0,
        )
        result = update_readme(readme_with_session, new_session)
        assert "Some intro text" in result

    def test_existing_sessions_preserved(self, readme_with_session):
        new_session = SessionSummary(
            date="2025-04-01",
            features=["new"],
            tests_added=0,
            prs_merged=0,
        )
        result = update_readme(readme_with_session, new_session)
        assert "2025-02-15" in result


# ---------------------------------------------------------------------------
# write_readme (file I/O)
# ---------------------------------------------------------------------------


class TestWriteReadme:
    def test_writes_file(self, tmp_path):
        p = tmp_path / "README.md"
        p.write_text("# Hello\n")
        new_session = SessionSummary(
            date="2025-07-01",
            features=["written"],
            tests_added=2,
            prs_merged=1,
        )
        write_readme(str(p), new_session)
        content = p.read_text()
        assert "written" in content

    def test_file_created_when_missing(self, tmp_path):
        p = tmp_path / "NEW_README.md"
        new_session = SessionSummary(
            date="2025-07-01",
            features=["brand new"],
            tests_added=0,
            prs_merged=0,
        )
        write_readme(str(p), new_session)
        assert p.exists()
        assert "brand new" in p.read_text()
