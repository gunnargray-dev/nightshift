"""Tests for the Awake changelog generator (src/changelog.py)."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from src.changelog import (
    CommitRecord,
    ChangelogSection,
    Changelog,
    SUBJECT_PATTERN,
    SESSION_PATTERN,
    _run_git,
    parse_commit_log,
    get_git_log,
    group_by_session,
    generate_changelog,
    save_changelog,
)


# ---------------------------------------------------------------------------
# CommitRecord
# ---------------------------------------------------------------------------


class TestCommitRecord:
    def test_defaults(self):
        cr = CommitRecord(
            sha="abc1234",
            subject="[awake] feat: add stats",
            commit_type="feat",
            description="add stats",
            session=1,
        )
        assert cr.sha == "abc1234"
        assert cr.commit_type == "feat"
        assert cr.session == 1
        assert cr.body == ""

    def test_to_dict(self):
        cr = CommitRecord(
            sha="abc1234",
            subject="[awake] fix: fix bug",
            commit_type="fix",
            description="fix bug",
            session=2,
            body="Session: 2",
        )
        d = cr.to_dict()
        assert d["sha"] == "abc1234"
        assert d["session"] == 2
        assert d["body"] == "Session: 2"


# ---------------------------------------------------------------------------
# ChangelogSection
# ---------------------------------------------------------------------------


class TestChangelogSection:
    def _make_commit(self, ctype: str = "feat", desc: str = "something") -> CommitRecord:
        return CommitRecord(
            sha="abc1234",
            subject=f"[awake] {ctype}: {desc}",
            commit_type=ctype,
            description=desc,
            session=1,
        )

    def test_total_commits_empty(self):
        section = ChangelogSection(session=1)
        assert section.total_commits() == 0

    def test_total_commits_counts_all(self):
        section = ChangelogSection(
            session=1,
            commits_by_type={
                "feat": [self._make_commit("feat"), self._make_commit("feat")],
                "fix": [self._make_commit("fix")],
            },
        )
        assert section.total_commits() == 3

    def test_to_dict(self):
        section = ChangelogSection(
            session=2,
            commits_by_type={"feat": [self._make_commit()]},
        )
        d = section.to_dict()
        assert d["session"] == 2
        assert "feat" in d["commits_by_type"]


# ---------------------------------------------------------------------------
# Changelog
# ---------------------------------------------------------------------------


class TestChangelog:
    def _make_section(self, session: int, types: dict[str, int]) -> ChangelogSection:
        """Build a section with N commits per type."""
        commits_by_type = {}
        for ctype, count in types.items():
            commits_by_type[ctype] = [
                CommitRecord(
                    sha=f"abc{i:04d}",
                    subject=f"[awake] {ctype}: item {i}",
                    commit_type=ctype,
                    description=f"item {i}",
                    session=session,
                )
                for i in range(count)
            ]
        return ChangelogSection(session=session, commits_by_type=commits_by_type)

    def test_empty_changelog(self):
        cl = Changelog()
        md = cl.to_markdown()
        assert "# Changelog" in md
        assert "No Awake commits found" in md

    def test_to_markdown_has_header(self):
        cl = Changelog(repo_name="awake", generated_at="2026-02-27")
        md = cl.to_markdown()
        assert "# Changelog" in md
        assert "awake" in md

    def test_to_markdown_has_generated_at(self):
        cl = Changelog(generated_at="2026-02-27 23:00 UTC")
        md = cl.to_markdown()
        assert "2026-02-27 23:00 UTC" in md

    def test_to_markdown_newest_session_first(self):
        cl = Changelog(
            sections=[
                self._make_section(1, {"feat": 1}),
                self._make_section(2, {"feat": 1}),
            ]
        )
        md = cl.to_markdown()
        idx_s2 = md.index("## Session 2")
        idx_s1 = md.index("## Session 1")
        assert idx_s2 < idx_s1

    def test_to_markdown_feat_section_label(self):
        cl = Changelog(sections=[self._make_section(1, {"feat": 2})])
        md = cl.to_markdown()
        assert "### Features" in md

    def test_to_markdown_fix_section_label(self):
        cl = Changelog(sections=[self._make_section(1, {"fix": 1})])
        md = cl.to_markdown()
        assert "### Bug Fixes" in md

    def test_to_markdown_ci_section_label(self):
        cl = Changelog(sections=[self._make_section(1, {"ci": 1})])
        md = cl.to_markdown()
        assert "### CI / Infrastructure" in md

    def test_to_markdown_sha_shortened(self):
        section = self._make_section(1, {"feat": 1})
        # Override SHA to a known value
        section.commits_by_type["feat"][0].sha = "abcdef1234567"
        cl = Changelog(sections=[section])
        md = cl.to_markdown()
        assert "`abcdef1`" in md

    def test_to_markdown_skips_empty_types(self):
        cl = Changelog(sections=[self._make_section(1, {"feat": 1})])
        md = cl.to_markdown()
        assert "### Bug Fixes" not in md

    def test_to_markdown_pre_session_label(self):
        cl = Changelog(sections=[self._make_section(0, {"meta": 1})])
        md = cl.to_markdown()
        assert "## Pre-session" in md


# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------


class TestPatterns:
    def test_subject_pattern_matches(self):
        m = SUBJECT_PATTERN.match("[awake] feat: add stats engine")
        assert m is not None
        assert m.group(1) == "feat"
        assert m.group(2) == "add stats engine"

    def test_subject_pattern_case_insensitive(self):
        m = SUBJECT_PATTERN.match("[Awake] FEAT: Add Thing")
        assert m is not None

    def test_subject_pattern_no_match_non_awake(self):
        m = SUBJECT_PATTERN.match("feat: add stats engine")
        assert m is None

    def test_session_pattern_matches(self):
        m = SESSION_PATTERN.search("Session: 3")
        assert m is not None
        assert m.group(1) == "3"

    def test_session_pattern_in_body(self):
        body = "Some body text\n\nSession: 5\n"
        m = SESSION_PATTERN.search(body)
        assert m is not None
        assert int(m.group(1)) == 5


# ---------------------------------------------------------------------------
# _run_git
# ---------------------------------------------------------------------------


class TestRunGit:
    def test_returns_empty_on_failure(self, tmp_path):
        result = _run_git(["rev-list", "--count", "HEAD"], cwd=tmp_path)
        assert result == ""

    def test_returns_empty_on_missing_git(self, tmp_path):
        with patch("src.changelog.subprocess.run", side_effect=FileNotFoundError):
            result = _run_git(["log"], cwd=tmp_path)
        assert result == ""

    def test_returns_empty_on_timeout(self, tmp_path):
        with patch(
            "src.changelog.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 30),
        ):
            result = _run_git(["log"], cwd=tmp_path)
        assert result == ""


# ---------------------------------------------------------------------------
# parse_commit_log
# ---------------------------------------------------------------------------


class TestParseCommitLog:
    def _make_raw_entry(
        self,
        sha: str = "abc1234def5678",
        subject: str = "[awake] feat: add thing",
        body: str = "Session: 1",
    ) -> str:
        return f"{sha}\x00{subject}\x00{body}\x1e"

    def test_parses_single_commit(self):
        raw = self._make_raw_entry()
        records = parse_commit_log(raw)
        assert len(records) == 1
        assert records[0].commit_type == "feat"
        assert records[0].description == "add thing"
        assert records[0].session == 1

    def test_ignores_non_awake_commits(self):
        raw = (
            self._make_raw_entry(subject="chore: cleanup") +
            self._make_raw_entry(subject="[awake] fix: bug fix")
        )
        records = parse_commit_log(raw)
        assert len(records) == 1
        assert records[0].commit_type == "fix"

    def test_session_zero_when_missing(self):
        raw = self._make_raw_entry(body="No session marker here")
        records = parse_commit_log(raw)
        assert records[0].session == 0

    def test_parses_multiple_commits(self):
        raw = (
            self._make_raw_entry(sha="aaa", subject="[awake] feat: feature A", body="Session: 1") +
            self._make_raw_entry(sha="bbb", subject="[awake] fix: fix B", body="Session: 2") +
            self._make_raw_entry(sha="ccc", subject="[awake] ci: add CI", body="Session: 1")
        )
        records = parse_commit_log(raw)
        assert len(records) == 3

    def test_strips_sha_and_subject(self):
        raw = self._make_raw_entry(sha="abc123full", subject="[awake] docs: update readme")
        records = parse_commit_log(raw)
        assert records[0].sha == "abc123full"
        assert records[0].description == "update readme"

    def test_empty_log_returns_empty_list(self):
        assert parse_commit_log("") == []

    def test_handles_entry_with_only_two_parts(self):
        raw = "abc1234\x00[awake] feat: thing\x1e"
        records = parse_commit_log(raw)
        assert len(records) == 1
        assert records[0].body == ""


# ---------------------------------------------------------------------------
# group_by_session
# ---------------------------------------------------------------------------


class TestGroupBySession:
    def _make_commit(self, ctype: str, session: int) -> CommitRecord:
        return CommitRecord(
            sha="abc1234",
            subject=f"[awake] {ctype}: thing",
            commit_type=ctype,
            description="thing",
            session=session,
        )

    def test_groups_by_session(self):
        commits = [
            self._make_commit("feat", 1),
            self._make_commit("fix", 1),
            self._make_commit("feat", 2),
        ]
        sections = group_by_session(commits)
        sessions = {s.session for s in sections}
        assert sessions == {1, 2}

    def test_groups_by_type_within_session(self):
        commits = [
            self._make_commit("feat", 1),
            self._make_commit("feat", 1),
            self._make_commit("fix", 1),
        ]
        sections = group_by_session(commits)
        assert len(sections) == 1
        section = sections[0]
        assert len(section.commits_by_type.get("feat", [])) == 2
        assert len(section.commits_by_type.get("fix", [])) == 1

    def test_empty_commits_returns_empty(self):
        assert group_by_session([]) == []


# ---------------------------------------------------------------------------
# generate_changelog (integration)
# ---------------------------------------------------------------------------


class TestGenerateChangelog:
    def test_returns_changelog_object(self, tmp_path):
        with patch("src.changelog.get_git_log", return_value=""):
            cl = generate_changelog(repo_path=tmp_path)
        assert isinstance(cl, Changelog)

    def test_timestamp_propagated(self, tmp_path):
        with patch("src.changelog.get_git_log", return_value=""):
            cl = generate_changelog(repo_path=tmp_path, timestamp="2026-02-27 23:00 UTC")
        assert cl.generated_at == "2026-02-27 23:00 UTC"

    def test_repo_name_propagated(self, tmp_path):
        with patch("src.changelog.get_git_log", return_value=""):
            cl = generate_changelog(repo_path=tmp_path, repo_name="my-repo")
        assert cl.repo_name == "my-repo"

    def test_parses_real_log(self, tmp_path):
        raw = (
            "abc1234\x00[awake] feat: add stats engine\x00Session: 1\x1e"
            "def5678\x00[awake] ci: add GitHub Actions\x00Session: 1\x1e"
        )
        with patch("src.changelog.get_git_log", return_value=raw):
            cl = generate_changelog(repo_path=tmp_path)
        assert len(cl.sections) == 1
        assert cl.sections[0].total_commits() == 2

    def test_integration_with_real_git(self, tmp_path):
        """Integration: creates a real git repo with Awake commits."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_path,
            capture_output=True,
        )
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "[awake] feat: add thing\n\nSession: 1"],
            cwd=tmp_path,
            capture_output=True,
        )
        cl = generate_changelog(repo_path=tmp_path)
        assert len(cl.sections) >= 1


# ---------------------------------------------------------------------------
# save_changelog
# ---------------------------------------------------------------------------


class TestSaveChangelog:
    def test_writes_file(self, tmp_path):
        cl = Changelog(generated_at="2026-02-27")
        out = tmp_path / "CHANGELOG.md"
        save_changelog(cl, out)
        assert out.exists()
        content = out.read_text()
        assert "# Changelog" in content

    def test_content_is_markdown(self, tmp_path):
        cl = Changelog(
            sections=[
                ChangelogSection(
                    session=1,
                    commits_by_type={
                        "feat": [
                            CommitRecord(
                                sha="abc1234",
                                subject="[awake] feat: add thing",
                                commit_type="feat",
                                description="add thing",
                                session=1,
                            )
                        ]
                    },
                )
            ],
            generated_at="2026-02-27",
        )
        out = tmp_path / "CHANGELOG.md"
        save_changelog(cl, out)
        content = out.read_text()
        assert "### Features" in content
        assert "add thing" in content
