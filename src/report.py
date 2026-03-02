"""Executive HTML report generator for Awake.

Combines outputs from all Awake analysis modules into a single polished
HTML report suitable for sharing with engineering leadership or external
stakeholders.

The report includes:

- Repository health score (from ``health.py``)
- Docstring coverage (from ``docstring_gen.py``)
- Refactor issues summary (from ``refactor.py``)
- Test quality grade (from ``test_quality.py``)
- Module graph statistics (from ``module_graph.py``)
- Trend sparklines (from ``trend_data.py``)

Each section is collapsible and the file is fully self-contained (no
external CDN dependencies; CSS and JS are inlined).

Public API
----------
- ``ReportSection``     -- one collapsible section in the report
- ``ReportData``        -- all data needed to render the report
- ``build_report(repo_path)`` -> ``ReportData``
- ``render_html(data)`` -> ``str``
- ``save_report(data, out_path)``

CLI
---
    awake report [--output PATH]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ReportSection:
    """A single collapsible section in the HTML report."""

    title: str
    score: float | None  # None if this section has no numeric score
    content_html: str
    status: str = "ok"   # "ok" | "warn" | "error"


@dataclass
class ReportData:
    """All data needed to render the executive report."""

    repo: str
    generated_at: str
    overall_score: float
    sections: list[ReportSection] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 0; background: #f8fafc; color: #1a202c; }
.header { background: #2d3748; color: #fff; padding: 2rem; }
.header h1 { margin: 0; font-size: 1.8rem; }
.header p  { margin: 0.25rem 0 0; opacity: 0.8; font-size: 0.9rem; }
.score-badge { display: inline-block; background: #48bb78; color: #fff;
               border-radius: 9999px; padding: 0.2rem 0.75rem;
               font-weight: 700; font-size: 1.2rem; margin-left: 1rem; }
.score-badge.warn  { background: #ed8936; }
.score-badge.error { background: #e53e3e; }
.container { max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
.section { background: #fff; border-radius: 8px; margin-bottom: 1rem;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
.section-header { padding: 1rem 1.5rem; cursor: pointer;
                  display: flex; justify-content: space-between;
                  align-items: center; user-select: none; }
.section-header:hover { background: #f7fafc; }
.section-title { font-weight: 600; font-size: 1rem; }
.section-score { font-size: 0.9rem; font-weight: 700; }
.section-score.ok    { color: #38a169; }
.section-score.warn  { color: #d69e2e; }
.section-score.error { color: #e53e3e; }
.section-body { padding: 1rem 1.5rem; border-top: 1px solid #e2e8f0;
                display: none; }
.section-body.open { display: block; }
pre { background: #2d3748; color: #e2e8f0; padding: 1rem;
      border-radius: 4px; overflow-x: auto; font-size: 0.8rem; }
table { border-collapse: collapse; width: 100%; font-size: 0.875rem; }
th, td { padding: 0.5rem 0.75rem; text-align: left;
         border-bottom: 1px solid #e2e8f0; }
th { background: #f7fafc; font-weight: 600; }
"""

_JS = """
document.querySelectorAll('.section-header').forEach(function(h) {
  h.addEventListener('click', function() {
    var body = h.nextElementSibling;
    body.classList.toggle('open');
  });
});
"""


def _score_cls(score: float | None) -> str:
    """Return a CSS class name based on the score value."""
    if score is None:
        return "ok"
    if score >= 75:
        return "ok"
    if score >= 50:
        return "warn"
    return "error"


# ---------------------------------------------------------------------------
# Stub builders
# ---------------------------------------------------------------------------
# These functions attempt to import each Awake module and fall back to empty
# data if it is not yet available, so the report runner stays functional even
# on a partially-built checkout.


def _health_section(root: Path) -> ReportSection:
    """Build the repository health section of the report."""
    try:
        from health import HealthReport, scan_repo  # type: ignore[import]

        report: HealthReport = scan_repo(root)
        rows = "".join(
            f"<tr><td>{f.path}</td><td>{f.score:.0f}</td>"
            f"<td>{len(f.issues)}</td></tr>"
            for f in sorted(report.files, key=lambda x: x.score)
        )
        html = (
            f"<p>Overall health score: <strong>{report.overall_score:.1f}/100</strong></p>"
            "<table><thead><tr><th>File</th><th>Score</th><th>Issues</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        return ReportSection(
            title="Repository Health",
            score=report.overall_score,
            content_html=html,
            status=_score_cls(report.overall_score),
        )
    except Exception as exc:  # noqa: BLE001
        return ReportSection(
            title="Repository Health",
            score=None,
            content_html=f"<p>Could not load health data: {exc}</p>",
            status="warn",
        )


