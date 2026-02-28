"""Executive HTML report generator for Nightshift.

Combines all analysis outputs into a single polished HTML document suitable
for sharing with stakeholders.  Uses only the standard library.

Usage
-----
    from src.report import generate_report
    report = generate_report(repo_root)
    report.save(repo_root / "docs" / "report.html")

CLI
---
    nightshift report                     # Generate and open in browser
    nightshift report --output report.html
    nightshift report --json              # Emit summary metadata as JSON
"""

from __future__ import annotations

import json
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.scoring import grade_colour as _grade_colour, score_colour as _score_colour, score_to_grade as _score_to_grade


@dataclass
class ReportSection:
    """A single section within the executive report."""
    title: str
    icon: str
    content_html: str
    score: Optional[float] = None
    grade: str = ""
    subsections: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutiveReport:
    """Full executive report combining all analysis dimensions."""
    repo_name: str
    generated_at: str
    session_number: int
    overall_grade: str
    overall_score: float
    sections: list[ReportSection] = field(default_factory=list)
    headline_metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_html(), encoding="utf-8")

    def to_html(self) -> str:
        return _render_html(self)


# _grade_colour, _score_colour and _score_to_grade are imported from src.scoring


def _render_section(sec: ReportSection) -> str:
    score_html = ""
    if sec.score is not None:
        sc = _score_colour(sec.score)
        grade_sc = _grade_colour(sec.grade)
        score_html = f"""
        <div class="section-score">
            <span class="score-badge" style="background:{sc}">{sec.score:.0f}</span>
            {'<span class="grade-badge" style="background:' + grade_sc + '">' + sec.grade + '</span>' if sec.grade else ''}
        </div>"""

    return f"""
    <div class="section">
        <div class="section-header">
            <span class="section-icon">{sec.icon}</span>
            <h2>{sec.title}</h2>
            {score_html}
        </div>
        <div class="section-body">
            {sec.content_html}
        </div>
    </div>"""


def _render_html(report: ExecutiveReport) -> str:
    sections_html = "\n".join(_render_section(s) for s in report.sections)
    metric_cards = ""
    for label, value in report.headline_metrics.items():
        metric_cards += f"""
        <div class="metric-card">
            <div class="metric-value">{value}</div>
            <div class="metric-label">{label}</div>
        </div>"""

    overall_colour = _grade_colour(report.overall_grade)
    overall_score_colour = _score_colour(report.overall_score)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nightshift Report - {report.repo_name}</title>
