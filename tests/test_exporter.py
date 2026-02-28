"""Tests for src/exporter.py — Export System."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.exporter import (
    ExportEngine,
    ExportResult,
    export_report,
    render_html_report,
    _md_to_html,
    FORMATS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class SimpleReport:
    """Minimal report object for testing."""

    def __init__(self, name: str = "test"):
        self._name = name

    def to_markdown(self) -> str:
        return f"# {self._name} Report\n\nSome content here.\n\n- item 1\n- item 2\n"

    def to_dict(self) -> dict:
        return {"name": self._name, "items": ["item1", "item2"]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class MarkdownOnlyReport:
    """Report with only to_markdown()."""

    def to_markdown(self) -> str:
        return "# MD Only\n\nContent.\n"


class DictOnlyReport:
    """Report with only to_dict()."""

    def to_dict(self) -> dict:
        return {"key": "value"}


# ---------------------------------------------------------------------------
# _md_to_html
# ---------------------------------------------------------------------------

class TestMdToHtml:
    def test_heading_h1(self):
        html = _md_to_html("# Hello World")
        assert "<h1>" in html
        assert "Hello World" in html

    def test_heading_h2(self):
        html = _md_to_html("## Section")
        assert "<h2>" in html

    def test_heading_h3(self):
        html = _md_to_html("### Subsection")
        assert "<h3>" in html

    def test_paragraph(self):
        html = _md_to_html("Just a paragraph of text.")
        assert "<p>" in html
        assert "paragraph of text" in html

    def test_bold(self):
        html = _md_to_html("This is **bold** text.")
        assert "<strong>" in html
        assert "bold" in html

    def test_inline_code(self):
        html = _md_to_html("Use `nightshift run`.")
        assert "<code>" in html
        assert "nightshift run" in html

    def test_code_block(self):
        html = _md_to_html("```\ndef foo():\n    pass\n```")
        assert "<pre>" in html
        assert "<code>" in html

    def test_unordered_list(self):
        html = _md_to_html("- item a\n- item b\n- item c")
        assert "<ul>" in html
        assert "<li>" in html
        assert "item a" in html

    def test_table(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        html = _md_to_html(md)
        assert "<table>" in html
        assert "<th>" in html
        assert "<td>" in html

    def test_horizontal_rule(self):
        html = _md_to_html("---")
        assert "<hr>" in html

    def test_blockquote(self):
        html = _md_to_html("> A quote here")
        assert "<blockquote>" in html

    def test_link(self):
        html = _md_to_html("[GitHub](https://github.com)")
        assert "<a href=" in html
        assert "GitHub" in html

    def test_empty_string(self):
        html = _md_to_html("")
        assert isinstance(html, str)

    def test_html_entities_escaped_in_code(self):
        html = _md_to_html("```\n<div>test</div>\n```")
        assert "&lt;" in html
        assert "&gt;" in html


# ---------------------------------------------------------------------------
# render_html_report
# ---------------------------------------------------------------------------

class TestRenderHtmlReport:
    def test_returns_string(self):
        html = render_html_report("Test Report", "# Hello\n\nContent.")
        assert isinstance(html, str)

    def test_contains_title(self):
        html = render_html_report("My Cool Report", "# Content")
        assert "My Cool Report" in html

    def test_valid_html_structure(self):
        html = render_html_report("Test", "# H\n\nParagraph.")
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "<head>" in html
        assert "<body>" in html
        assert "</html>" in html

    def test_contains_metadata(self):
        html = render_html_report(
            "Test",
            "# H",
            metadata={"Session": "11", "Modules": "19"},
        )
        assert "Session" in html
        assert "11" in html

    def test_no_metadata_works(self):
        html = render_html_report("Test", "# H")
        assert "<!DOCTYPE html>" in html

    def test_contains_generated_at(self):
        html = render_html_report("Test", "# H")
        assert "UTC" in html or "Generated" in html

    def test_nightshift_footer(self):
        html = render_html_report("Test", "# H")
        assert "Nightshift" in html

    def test_dark_theme_colors(self):
        html = render_html_report("Test", "# H")
        assert "--bg:" in html or "0d1117" in html


# ---------------------------------------------------------------------------
# ExportResult
# ---------------------------------------------------------------------------

class TestExportResult:
    def test_to_dict(self):
        result = ExportResult(
            name="test",
            files={"json": Path("/tmp/test.json")},
            errors=["html: failed"],
        )
        d = result.to_dict()
        assert d["name"] == "test"
        assert "json" in d["files"]
        assert len(d["errors"]) == 1


# ---------------------------------------------------------------------------
# ExportEngine
# ---------------------------------------------------------------------------

class TestExportEngine:
    def test_init(self, tmp_path: Path):
        engine = ExportEngine("my-report", tmp_path)
        assert engine.name == "my-report"
        assert engine.out_dir == tmp_path

    def test_export_json(self, tmp_path: Path):
        engine = ExportEngine("test-report", tmp_path)
        report = SimpleReport()
        result = engine.export(report, formats=["json"])
        assert "json" in result.files
        assert result.files["json"].exists()
        data = json.loads(result.files["json"].read_text())
        assert "name" in data

    def test_export_markdown(self, tmp_path: Path):
        engine = ExportEngine("test-report", tmp_path)
        report = SimpleReport()
        result = engine.export(report, formats=["markdown"])
        assert "markdown" in result.files
        assert result.files["markdown"].exists()
        content = result.files["markdown"].read_text()
        assert "Report" in content

    def test_export_html(self, tmp_path: Path):
        engine = ExportEngine("test-report", tmp_path)
        report = SimpleReport()
        result = engine.export(report, formats=["html"])
        assert "html" in result.files
        assert result.files["html"].exists()
        content = result.files["html"].read_text()
        assert "<!DOCTYPE html>" in content

    def test_export_all_formats(self, tmp_path: Path):
        engine = ExportEngine("test-report", tmp_path)
        report = SimpleReport()
        result = engine.export(report)
        assert len(result.files) == 3  # json, markdown, html

    def test_creates_out_dir(self, tmp_path: Path):
        out_dir = tmp_path / "reports" / "nested"
        engine = ExportEngine("test", out_dir)
        report = SimpleReport()
        engine.export(report, formats=["json"])
        assert out_dir.exists()

    def test_unknown_format_captured_in_errors(self, tmp_path: Path):
        engine = ExportEngine("test", tmp_path)
        report = SimpleReport()
        result = engine.export(report, formats=["unknown_fmt"])
        assert len(result.errors) >= 1

    def test_markdown_only_report(self, tmp_path: Path):
        engine = ExportEngine("test", tmp_path)
        report = MarkdownOnlyReport()
        result = engine.export(report, formats=["markdown", "html"])
        assert result.files["markdown"].exists()

    def test_dict_only_report_json(self, tmp_path: Path):
        engine = ExportEngine("test", tmp_path)
        report = DictOnlyReport()
        result = engine.export(report, formats=["json"])
        assert result.files["json"].exists()

    def test_with_metadata(self, tmp_path: Path):
        engine = ExportEngine("test", tmp_path, title="Custom Title")
        report = SimpleReport()
        result = engine.export(
            report,
            formats=["html"],
            metadata={"Session": "11", "Modules": "4"},
        )
        html = result.files["html"].read_text()
        assert "Session" in html
        assert "11" in html

    def test_json_file_named_correctly(self, tmp_path: Path):
        engine = ExportEngine("my-analysis", tmp_path)
        report = SimpleReport()
        result = engine.export(report, formats=["json"])
        assert result.files["json"].name == "my-analysis.json"

    def test_html_file_named_correctly(self, tmp_path: Path):
        engine = ExportEngine("coupling-report", tmp_path)
        report = SimpleReport()
        result = engine.export(report, formats=["html"])
        assert result.files["html"].name == "coupling-report.html"


# ---------------------------------------------------------------------------
# export_report convenience function
# ---------------------------------------------------------------------------

class TestExportReport:
    def test_returns_export_result(self, tmp_path: Path):
        report = SimpleReport()
        result = export_report(report, tmp_path, "test")
        assert isinstance(result, ExportResult)

    def test_all_formats(self, tmp_path: Path):
        report = SimpleReport()
        result = export_report(report, tmp_path, "test")
        assert len(result.files) == 3

    def test_subset_formats(self, tmp_path: Path):
        report = SimpleReport()
        result = export_report(report, tmp_path, "test", formats=["json"])
        assert "json" in result.files
        assert "html" not in result.files

    def test_with_title(self, tmp_path: Path):
        report = SimpleReport()
        result = export_report(
            report, tmp_path, "test", title="My Report Title"
        )
        html = result.files["html"].read_text()
        assert "My Report Title" in html

    def test_with_metadata(self, tmp_path: Path):
        report = SimpleReport()
        result = export_report(
            report,
            tmp_path,
            "test",
            formats=["html"],
            metadata={"key": "value123"},
        )
        html = result.files["html"].read_text()
        assert "value123" in html


# ---------------------------------------------------------------------------
# FORMATS constant
# ---------------------------------------------------------------------------

class TestFormats:
    def test_formats_tuple(self):
        assert "json" in FORMATS
        assert "markdown" in FORMATS
        assert "html" in FORMATS


# ---------------------------------------------------------------------------
# Integration with real modules
# ---------------------------------------------------------------------------

class TestIntegrationWithRealModules:
    def test_with_complexity_report(self, tmp_path: Path):
        from src.complexity import analyze_complexity
        repo = Path(__file__).resolve().parent.parent
        report = analyze_complexity(repo_path=repo, session_number=11)
        result = export_report(
            report,
            tmp_path,
            "complexity-report",
            title="Complexity Report — Session 11",
        )
        assert result.files["json"].exists()
        assert result.files["markdown"].exists()
        assert result.files["html"].exists()
        html = result.files["html"].read_text()
        assert "Cyclomatic" in html

    def test_with_coupling_report(self, tmp_path: Path):
        from src.coupling import analyze_coupling
        repo = Path(__file__).resolve().parent.parent
        report = analyze_coupling(repo_path=repo)
        result = export_report(
            report,
            tmp_path,
            "coupling-report",
        )
        assert result.files["json"].exists()
        html = result.files["html"].read_text()
        assert "Coupling" in html

    def test_with_timeline(self, tmp_path: Path):
        from src.timeline import build_timeline
        repo = Path(__file__).resolve().parent.parent
        tl = build_timeline(repo_path=repo)
        result = export_report(tl, tmp_path, "timeline-report")
        assert result.files["html"].exists()
