"""Tests for src/semver.py — Session 16."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


def _import():
    from src import semver
    return semver


# ---------------------------------------------------------------------------
# _classify_commit
# ---------------------------------------------------------------------------

class TestClassifyCommit:
    def test_feat_is_minor(self):
        s = _import()
        c = s._classify_commit("abc1234", "feat: add new dashboard widget")
        assert c.commit_type == "feat"
        assert c.bump == "minor"
        assert not c.is_breaking

    def test_fix_is_patch(self):
        s = _import()
        c = s._classify_commit("abc1234", "fix: correct off-by-one in loop")
        assert c.commit_type == "fix"
        assert c.bump == "patch"

    def test_breaking_bang_is_major(self):
        s = _import()
        c = s._classify_commit("abc1234", "feat!: remove deprecated API")
        assert c.is_breaking
        assert c.bump == "major"

    def test_breaking_change_in_body(self):
        s = _import()
        c = s._classify_commit("abc1234", "BREAKING CHANGE: redesign config")
        assert c.is_breaking
        assert c.bump == "major"

    def test_chore_is_patch(self):
        s = _import()
        c = s._classify_commit("abc1234", "chore: update CI config")
        assert c.commit_type == "chore"
        assert c.bump == "patch"

    def test_scoped_commit(self):
        s = _import()
        c = s._classify_commit("abc1234", "feat(dashboard): add health tab")
        assert c.scope == "dashboard"
        assert c.commit_type == "feat"

    def test_unknown_type(self):
        s = _import()
        c = s._classify_commit("abc1234", "added a thing without prefix")
        assert c.commit_type == "unknown"
        assert c.bump == "patch"

    def test_refactor_is_patch(self):
        s = _import()
        c = s._classify_commit("abc1234", "refactor: simplify audit logic")
        assert c.commit_type == "refactor"
        assert c.bump == "patch"

    def test_description_extracted(self):
        s = _import()
        c = s._classify_commit("abc1234", "fix: correct loop boundary")
        assert c.description == "correct loop boundary"

    def test_sha_preserved(self):
        s = _import()
        c = s._classify_commit("deadbeef", "feat: something")
        assert c.sha == "deadbeef"


# ---------------------------------------------------------------------------
# _parse_version / _bump_version
# ---------------------------------------------------------------------------

class TestVersionHelpers:
    def test_parse_simple(self):
        s = _import()
        assert s._parse_version("1.2.3") == (1, 2, 3)

    def test_parse_zero(self):
        s = _import()
        assert s._parse_version("0.1.0") == (0, 1, 0)

    def test_bump_major(self):
        s = _import()
        assert s._bump_version("1.2.3", "major") == "2.0.0"

    def test_bump_minor(self):
        s = _import()
        assert s._bump_version("1.2.3", "minor") == "1.3.0"

    def test_bump_patch(self):
        s = _import()
        assert s._bump_version("1.2.3", "patch") == "1.2.4"

    def test_bump_none(self):
        s = _import()
        assert s._bump_version("1.2.3", "none") == "1.2.3"

    def test_bump_minor_resets_patch(self):
        s = _import()
        assert s._bump_version("0.5.9", "minor") == "0.6.0"


# ---------------------------------------------------------------------------
# _read_current_version
# ---------------------------------------------------------------------------

class TestReadVersion:
    def test_reads_from_pyproject(self, tmp_path):
        s = _import()
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "1.3.7"\n', encoding="utf-8"
        )
        assert s._read_current_version(tmp_path) == "1.3.7"

    def test_missing_file_defaults(self, tmp_path):
        s = _import()
        result = s._read_current_version(tmp_path)
        assert result == "0.1.0"

    def test_single_quote_version(self, tmp_path):
        s = _import()
        (tmp_path / "pyproject.toml").write_text(
            "[project]\nversion = '2.0.0'\n", encoding="utf-8"
        )
        assert s._read_current_version(tmp_path) == "2.0.0"


# ---------------------------------------------------------------------------
# _build_changelog_entry
# ---------------------------------------------------------------------------

class TestChangelogEntry:
    def test_entry_contains_version(self):
        s = _import()
        result = s._build_changelog_entry("1.0.0", [], [], [], [], [])
        assert "1.0.0" in result

    def test_entry_contains_date(self):
        import datetime
        s = _import()
        result = s._build_changelog_entry("1.0.0", [], [], [], [], [])
        today = datetime.date.today().isoformat()
        assert today in result

    def test_entry_has_features_section(self):
        s = _import()
        feat = s.CommitInfo("abc", "feat: cool thing", "feat", None, "cool thing", False, "minor")
        result = s._build_changelog_entry("1.0.0", [feat], [], [feat], [], [])
        assert "Features" in result
        assert "cool thing" in result

    def test_entry_has_breaking_section(self):
        s = _import()
        brk = s.CommitInfo("abc", "feat!: break api", "feat", None, "break api", True, "major")
        result = s._build_changelog_entry("1.0.0", [brk], [brk], [], [], [])
        assert "BREAKING" in result


# ---------------------------------------------------------------------------
# SemverBump
# ---------------------------------------------------------------------------

class TestSemverBump:
    def _make_bump(self):
        s = _import()
        commits = [
            s.CommitInfo("a1b2c3d", "feat: add predict", "feat", None, "add predict", False, "minor"),
            s.CommitInfo("e4f5a6b", "fix: null pointer", "fix", None, "null pointer", False, "patch"),
        ]
        return s.SemverBump(
            current_version="0.1.0",
            next_version="0.2.0",
            bump_type="minor",
            commits=commits,
            since_ref="v0.1.0",
            changelog_entry="## [0.2.0]\n- feat: add predict\n",
        )

    def test_features_property(self):
        b = self._make_bump()
        assert len(b.features) == 1

    def test_fixes_property(self):
        b = self._make_bump()
        assert len(b.fixes) == 1

    def test_breaking_property_empty(self):
        b = self._make_bump()
        assert len(b.breaking) == 0

    def test_to_dict_has_bump_type(self):
        b = self._make_bump()
        d = b.to_dict()
        assert d["bump_type"] == "minor"

    def test_to_json_valid(self):
        b = self._make_bump()
        parsed = json.loads(b.to_json())
        assert parsed["next_version"] == "0.2.0"

    def test_to_markdown_contains_next_version(self):
        b = self._make_bump()
        md = b.to_markdown()
        assert "0.2.0" in md

    def test_to_markdown_has_changelog_preview(self):
        b = self._make_bump()
        md = b.to_markdown()
        assert "CHANGELOG" in md


# ---------------------------------------------------------------------------
# analyze_semver (integration with mocked git)
# ---------------------------------------------------------------------------

class TestAnalyzeSemver:
    def test_no_tags_no_commits(self, tmp_path):
        s = _import()
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "0.1.0"\n', encoding="utf-8"
        )
        with patch.object(s, "_get_latest_tag", return_value=None), \
             patch.object(s, "_get_commits_since", return_value=[]):
            bump = s.analyze_semver(tmp_path)
        assert bump.current_version == "0.1.0"
        assert bump.bump_type == "none"
        assert bump.next_version == "0.1.0"

    def test_feat_commit_triggers_minor(self, tmp_path):
        s = _import()
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "1.0.0"\n', encoding="utf-8"
        )
        with patch.object(s, "_get_latest_tag", return_value="v1.0.0"), \
             patch.object(s, "_get_commits_since", return_value=[
                 ("aaa1111", "feat: add new widget"),
                 ("bbb2222", "fix: typo"),
             ]):
            bump = s.analyze_semver(tmp_path)
        assert bump.bump_type == "minor"
        assert bump.next_version == "1.1.0"

    def test_breaking_triggers_major(self, tmp_path):
        s = _import()
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "1.0.0"\n', encoding="utf-8"
        )
        with patch.object(s, "_get_latest_tag", return_value="v1.0.0"), \
             patch.object(s, "_get_commits_since", return_value=[
                 ("aaa1111", "feat!: remove legacy API"),
             ]):
            bump = s.analyze_semver(tmp_path)
        assert bump.bump_type == "major"
        assert bump.next_version == "2.0.0"


# ---------------------------------------------------------------------------
# apply_version_bump
# ---------------------------------------------------------------------------

class TestApplyVersionBump:
    def test_writes_new_version(self, tmp_path):
        s = _import()
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nversion = "0.1.0"\n', encoding="utf-8"
        )
        bump = MagicMock()
        bump.current_version = "0.1.0"
        bump.next_version = "0.2.0"
        result = s.apply_version_bump(bump, tmp_path)
        assert result is True
        content = (tmp_path / "pyproject.toml").read_text()
        assert "0.2.0" in content
        assert "0.1.0" not in content

    def test_missing_pyproject_returns_false(self, tmp_path):
        s = _import()
        bump = MagicMock()
        bump.current_version = "0.1.0"
        bump.next_version = "0.2.0"
        result = s.apply_version_bump(bump, tmp_path)
        assert result is False


# ---------------------------------------------------------------------------
# prepend_changelog_entry
# ---------------------------------------------------------------------------

class TestPrependChangelog:
    def test_creates_changelog_if_missing(self, tmp_path):
        s = _import()
        bump = MagicMock()
        bump.changelog_entry = "## [0.2.0]\n- feat: new\n"
        s.prepend_changelog_entry(bump, tmp_path)
        cl = tmp_path / "CHANGELOG.md"
        assert cl.exists()
        assert "0.2.0" in cl.read_text()

    def test_prepends_to_existing(self, tmp_path):
        s = _import()
        cl = tmp_path / "CHANGELOG.md"
        cl.write_text("# Changelog\n\nOld content\n", encoding="utf-8")
        bump = MagicMock()
        bump.changelog_entry = "## [0.2.0]\n- feat: new\n"
        s.prepend_changelog_entry(bump, tmp_path)
        content = cl.read_text()
        assert content.index("0.2.0") < content.index("Old content")