<style>
  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #21262d;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --accent2: #bc8cff;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; font-size: 14px; line-height: 1.6; }}
  .header {{ background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border-bottom: 1px solid var(--border); padding: 40px 48px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 24px; }}
  .header-left h1 {{ font-size: 28px; font-weight: 700; }}
  .metric-card {{ flex: 1; min-width: 120px; background: var(--surface); padding: 20px 24px; text-align: center; }}
  .metric-value {{ font-size: 24px; font-weight: 700; color: var(--accent); }}
  .metric-label {{ font-size: 12px; color: var(--muted); text-transform: uppercase; margin-top: 4px; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 32px 48px; }}
  .section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 24px; overflow: hidden; }}
  .section-header {{ display: flex; align-items: center; gap: 12px; padding: 18px 24px; background: var(--surface2); border-bottom: 1px solid var(--border); }}
  .section-body {{ padding: 20px 24px; }}
  .section-header h2 {{ font-size: 16px; font-weight: 600; flex: 1; }}
  .score-badge, .grade-badge {{ padding: 4px 10px; border-radius: 20px; font-size: 13px; font-weight: 700; color: #0d1117; }}
  .metrics-strip {{ display: flex; flex-wrap: wrap; gap: 1px; background: var(--border); border-bottom: 1px solid var(--border); }}
  .footer {{ text-align: center; padding: 32px; color: var(--muted); font-size: 12px; border-top: 1px solid var(--border); margin-top: 32px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 12px; }}
  th {{ text-align: left; padding: 8px 12px; background: var(--surface2); color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
  .bar-label {{ width: 150px; font-size: 12px; color: var(--muted); }}
  .bar-track {{ flex: 1; height: 8px; background: var(--surface2); border-radius: 4px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 4px; }}
  .bar-value {{ width: 40px; font-size: 12px; font-weight: 600; }}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <h1>Nightshift Report</h1>
    <p>{report.repo_name} - Session {report.session_number} - {report.generated_at}</p>
  </div>
  <div style="display:flex;gap:16px;align-items:center">
    <div style="text-align:center">
      <div style="font-size:11px;color:#8b949e">SCORE</div>
      <div style="width:80px;height:80px;border-radius:50%;background:{overall_score_colour};display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:800;color:#0d1117">{report.overall_score:.0f}</div>
    </div>
    <div style="text-align:center">
      <div style="font-size:11px;color:#8b949e">GRADE</div>
      <div style="width:80px;height:80px;border-radius:12px;background:{overall_colour};display:flex;align-items:center;justify-content:center;font-size:32px;font-weight:800;color:#0d1117">{report.overall_grade}</div>
    </div>
  </div>
</div>
<div class="metrics-strip">{metric_cards}</div>
<div class="container">
{sections_html}
<div class="footer">Generated by <a href="https://github.com/gunnargray-dev/nightshift" style="color:#8b949e">Nightshift</a> - {report.generated_at}</div>
</div>
</body>
</html>"""


def _run_cmd(args: list[str], repo_root: Path) -> Optional[dict]:
    """Run a nightshift CLI command and return parsed JSON."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "src.cli"] + args + ["--json"],
            capture_output=True, text=True, cwd=str(repo_root), timeout=60,
        )
        if result.returncode != 0:
            return None
        out = result.stdout
        for i, ch in enumerate(out):
            if ch in ("{", "["):
                return json.loads(out[i:])
        return None
    except Exception:
        return None


def _safe_score(d: Optional[dict], *keys: str) -> Optional[float]:
    if not d:
        return None
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return None
    try:
        return float(d)
    except (TypeError, ValueError):
        return None


# _score_to_grade imported from src.scoring above


def _html_table_from_list(rows: list[dict], columns: list[str]) -> str:
    if not rows:
        return "<p><em>No data available.</em></p>"
    headers = "".join(f"<th>{c}</th>" for c in columns)
    body_rows = []
    for row in rows[:20]:
        cells = "".join(f"<td>{row.get(c, '-')}</td>" for c in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{headers}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def _bar_chart_html(items: list) -> str:
    rows = []
    for label, val, colour in items[:15]:
        rows.append(
            f'<div class="bar-row">'
            f'<div class="bar-label">{label}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{val:.0f}%;background:{colour}"></div></div>'
            f'<div class="bar-value">{val:.0f}</div>'
            f'</div>'
        )
    return f'<div>{"".join(rows)}</div>'


def generate_report(repo_root: Path, session_number: int = 0) -> ExecutiveReport:
    """Build the full executive report by gathering all analysis outputs."""
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    repo_name = repo_root.name

    if session_number == 0:
        log = repo_root / "NIGHTSHIFT_LOG.md"
        if log.exists():
            import re
            matches = re.findall(r"## Session (\d+)", log.read_text())
            if matches:
                session_number = int(matches[-1])

    sections: list[ReportSection] = []
    scores: list[float] = []
    headline: dict = {}

    stats_data = _run_cmd(["stats"], repo_root)
    if stats_data:
        nights = stats_data.get("sessions_count", 0)
        prs = stats_data.get("total_prs", 0)
        commits = stats_data.get("total_commits", 0)
        lines = stats_data.get("total_lines_changed", 0)
        headline.update({"Sessions": nights, "Total PRs": prs, "Commits": commits, "Lines Changed": f"{lines:,}" if isinstance(lines, int) else lines})
        content = _html_table_from_list([{"Metric": k, "Value": v} for k, v in headline.items()], ["Metric", "Value"])
        sections.append(ReportSection(title="Repository Stats", icon="&#128202;", content_html=content))

    health_data = _run_cmd(["health"], repo_root)
    health_score = _safe_score(health_data, "overall_health_score")
    if health_score is None:
        health_score = _safe_score(health_data, "summary", "average_health")
    if health_score is not None:
        scores.append(health_score)
    if health_data:
        files = health_data.get("files", [])
        bar_items = [(f.get("name", ""), float(f.get("health_score", 0)), _score_colour(float(f.get("health_score", 0)))) for f in files[:10]]
        content = f"<p>Overall health: <strong>{health_score:.0f}/100</strong></p>{_bar_chart_html(bar_items)}"
        sections.append(ReportSection(title="Code Health", icon="&#127973;", content_html=content, score=health_score, grade=_score_to_grade(health_score)))

    overall_score = sum(scores) / len(scores) if scores else 75.0
    overall_grade = _score_to_grade(overall_score)

    if "Sessions" not in headline:
        headline["Sessions"] = session_number

    return ExecutiveReport(
        repo_name=repo_name,
        generated_at=now,
        session_number=session_number,
        overall_grade=overall_grade,
        overall_score=overall_score,
        sections=sections,
        headline_metrics=headline,
    )