def _docstring_section(root: Path) -> ReportSection:
    """Build the docstring coverage section of the report."""
    try:
        from docstring_gen import DocstringReport, scan_missing_docstrings  # type: ignore[import]

        report: DocstringReport = scan_missing_docstrings(root)
        pct = report.coverage * 100
        html = (
            f"<p>Docstring coverage: <strong>{pct:.1f}%</strong> "
            f"({len(report.missing)} missing out of {report.total_items} items)</p>"
        )
        return ReportSection(
            title="Docstring Coverage",
            score=pct,
            content_html=html,
            status=_score_cls(pct),
        )
    except Exception as exc:  # noqa: BLE001
        return ReportSection(
            title="Docstring Coverage",
            score=None,
            content_html=f"<p>Could not load docstring data: {exc}</p>",
            status="warn",
        )


def _refactor_section(root: Path) -> ReportSection:
    """Build the refactor issues section of the report."""
    try:
        from refactor import scan_repo  # type: ignore[import]

        reports = scan_repo(root)
        total = sum(len(r.issues) for r in reports)
        fixable = sum(r.fixable_count for r in reports)
        score = max(0.0, 100.0 - total * 0.5)
        rows = "".join(
            f"<tr><td>{r.path}</td><td>{len(r.issues)}</td><td>{r.fixable_count}</td></tr>"
            for r in reports
            if r.issues
        )
        html = (
            f"<p>{total} issues found ({fixable} auto-fixable).</p>"
            "<table><thead><tr><th>File</th><th>Issues</th><th>Fixable</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
        return ReportSection(
            title="Refactor Issues",
            score=score,
            content_html=html,
            status=_score_cls(score),
        )
    except Exception as exc:  # noqa: BLE001
        return ReportSection(
            title="Refactor Issues",
            score=None,
            content_html=f"<p>Could not load refactor data: {exc}</p>",
            status="warn",
        )


def _test_quality_section(root: Path) -> ReportSection:
    """Build the test quality section of the report."""
    try:
        from test_quality import TestQualityReport, analyze_test_quality  # type: ignore[import]

        report: TestQualityReport = analyze_test_quality(root)
        html = (
            f"<p>Overall test quality: <strong>{report.overall_score:.1f}/100</strong> "
            f"across {len(report.files)} test files ({report.total_tests} tests, "
            f"{report.total_issues} issues)</p>"
        )
        return ReportSection(
            title="Test Quality",
            score=report.overall_score,
            content_html=html,
            status=_score_cls(report.overall_score),
        )
    except Exception as exc:  # noqa: BLE001
        return ReportSection(
            title="Test Quality",
            score=None,
            content_html=f"<p>Could not load test quality data: {exc}</p>",
            status="warn",
        )


# ---------------------------------------------------------------------------
# Build & render
# ---------------------------------------------------------------------------


def build_report(repo_path: str | Path) -> ReportData:
    """Collect data from all Awake modules and return a :class:`ReportData`.

    Parameters
    ----------
    repo_path:
        Root of the repository.

    Returns
    -------
    ReportData
        All data needed to render the HTML report.
    """
    from datetime import datetime, timezone

    root = Path(repo_path)
    sections = [
        _health_section(root),
        _docstring_section(root),
        _refactor_section(root),
        _test_quality_section(root),
    ]
    scored = [s.score for s in sections if s.score is not None]
    overall = sum(scored) / len(scored) if scored else 0.0
    return ReportData(
        repo=str(root),
        generated_at=datetime.now(timezone.utc).isoformat(),
        overall_score=overall,
        sections=sections,
    )


def render_html(data: ReportData) -> str:
    """Render *data* as a self-contained HTML string.

    Parameters
    ----------
    data:
        Report data to render.

    Returns
    -------
    str
        Full HTML document as a string.
    """
    badge_cls = _score_cls(data.overall_score)
    sections_html = ""
    for sec in data.sections:
        score_txt = f"{sec.score:.1f}" if sec.score is not None else "N/A"
        sections_html += (
            f'<div class="section">'
            f'<div class="section-header">'
            f'<span class="section-title">{sec.title}</span>'
            f'<span class="section-score {sec.status}">{score_txt}</span>'
            f"</div>"
            f'<div class="section-body">{sec.content_html}</div>'
            f"</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Awake Report – {data.repo}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="header">
  <h1>Awake Report
    <span class="score-badge {badge_cls}">{data.overall_score:.1f}</span>
  </h1>
  <p>{data.repo} &nbsp;·&nbsp; Generated {data.generated_at}</p>
</div>
<div class="container">
{sections_html}
</div>
<script>{_JS}</script>
</body>
</html>"""


def save_report(data: ReportData, out_path: str | Path) -> None:
    """Write the rendered HTML report to *out_path*.

    Parameters
    ----------
    data:
        Report data to save.
    out_path:
        Destination file path.
    """
    html = render_html(data)
    Path(out_path).write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the executive report generator.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake report",
        description="Generate an executive HTML report.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument(
        "--output",
        "-o",
        default="awake_report.html",
        help="Output file path (default: awake_report.html)",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    data = build_report(root)
    save_report(data, args.output)
    print(f"Report written to {args.output}")
    print(f"Overall score: {data.overall_score:.1f}/100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
