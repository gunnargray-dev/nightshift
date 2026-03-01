"""Comprehensive tests for src/report.py.

Covers:
- Data classes: ReportSection, ExecutiveReport
- Helper functions: _grade_colour, _score_colour, _score_to_grade,
  _render_section, _render_html, _run_cmd, _safe_score,
  _html_table_from_list, _bar_chart_html
- Public API: generate_report
- Edge cases: empty data, None inputs, boundary scores
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Make sure src is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.report import (
    ReportSection,
    ExecutiveReport,
    _grade_colour,
    _score_colour,
    _render_section,
    _render_html,
    _run_cmd,
    _safe_score,
    _score_to_grade,
    _html_table_from_list,
    _bar_chart_html,
    generate_report,
)


# ===========================================================================
# ReportSection
# ===========================================================================

class TestReportSection:
    def test_creation_minimal(self):
        sec = ReportSection(title="Health", icon="❤", content_html="<p>OK</p>")
        assert sec.title == "Health"
        assert sec.icon == "❤"
        assert sec.score is None
        assert sec.grade == ""
        assert sec.subsections == []

    def test_creation_full(self):
        sec = ReportSection(
            title="Security",
            icon="🔒",
            content_html="<p>Secure</p>",
            score=88.0,
            grade="B+",
            subsections=[{"key": "value"}],
        )
        assert sec.score == 88.0
        assert sec.grade == "B+"
        assert len(sec.subsections) == 1

    def test_to_dict_contains_all_fields(self):
        sec = ReportSection(title="T", icon="I", content_html="C", score=70.0, grade="B-")
        d = sec.to_dict()
        assert d["title"] == "T"
        assert d["icon"] == "I"
        assert d["content_html"] == "C"
        assert d["score"] == 70.0
        assert d["grade"] == "B-"

    def test_to_dict_none_score(self):
        sec = ReportSection(title="T", icon="I", content_html="C")
        d = sec.to_dict()
        assert d["score"] is None

    def test_to_dict_is_json_serialisable(self):
        sec = ReportSection(title="T", icon="I", content_html="C", score=55.5, grade="C-")
        json.dumps(sec.to_dict())  # should not raise


# ===========================================================================
# ExecutiveReport
# ===========================================================================

class TestExecutiveReport:
    def _make_report(self, **kwargs) -> ExecutiveReport:
        defaults = dict(
            repo_name="testrepo",
            generated_at="January 01, 2025 at 00:00 UTC",
            session_number=5,
            overall_grade="B",
            overall_score=77.5,
        )
        defaults.update(kwargs)
        return ExecutiveReport(**defaults)

    def test_creation_defaults(self):
        r = self._make_report()
        assert r.sections == []
        assert r.headline_metrics == {}

    def test_to_dict_keys(self):
        r = self._make_report()
        d = r.to_dict()
        for key in ("repo_name", "generated_at", "session_number",
                    "overall_grade", "overall_score", "sections", "headline_metrics"):
            assert key in d

    def test_to_html_is_string(self):
        r = self._make_report()
        html = r.to_html()
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_to_html_contains_repo_name(self):
        r = self._make_report(repo_name="myrepo")
        html = r.to_html()
        assert "myrepo" in html

    def test_to_html_contains_grade(self):
        r = self._make_report(overall_grade="A+")
        html = r.to_html()
        assert "A+" in html

    def test_save_writes_file(self, tmp_path):
        r = self._make_report()
        out = tmp_path / "report.html"
        r.save(out)
        assert out.exists()
        assert "<!DOCTYPE html>" in out.read_text()

    def test_save_creates_parent_dirs(self, tmp_path):
        r = self._make_report()
        out = tmp_path / "sub" / "dir" / "report.html"
        r.save(out)
        assert out.exists()

    def test_to_dict_is_json_serialisable(self):
        sec = ReportSection(title="T", icon="I", content_html="C", score=80.0, grade="B+")
        r = self._make_report(sections=[sec], headline_metrics={"Sessions": 5})
        json.dumps(r.to_dict())  # should not raise


# ===========================================================================
# _grade_colour
# ===========================================================================

class TestGradeColour:
    def test_a_plus_returns_green(self):
        colour = _grade_colour("A+")
        assert "#" in colour

    def test_f_returns_red(self):
        colour = _grade_colour("F")
        assert "#" in colour
        assert colour != _grade_colour("A")

    def test_unknown_grade_returns_fallback(self):
        colour = _grade_colour("Z")
        assert isinstance(colour, str)
        assert len(colour) > 0

    @pytest.mark.parametrize("grade", ["A+", "A", "A-", "B+", "B", "B-",
                                         "C+", "C", "C-", "D+", "D", "D-", "F"])
    def test_all_grades_return_a_string(self, grade):
        assert isinstance(_grade_colour(grade), str)


# ===========================================================================
# _score_colour
# ===========================================================================

class TestScoreColour:
    def test_high_score_is_green(self):
        c = _score_colour(95)
        assert c == _score_colour(90)  # both >= 90

    def test_low_score_is_red(self):
        c = _score_colour(10)
        assert "#ff" in c.lower() or "ff" in c.lower()

    @pytest.mark.parametrize("score", [0, 10, 39, 40, 59, 60, 74, 75, 89, 90, 100])
    def test_all_boundaries_return_string(self, score):
        assert isinstance(_score_colour(score), str)

    def test_boundary_at_90(self):
        assert _score_colour(90) == _score_colour(91)

    def test_score_less_than_40_differs_from_60(self):
        assert _score_colour(30) != _score_colour(65)


# ===========================================================================
# _score_to_grade
# ===========================================================================

class TestScoreToGrade:
    @pytest.mark.parametrize("score,expected", [
        (100, "A+"),
        (95, "A+"),
        (90, "A"),
        (85, "A-"),
        (80, "B+"),
        (75, "B"),
        (70, "B-"),
        (65, "C+"),
        (60, "C"),
        (55, "C-"),
        (50, "D+"),
        (45, "D"),
        (40, "D-"),
        (30, "F"),
        (0, "F"),
    ])
    def test_known_values(self, score, expected):
        assert _score_to_grade(score) == expected

    def test_none_returns_empty_string(self):
        assert _score_to_grade(None) == ""

    def test_returns_string(self):
        assert isinstance(_score_to_grade(72), str)


# ===========================================================================
# _render_section
# ===========================================================================

class TestRenderSection:
    def test_renders_title(self):
        sec = ReportSection(title="My Section", icon="🔑", content_html="<p>body</p>")
        html = _render_section(sec)
        assert "My Section" in html

    def test_renders_icon(self):
        sec = ReportSection(title="T", icon="🌟", content_html="<p>body</p>")
        html = _render_section(sec)
        assert "🌟" in html

    def test_renders_content(self):
        sec = ReportSection(title="T", icon="I", content_html="<em>custom content</em>")
        html = _render_section(sec)
        assert "<em>custom content</em>" in html

    def test_renders_score_badge_when_score_present(self):
        sec = ReportSection(title="T", icon="I", content_html="C", score=85.0, grade="A-")
        html = _render_section(sec)
        assert "score-badge" in html
        assert "85" in html

    def test_no_score_badge_when_score_is_none(self):
        sec = ReportSection(title="T", icon="I", content_html="C")
        html = _render_section(sec)
        assert "score-badge" not in html

    def test_renders_grade_badge_when_grade_present(self):
        sec = ReportSection(title="T", icon="I", content_html="C", score=80.0, grade="B+")
        html = _render_section(sec)
        assert "B+" in html


# ===========================================================================
# _render_html
# ===========================================================================

class TestRenderHtml:
    def _report(self, **kw) -> ExecutiveReport:
        defaults = dict(
            repo_name="repo",
            generated_at="2025-01-01",
            session_number=1,
            overall_grade="C",
            overall_score=60.0,
        )
        defaults.update(kw)
        return ExecutiveReport(**defaults)

    def test_returns_string(self):
        assert isinstance(_render_html(self._report()), str)

    def test_contains_doctype(self):
        assert "<!DOCTYPE html>" in _render_html(self._report())

    def test_contains_session_number(self):
        html = _render_html(self._report(session_number=17))
        assert "17" in html

    def test_metric_cards_appear_in_output(self):
        r = self._report(headline_metrics={"Sessions": 10, "PRs": 42})
        html = _render_html(r)
        assert "Sessions" in html
        assert "42" in html

    def test_sections_rendered(self):
        r = self._report()
        r.sections.append(ReportSection(title="UNIQUE_TITLE", icon="X", content_html="<b>body</b>"))
        html = _render_html(r)
        assert "UNIQUE_TITLE" in html

    def test_footer_contains_generated_at(self):
        r = self._report(generated_at="March 15, 2025")
        html = _render_html(r)
        assert "March 15, 2025" in html


# ===========================================================================
# _safe_score
# ===========================================================================

class TestSafeScore:
    def test_nested_key_access(self):
        d = {"a": {"b": 80.0}}
        assert _safe_score(d, "a", "b") == 80.0

    def test_none_dict_returns_none(self):
        assert _safe_score(None) is None

    def test_missing_key_returns_none(self):
        d = {"x": 50.0}
        assert _safe_score(d, "missing") is None

    def test_non_numeric_returns_none(self):
        d = {"score": "not-a-number"}
        assert _safe_score(d, "score") is None

    def test_integer_value_is_converted(self):
        d = {"score": 75}
        assert _safe_score(d, "score") == 75.0

    def test_string_numeric_is_converted(self):
        d = {"score": "85.5"}
        assert _safe_score(d, "score") == 85.5

    def test_deeply_nested(self):
        d = {"a": {"b": {"c": 42.0}}}
        assert _safe_score(d, "a", "b", "c") == 42.0


# ===========================================================================
# _html_table_from_list
# ===========================================================================

class TestHtmlTableFromList:
    def test_empty_rows_returns_no_data_message(self):
        html = _html_table_from_list([], ["Col1", "Col2"])
        assert "No data" in html

    def test_headers_appear_in_output(self):
        rows = [{"Name": "Alice", "Score": 90}]
        html = _html_table_from_list(rows, ["Name", "Score"])
        assert "<th>Name</th>" in html
        assert "<th>Score</th>" in html

    def test_values_appear_in_cells(self):
        rows = [{"Name": "Bob", "Score": 85}]
        html = _html_table_from_list(rows, ["Name", "Score"])
        assert "Bob" in html
        assert "85" in html

    def test_missing_column_uses_dash(self):
        rows = [{"Name": "Carol"}]
        html = _html_table_from_list(rows, ["Name", "Score"])
        assert "<td>-</td>" in html

    def test_truncates_at_20_rows(self):
        rows = [{"Name": str(i)} for i in range(25)]
        html = _html_table_from_list(rows, ["Name"])
        # 21 and above should not appear
        assert "21" not in html
        assert "19" in html

    def test_returns_table_tag(self):
        rows = [{"k": "v"}]
        html = _html_table_from_list(rows, ["k"])
        assert "<table>" in html


# ===========================================================================
# _bar_chart_html
# ===========================================================================

class TestBarChartHtml:
    def test_returns_string(self):
        items = [("mod", 80.0, "#00c853")]
        html = _bar_chart_html(items)
        assert isinstance(html, str)

    def test_label_appears(self):
        items = [("my_module", 70.0, "#76ff03")]
        html = _bar_chart_html(items)
        assert "my_module" in html

    def test_colour_applied(self):
        items = [("mod", 50.0, "#ffea00")]
        html = _bar_chart_html(items)
        assert "#ffea00" in html

    def test_empty_list_returns_wrapper(self):
        html = _bar_chart_html([])
        assert "<div>" in html

    def test_truncates_at_15_items(self):
        items = [(f"mod{i}", float(i * 5), "#fff") for i in range(20)]
        html = _bar_chart_html(items)
        # Item 16 (index 15) should not appear
        assert "mod15" not in html
        assert "mod14" in html


# ===========================================================================
# _run_cmd
# ===========================================================================

class TestRunCmd:
    def test_returns_none_on_nonzero_exit(self, tmp_path):
        result = MagicMock()
        result.returncode = 1
        result.stdout = ""
        with patch("subprocess.run", return_value=result):
            assert _run_cmd(["stats"], tmp_path) is None

    def test_returns_none_on_invalid_json(self, tmp_path):
        result = MagicMock()
        result.returncode = 0
        result.stdout = "not json"
        with patch("subprocess.run", return_value=result):
            assert _run_cmd(["stats"], tmp_path) is None

    def test_returns_dict_on_valid_json_object(self, tmp_path):
        result = MagicMock()
        result.returncode = 0
        result.stdout = '{"key": "value"}'
        with patch("subprocess.run", return_value=result):
            r = _run_cmd(["stats"], tmp_path)
            assert r == {"key": "value"}

    def test_returns_list_on_valid_json_array(self, tmp_path):
        result = MagicMock()
        result.returncode = 0
        result.stdout = '[1, 2, 3]'
        with patch("subprocess.run", return_value=result):
            r = _run_cmd(["stats"], tmp_path)
            assert r == [1, 2, 3]

    def test_handles_json_with_leading_text(self, tmp_path):
        result = MagicMock()
        result.returncode = 0
        result.stdout = 'INFO: startup\n{"result": 42}'
        with patch("subprocess.run", return_value=result):
            r = _run_cmd(["stats"], tmp_path)
            assert r == {"result": 42}

    def test_returns_none_on_exception(self, tmp_path):
        with patch("subprocess.run", side_effect=Exception("broken")):
            assert _run_cmd(["stats"], tmp_path) is None


# ===========================================================================
# generate_report  (integration-style, mocked subprocess)
# ===========================================================================

class TestGenerateReport:
    def _null_run_cmd(self, *args, **kwargs):
        return None

    def test_returns_executive_report(self, tmp_path):
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(tmp_path)
        assert isinstance(report, ExecutiveReport)

    def test_repo_name_matches_folder(self, tmp_path):
        folder = tmp_path / "my_project"
        folder.mkdir()
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(folder)
        assert report.repo_name == "my_project"

    def test_overall_score_is_float(self, tmp_path):
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(tmp_path)
        assert isinstance(report.overall_score, float)

    def test_overall_grade_is_string(self, tmp_path):
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(tmp_path)
        assert isinstance(report.overall_grade, str)

    def test_generated_at_is_string(self, tmp_path):
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(tmp_path)
        assert isinstance(report.generated_at, str)
        assert len(report.generated_at) > 0

    def test_session_number_from_log(self, tmp_path):
        log = tmp_path / "AWAKE_LOG.md"
        log.write_text("## Session 7\nsome content\n## Session 8\nmore content")
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(tmp_path)
        assert report.session_number == 8

    def test_explicit_session_number_used(self, tmp_path):
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(tmp_path, session_number=42)
        assert report.session_number == 42

    def test_to_html_produces_valid_output(self, tmp_path):
        with patch("src.report._run_cmd", self._null_run_cmd):
            report = generate_report(tmp_path)
        html = report.to_html()
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_stats_section_added_when_data_present(self, tmp_path):
        stats_data = {
            "sessions_count": 10,
            "total_prs": 25,
            "total_commits": 200,
            "total_lines_changed": 5000,
        }
        def mock_run_cmd(args, repo):
            if args == ["stats"]:
                return stats_data
            return None
        with patch("src.report._run_cmd", mock_run_cmd):
            report = generate_report(tmp_path)
        # Stats section should appear
        titles = [s.title for s in report.sections]
        assert any("Stats" in t for t in titles)

    def test_health_section_added_when_data_present(self, tmp_path):
        health_data = {
            "overall_health_score": 82.5,
            "files": [{"name": "cli.py", "health_score": 75}],
        }
        def mock_run_cmd(args, repo):
            if args == ["health"]:
                return health_data
            return None
        with patch("src.report._run_cmd", mock_run_cmd):
            report = generate_report(tmp_path)
        titles = [s.title for s in report.sections]
        assert any("Health" in t for t in titles)

    def test_no_sections_when_all_cmds_fail(self, tmp_path):
        with patch("src.report._run_cmd", return_value=None):
            report = generate_report(tmp_path)
        assert report.sections == []

    def test_overall_score_uses_health_when_present(self, tmp_path):
        health_data = {"overall_health_score": 55.0, "files": []}
        def mock_run_cmd(args, repo):
            if args == ["health"]:
                return health_data
            return None
        with patch("src.report._run_cmd", mock_run_cmd):
            report = generate_report(tmp_path)
        assert report.overall_score == 55.0

    def test_fallback_score_is_75(self, tmp_path):
        """When no analysis commands return data, overall_score defaults to 75."""
        with patch("src.report._run_cmd", return_value=None):
            report = generate_report(tmp_path)
        assert report.overall_score == 75.0
