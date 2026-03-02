"""Executive HTML report generator for Awake.

Combines all analysis outputs into a single self-contained HTML page that
can be shared with stakeholders or committed to the repo.  The report
includes:

- Health score summary (with colour-coded gauge)
- Trend sparklines (ASCII art -- no external image dependencies)
- Module dependency table
- Top refactoring suggestions
- Docstring coverage
- Test quality summary
- PR score history (if available)

CLI
---
    awake report               # Print HTML to stdout
    awake report --write       # Write docs/report.html
    awake report --open        # Write + open in default browser
"""

from __future__ import annotations

import html
import json
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReportSection:
    """A single section within the HTML report."""
    title: str
    content_html: str   # pre-rendered inner HTML
    icon: str = ""      # emoji or short text icon

    def to_html(self) -> str:
        """Render the section as an HTML article element."""
        icon_span = f'<span class="icon">{html.escape(self.icon)}</span> ' if self.icon else ""
        return (
            f'<article class="section">\n'
            f'  <h2>{icon_span}{html.escape(self.title)}</h2>\n'
            f'  <div class="content">\n{self.content_html}\n  </div>\n'
            f'</article>\n'
        )


@dataclass
class AwakeReport:
    """Full executive report."""
    title: str = "Awake Report"
    repo_name: str = ""
    generated_at: str = ""
    sections: list[ReportSection] = field(default_factory=list)

    def to_html(self) -> str:
        """Render the full HTML report as a string."""
        sections_html = "\n".join(s.to_html() for s in self.sections)
        return _HTML_TEMPLATE.format(
            title=html.escape(self.title),
            repo_name=html.escape(self.repo_name),
            generated_at=html.escape(self.generated_at),
            sections=sections_html,
        )


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    :root {{
      --bg: #0d1117;
      --surface: #161b22;
      --border: #30363d;
      --text: #c9d1d9;
      --muted: #8b949e;
      --green: #3fb950;
      --yellow: #d29922;
      --red: #f85149;
      --blue: #58a6ff;
      --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); font-family: var(--font); line-height: 1.6; }}
    header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.5rem 2rem; }}
    header h1 {{ font-size: 1.5rem; color: var(--blue); }}
    header p {{ color: var(--muted); font-size: 0.875rem; margin-top: 0.25rem; }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 2rem; display: grid; gap: 1.5rem; }}
    .section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1.5rem; }}
    .section h2 {{ font-size: 1.1rem; margin-bottom: 1rem; color: var(--blue); }}
    .icon {{ margin-right: 0.5rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
    th {{ background: var(--bg); color: var(--muted); text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }}
    td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: top; }}
    tr:last-child td {{ border-bottom: none; }}
    .badge {{ display: inline-block; padding: 0.2rem 0.5rem; border-radius: 3px; font-size: 0.75rem; font-weight: 600; }}
    .green {{ color: var(--green); }}
    .yellow {{ color: var(--yellow); }}
    .red {{ color: var(--red); }}
    .muted {{ color: var(--muted); }}
    pre {{ background: var(--bg); padding: 1rem; border-radius: 4px; font-size: 0.8rem; overflow-x: auto; }}
    .gauge {{ font-size: 2rem; font-weight: bold; }}
  </style>
