"""Tests for src/blame.py — Git blame attribution module."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.blame import (
    FileBlame,
    BlameReport,
    _is_ai_author,
    _blame_file,
    analyze_blame,
    save_blame_report,
)


# ---------------------------------------------------------------------------
# _is_ai_author
# ---------------------------------------------------------------------------

class TestIsAiAuthor:
    def test_computer_is_ai(self):
        assert _is_ai_author("Computer") is True

    def test_computer_lowercase(self):
        assert _is_ai_author("computer") is True

    def test_nightshift_is_ai(self):
        assert _is_ai_author("nightshift-bot") is True

    def test_perplexity_email_is_ai(self):
        assert _is_ai_author("gunnar@perplexity.ai") is True

    def test_human_name_not_ai(self):
        assert _is_ai_author("Alice Smith") is False

    def test_random_email_not_ai(self):
        assert _is_ai_author("dev@example.com") is False

    def test_empty_string_not_ai(self):
        assert _is_ai_author("") is False


# ---------------------------------------------------------------------------
# FileBlame
# ---------------------------------------------------------------------------

class TestFileBlame:
    def _make(self, ai=60, human=40) -> FileBlame:
        fb = FileBlame(path="src/foo.py")
        fb.total_lines = ai + human
        fb.ai_lines = ai
        fb.human_lines = human
        fb.ai_authors = ["Computer"] * ai
        fb.human_authors = ["Alice"] * human
        return fb

    def test_ai_pct(self):
        fb = self._make(ai=60, human=40)
        assert fb.ai_pct == 60.0

    def test_human_pct(self):
        fb = self._make(ai=60, human=40)
        assert fb.human_pct == 40.0

    def test_zero_total_lines(self):
        fb = FileBlame(path="src/empty.py")
        assert fb.ai_pct == 0.0
        assert fb.human_pct == 0.0

    def test_to_dict_keys(self):
        fb = self._make()
        d = fb.to_dict()
        assert "ai_pct" in d
        assert "human_pct" in d
        assert "ai_authors" in d
        assert "human_authors" in d

    def test_to_dict_authors_deduped(self):
        fb = self._make(ai=5, human=3)
        d = fb.to_dict()
        # Authors list should contain unique values only
        assert d["ai_authors"] == ["Computer"]
        assert d["human_authors"] == ["Alice"]


# ---------------------------------------------------------------------------
# BlameReport
# ---------------------------------------------------------------------------

class TestBlameReport:
    def _make_report(self) -> BlameReport:
        rpt = BlameReport(repo_path="/tmp/repo")
        fb1 = FileBlame(path="src/a.py")
        fb1.total_lines = 100
        fb1.ai_lines = 80
        fb1.human_lines = 20
        fb1.ai_authors = ["Computer"]
        fb1.human_authors = ["Bob"]
        fb2 = FileBlame(path="src/b.py")
        fb2.total_lines = 50
        fb2.ai_lines = 10
        fb2.human_lines = 40
        fb2.ai_authors = ["Computer"]
        fb2.human_authors = ["Bob"]
        rpt.files = [fb1, fb2]
        return rpt

    def test_total_lines(self):
        rpt = self._make_report()
        assert rpt.total_lines == 150

    def test_total_ai_lines(self):
        rpt = self._make_report()
        assert rpt.total_ai_lines == 90

    def test_total_human_lines(self):
        rpt = self._make_report()
        assert rpt.total_human_lines == 60

    def test_repo_ai_pct(self):
        rpt = self._make_report()
        assert rpt.repo_ai_pct == 60.0

    def test_repo_human_pct(self):
        rpt = self._make_report()
        assert rpt.repo_human_pct == 40.0

    def test_unique_human_authors(self):
        rpt = self._make_report()
        assert rpt.unique_human_authors == ["Bob"]

    def test_unique_ai_authors(self):
        rpt = self._make_report()
        assert rpt.unique_ai_authors == ["Computer"]

    def test_empty_report(self):
        rpt = BlameReport()
        assert rpt.total_lines == 0
        assert rpt.repo_ai_pct == 0.0

    def test_to_markdown_contains_summary(self):
        rpt = self._make_report()
        md = rpt.to_markdown()
        assert "Summary" in md
        assert "60.0%" in md

    def test_to_markdown_no_files(self):
        rpt = BlameReport(repo_path="/tmp/empty")
        md = rpt.to_markdown()
        assert "No files blamed" in md

    def test_to_dict(self):
        rpt = self._make_report()
        d = rpt.to_dict()
        assert "files" in d
        assert d["total_lines"] == 150
        assert d["repo_ai_pct"] == 60.0

    def test_to_json_valid(self):
        rpt = self._make_report()
        obj = json.loads(rpt.to_json())
        assert "files" in obj


# ---------------------------------------------------------------------------
# analyze_blame (with mock subprocess)
# ---------------------------------------------------------------------------

class TestAnalyzeBlame:
    def test_returns_report_when_no_git(self, tmp_path):
        # No git repo, subprocess returns non-zero
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.py").write_text("def hello(): pass\n")
        report = analyze_blame(repo_path=tmp_path)
        # Should still return a report (even if git blame fails gracefully)
        assert isinstance(report, BlameReport)
        assert len(report.files) == 1

    def test_skips_init_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "__init__.py").write_text("")
        (src / "foo.py").write_text("def bar(): pass\n")
        report = analyze_blame(repo_path=tmp_path)
        paths = [f.path for f in report.files]
        assert not any("__init__" in p for p in paths)

    def test_missing_src_dir(self, tmp_path):
        report = analyze_blame(repo_path=tmp_path)
        assert len(report.files) == 0

    def test_blame_with_mocked_git(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mod.py").write_text("def foo(): pass\ndef bar(): pass\n")

        porcelain_output = (
            "abc123 1 1 2\n"
            "author Computer\n"
            "author-mail <computer@perplexity.ai>\n"
            "\tdef foo(): pass\n"
            "abc123 2 2\n"
            "author Computer\n"
            "author-mail <computer@perplexity.ai>\n"
            "\tdef bar(): pass\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = porcelain_output

        with patch("src.blame.subprocess.run", return_value=mock_result):
            report = analyze_blame(repo_path=tmp_path)

        assert len(report.files) == 1
        fb = report.files[0]
        assert fb.ai_lines == 2
        assert fb.human_lines == 0

    def test_blame_mixed_authors(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "mix.py").write_text("a = 1\nb = 2\n")

        porcelain_output = (
            "aaa 1 1\n"
            "author Computer\n"
            "author-mail <c@perplexity.ai>\n"
            "\ta = 1\n"
            "bbb 2 2\n"
            "author Alice Human\n"
            "author-mail <alice@corp.com>\n"
            "\tb = 2\n"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = porcelain_output

        with patch("src.blame.subprocess.run", return_value=mock_result):
            report = analyze_blame(repo_path=tmp_path)

        fb = report.files[0]
        assert fb.ai_lines == 1
        assert fb.human_lines == 1
        assert report.repo_ai_pct == 50.0


# ---------------------------------------------------------------------------
# save_blame_report
# ---------------------------------------------------------------------------

class TestSaveBlameReport:
    def test_saves_markdown_and_json(self, tmp_path):
        out = tmp_path / "out" / "blame.md"
        rpt = BlameReport(repo_path=str(tmp_path))
        save_blame_report(rpt, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_json_content_valid(self, tmp_path):
        out = tmp_path / "blame.md"
        rpt = BlameReport(repo_path=str(tmp_path))
        save_blame_report(rpt, out)
        data = json.loads(out.with_suffix(".json").read_text())
        assert "files" in data

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "a" / "b" / "c" / "blame.md"
        rpt = BlameReport(repo_path=str(tmp_path))
        save_blame_report(rpt, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# Bar renderer edge cases
# ---------------------------------------------------------------------------

class TestBlameBar:
    def test_100pct_all_filled(self):
        rpt = BlameReport()
        bar = rpt._bar(100.0, width=10)
        assert bar == "█" * 10

    def test_0pct_all_empty(self):
        rpt = BlameReport()
        bar = rpt._bar(0.0, width=10)
        assert bar == "░" * 10

    def test_50pct_half_filled(self):
        rpt = BlameReport()
        bar = rpt._bar(50.0, width=10)
        assert bar.count("█") == 5
        assert bar.count("░") == 5
