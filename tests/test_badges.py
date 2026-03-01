"""Tests for src/badges.py — Automated README Badge Generator."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from src.badges import (
    Badge,
    BadgeBlock,
    generate_badges,
    save_badges_report,
    write_badges_to_readme,
    _shields_static,
    _grade_color,
    _score_color,
    _get_session_count,
    _get_test_count,
    _get_module_count,
)


class TestUtilityFunctions:
    def test_grade_color_a(self):
        assert _grade_color("A+") == "brightgreen"
        assert _grade_color("A") == "brightgreen"

    def test_grade_color_b(self):
        assert _grade_color("B") == "green"

    def test_grade_color_c(self):
        assert _grade_color("C") == "yellow"

    def test_grade_color_d(self):
        assert _grade_color("D") == "orange"

    def test_grade_color_f(self):
        assert _grade_color("F") == "red"
        assert _grade_color("E") == "red"

    def test_score_color_high(self):
        assert _score_color(85.0) == "brightgreen"

    def test_score_color_medium_high(self):
        assert _score_color(70.0) == "green"

    def test_score_color_medium(self):
        assert _score_color(55.0) == "yellow"

    def test_score_color_low(self):
        assert _score_color(40.0) == "orange"

    def test_score_color_critical(self):
        assert _score_color(20.0) == "red"

    def test_shields_static_returns_markdown(self):
        md = _shields_static("tests", "1000", "brightgreen")
        assert "img.shields.io/badge/" in md
        assert "tests" in md
        assert "1000" in md


class TestBadge:
    def test_basic_construction(self):
        b = Badge(label="sessions", message="15", color="blueviolet")
        assert b.label == "sessions"
        assert b.message == "15"
        assert b.color == "blueviolet"

    def test_to_markdown_contains_shields_url(self):
        b = Badge(label="sessions", message="15", color="blueviolet", alt="Sessions")
        md = b.to_markdown()
        assert "img.shields.io/badge/" in md
        assert "Sessions" in md

    def test_to_markdown_url_encoded(self):
        b = Badge(label="test count", message="1,000", color="green")
        md = b.to_markdown()
        assert " " not in md or "%20" in md

    def test_to_dict(self):
        b = Badge(label="health", message="85/100", color="brightgreen")
        d = b.to_dict()
        assert d["label"] == "health"
        assert d["message"] == "85/100"
        assert d["color"] == "brightgreen"

    def test_alt_defaults_to_label(self):
        b = Badge(label="security", message="A+", color="brightgreen")
        md = b.to_markdown()
        assert "security" in md


class TestBadgeBlock:
    def _make_block(self) -> BadgeBlock:
        return BadgeBlock(
            badges=[
                Badge(label="sessions", message="15", color="blueviolet"),
                Badge(label="tests", message="1,500", color="brightgreen"),
                Badge(label="health", message="85/100", color="brightgreen"),
            ],
            generated_at="2026-02-28",
        )

    def test_to_markdown_contains_all_badges(self):
        block = self._make_block()
        md = block.to_markdown()
        assert "sessions" in md
        assert "tests" in md
        assert "health" in md

    def test_to_markdown_block_ends_with_newline(self):
        block = self._make_block()
        md = block.to_markdown_block()
        assert md.endswith("\n")

    def test_to_json_valid(self):
        block = self._make_block()
        data = json.loads(block.to_json())
        assert "badges" in data
        assert len(data["badges"]) == 3
        assert data["generated_at"] == "2026-02-28"

    def test_to_dict_structure(self):
        block = self._make_block()
        d = block.to_dict()
        assert "badges" in d
        assert "generated_at" in d

    def test_empty_block(self):
        block = BadgeBlock()
        md = block.to_markdown()
        assert isinstance(md, str)


class TestMetricExtractors:
    def test_get_session_count_no_file(self, tmp_path):
        count = _get_session_count(tmp_path)
        assert count == 0

    def test_get_session_count_from_log(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text("## Session 1\n\n## Session 2\n\n## Session 3\n")
        count = _get_session_count(tmp_path)
        assert count == 3

    def test_get_test_count_no_tests(self, tmp_path):
        (tmp_path / "tests").mkdir()
        count = _get_test_count(tmp_path)
        assert count == 0

    def test_get_test_count_with_tests(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text(
            "def test_one(): pass\ndef test_two(): pass\ndef helper(): pass\n"
        )
        count = _get_test_count(tmp_path)
        assert count == 2

    def test_get_module_count_no_src(self, tmp_path):
        count = _get_module_count(tmp_path)
        assert count == 0

    def test_get_module_count_with_src(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        for name in ["health.py", "stats.py", "cli.py", "__init__.py"]:
            (src / name).write_text("# module")
        count = _get_module_count(tmp_path)
        assert count == 3


class TestGenerateBadges:
    def test_returns_badge_block(self, tmp_path):
        block = generate_badges(repo_path=tmp_path)
        assert isinstance(block, BadgeBlock)

    def test_always_has_at_least_one_badge(self, tmp_path):
        block = generate_badges(repo_path=tmp_path)
        assert len(block.badges) >= 1

    def test_session_badge_present_when_log_exists(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text("## Session 1\n\n## Session 2\n")
        block = generate_badges(repo_path=tmp_path)
        labels = [b.label for b in block.badges]
        assert "sessions" in labels

    def test_test_badge_present_when_tests_exist(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text("def test_a(): pass\ndef test_b(): pass\n")
        block = generate_badges(repo_path=tmp_path)
        labels = [b.label for b in block.badges]
        assert "tests" in labels

    def test_python_badge_always_present(self, tmp_path):
        block = generate_badges(repo_path=tmp_path)
        labels = [b.label for b in block.badges]
        assert "python" in labels

    def test_license_badge_always_present(self, tmp_path):
        block = generate_badges(repo_path=tmp_path)
        labels = [b.label for b in block.badges]
        assert "license" in labels

    def test_has_generated_at(self, tmp_path):
        block = generate_badges(repo_path=tmp_path)
        assert block.generated_at != ""


class TestWriteBadgesToReadme:
    def _make_block(self) -> BadgeBlock:
        return BadgeBlock(badges=[Badge(label="sessions", message="15", color="blueviolet")])

    def test_no_readme_returns_false(self, tmp_path):
        block = self._make_block()
        result = write_badges_to_readme(block, repo_path=tmp_path)
        assert result is False

    def test_inserts_after_h1(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# My Project\n\nSome text here.\n")
        block = self._make_block()
        result = write_badges_to_readme(block, repo_path=tmp_path)
        assert result is True
        text = readme.read_text()
        assert "img.shields.io" in text

    def test_replaces_existing_markers(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("# My Project\n<!-- badges:start -->\nOLD BADGES\n<!-- badges:end -->\n")
        block = self._make_block()
        result = write_badges_to_readme(block, repo_path=tmp_path)
        assert result is True
        text = readme.read_text()
        assert "OLD BADGES" not in text
        assert "img.shields.io" in text
        assert "<!-- badges:start -->" in text
        assert "<!-- badges:end -->" in text

    def test_readme_without_h1_returns_false(self, tmp_path):
        readme = tmp_path / "README.md"
        readme.write_text("Just some text without a heading.\n")
        block = self._make_block()
        result = write_badges_to_readme(block, repo_path=tmp_path)
        assert result is False


class TestSaveBadgesReport:
    def test_creates_md_and_json(self, tmp_path):
        block = BadgeBlock(
            badges=[Badge(label="tests", message="1500", color="brightgreen")],
            generated_at="2026-02-28",
        )
        out = tmp_path / "badges.md"
        save_badges_report(block, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_markdown_has_badge_table(self, tmp_path):
        block = BadgeBlock(badges=[Badge(label="health", message="80/100", color="green")])
        out = tmp_path / "badges.md"
        save_badges_report(block, out)
        text = out.read_text()
        assert "health" in text

    def test_json_valid(self, tmp_path):
        block = BadgeBlock(
            badges=[Badge(label="security", message="A+", color="brightgreen")],
            generated_at="2026-02-28",
        )
        out = tmp_path / "badges.md"
        save_badges_report(block, out)
        data = json.loads(out.with_suffix(".json").read_text())
        assert data["generated_at"] == "2026-02-28"
        assert len(data["badges"]) == 1