</head>
<body>
  <header>
    <h1>Awake Report -- {repo_name}</h1>
    <p>Generated {generated_at}</p>
  </header>
  <main>
{sections}
  </main>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Optional[dict]:
    """Load and parse a JSON file, returning None on failure."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _color_class(score: float) -> str:
    """Return a CSS class name based on a 0-100 score."""
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def _ascii_sparkline(values: list[float], width: int = 20) -> str:
    """Build a simple ASCII sparkline from a list of values."""
    if not values:
        return ""
    CHARS = " _.-~=+*#@"
    mn, mx = min(values), max(values)
    span = mx - mn or 1
    result = ""
    for v in values[-width:]:
        idx = int((v - mn) / span * (len(CHARS) - 1))
        result += CHARS[idx]
    return result


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_health_section(docs: Path) -> Optional[ReportSection]:
    """Build the health score section from health_report.json."""
    data = _load_json(docs / "health_report.json")
    if not data:
        return None
    score = data.get("overall_score", 0.0)
    cc = _color_class(float(score))
    inner = (
        f'<p class="gauge {cc}">{score:.1f} / 100</p>'
        f'<p class="muted" style="margin-top:0.5rem">'
        f'{data.get("files_scored", "?")} files scored</p>'
    )
    return ReportSection(title="Health Score", content_html=inner, icon="")


def _build_trends_section(docs: Path) -> Optional[ReportSection]:
    """Build the trends section from trend_data.json."""
    data = _load_json(docs / "trend_data.json")
    if not data:
        return None
    snapshots = data.get("snapshots", [])
    if not snapshots:
        return None
    scores = [s.get("overall_score", 0) for s in snapshots[-20:]]
    spark = _ascii_sparkline(scores)
    inner = (
        f'<pre>{html.escape(spark)}</pre>'
        f'<p class="muted">Last {len(scores)} snapshots. '
        f'Latest: {scores[-1]:.1f}</p>'
    )
    return ReportSection(title="Score Trends", content_html=inner, icon="")


def _build_modules_section(docs: Path) -> Optional[ReportSection]:
    """Build the module dependency section from module_graph.json."""
    data = _load_json(docs / "module_graph.json")
    if not data:
        return None
    nodes = data.get("nodes", [])
    rows = ""
    for n in nodes[:20]:
        name = html.escape(str(n.get("name", "")))
        imports = n.get("imports", 0)
        imported = n.get("imported_by", 0)
        rows += f"<tr><td>{name}</td><td>{imports}</td><td>{imported}</td></tr>\n"
    inner = (
        "<table><thead><tr>"
        "<th>Module</th><th>Imports</th><th>Imported by</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    return ReportSection(title="Module Graph", content_html=inner, icon="")


def _build_refactor_section(docs: Path) -> Optional[ReportSection]:
    """Build the refactoring suggestions section from refactor_report.json."""
    data = _load_json(docs / "refactor_report.json")
    if not data:
        return None
    suggestions = data.get("suggestions", [])
    rows = ""
    for s in suggestions[:10]:
        f = html.escape(s.get("file", ""))
        k = html.escape(s.get("kind", ""))
        d = html.escape(s.get("description", "")[:80])
        rows += f"<tr><td>{f}</td><td>{k}</td><td>{d}</td></tr>\n"
    total = data.get("total_suggestions", 0)
    inner = (
        f"<p class='muted' style='margin-bottom:0.75rem'>{total} total suggestion(s)</p>"
        "<table><thead><tr>"
        "<th>File</th><th>Kind</th><th>Description</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )
    return ReportSection(title="Refactor Suggestions", content_html=inner, icon="")


def _build_docstring_section(docs: Path) -> Optional[ReportSection]:
    """Build the docstring coverage section from docstring_report.json."""
    data = _load_json(docs / "docstring_report.json")
    if not data:
        return None
    pct = data.get("coverage_pct", 0.0)
    cc = _color_class(float(pct))
    inner = (
        f'<p class="gauge {cc}">{pct:.1f}%</p>'
        f'<p class="muted" style="margin-top:0.5rem">'
        f'{data.get("documented", "?")} / {data.get("total_items", "?")} items documented</p>'
    )
    return ReportSection(title="Docstring Coverage", content_html=inner, icon="")


def _build_test_section(docs: Path) -> Optional[ReportSection]:
    """Build the test quality section from test_quality_report.json."""
    data = _load_json(docs / "test_quality_report.json")
    if not data:
        return None
    score = data.get("overall_score", 0.0)
    cc = _color_class(float(score))
    inner = (
        f'<p class="gauge {cc}">{score:.1f} / 100</p>'
        f'<p class="muted" style="margin-top:0.5rem">'
        f'{data.get("files_graded", "?")} test files graded</p>'
    )
    return ReportSection(title="Test Quality", content_html=inner, icon="")


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_report(repo_path: str | Path) -> AwakeReport:
    """Build the full executive report from all available docs.

    Parameters
    ----------
    repo_path:
        Path to the repository root.

    Returns
    -------
    AwakeReport
    """
    import datetime

    repo = Path(repo_path).expanduser().resolve()
    docs = repo / "docs"
    repo_name = repo.name

    report = AwakeReport(
        title=f"Awake Report -- {repo_name}",
        repo_name=repo_name,
        generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
    )

    builders = [
        _build_health_section,
        _build_trends_section,
        _build_modules_section,
        _build_refactor_section,
        _build_docstring_section,
        _build_test_section,
    ]
    for builder in builders:
        section = builder(docs)
        if section:
            report.sections.append(section)

    if not report.sections:
        report.sections.append(
            ReportSection(
                title="No Data",
                content_html="<p class='muted'>Run <code>awake health</code> first to generate data.</p>",
                icon="",
            )
        )

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for the executive report generator."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-report")
    p.add_argument("--repo", default=None, help="Repository root")
    p.add_argument("--write", action="store_true", help="Write docs/report.html")
    p.add_argument("--open", action="store_true", help="Open in default browser after writing")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    report = build_report(repo_path)
    html_content = report.to_html()

    if args.write or args.open:
        docs = repo_path / "docs"
        docs.mkdir(exist_ok=True)
        out_path = docs / "report.html"
        out_path.write_text(html_content, encoding="utf-8")
        print(f"  Wrote {out_path}")
        if args.open:
            webbrowser.open(out_path.as_uri())
        return 0

    print(html_content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
