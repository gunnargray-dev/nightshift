"""Terminal dashboard for Nightshift.

Renders a rich terminal overview using box-drawing characters showing all key
Nightshift metrics in a single glance.  No external libraries required — all
layout is done with pure Python string manipulation.

CLI usage
---------
    nightshift dashboard
    nightshift dashboard --write       # saves to docs/dashboard.txt
    nightshift dashboard --json        # raw JSON data
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Box-drawing helpers
# ---------------------------------------------------------------------------

# Single-line box characters
_TL = "┌"
_TR = "┐"
_BL = "└"
_BR = "┘"
_H  = "─"
_V  = "│"
_ML = "├"
_MR = "┤"
_TM = "┬"
_BM = "┴"
_CROSS = "┼"


def _box(title: str, lines: list[str], width: int = 54) -> str:
    """Render a box with a title bar and body lines."""
    inner = width - 2  # space between │ and │
    title_padded = f" {title} "
    top_fill = inner - len(title_padded)
    left_fill = top_fill // 2
    right_fill = top_fill - left_fill

    header = _TL + _H * left_fill + title_padded + _H * right_fill + _TR
    divider = _ML + _H * inner + _MR
    footer = _BL + _H * inner + _BR

    body_lines = [header]
    for line in lines:
        # Truncate or pad to inner width
        padded = line[:inner].ljust(inner)
        body_lines.append(f"{_V}{padded}{_V}")
    body_lines.append(footer)
    return "\n".join(body_lines)


def _bar(value: float, max_value: float = 100.0, width: int = 20) -> str:
    """Render a simple ASCII progress bar."""
    pct = min(max(value / max_value, 0.0), 1.0)
    filled = int(pct * width)
    empty = width - filled
    inner_fill = "\u2588" * (filled - 1) if filled > 0 else ""
    inner_empty = "\u2591" * (empty - 1) if empty > 0 else ""
    return f"[\u2588{inner_fill}\u2591{inner_empty}] {value:.0f}/{max_value:.0f}"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DashboardPanel:
    """A named panel with key-value pairs for display."""

    title: str
    items: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"title": self.title, "items": dict(self.items)}


@dataclass
class DashboardData:
    """The full set of data shown in the dashboard."""

    generated_at: str = ""
    repo_path: str = ""
    panels: list[DashboardPanel] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "repo_path": self.repo_path,
            "panels": [p.to_dict() for p in self.panels],
        }


# ---------------------------------------------------------------------------
# Dashboard construction
# ---------------------------------------------------------------------------


def build_dashboard(repo_path: Optional[Path] = None) -> DashboardData:
    """Collect data from all available Nightshift modules and build DashboardData.

    Gracefully skips any module that fails to load or produces no data.

    Args:
        repo_path: Repository root. Defaults to CWD.

    Returns:
        DashboardData ready for rendering.
    """
    repo = repo_path or Path.cwd()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    dash = DashboardData(
        generated_at=ts,
        repo_path=str(repo),
    )

    # --- Health panel ---
    try:
        from src.health import generate_health_report
        rpt = generate_health_report(repo_path=repo)
        panel = DashboardPanel(title="Code Health")
        panel.items = [
            ("Score", f"{rpt.overall_health_score}/100"),
            ("Files analysed", str(len(rpt.files))),
            ("Total lines", str(rpt.total_lines)),
            ("Functions", str(rpt.total_functions)),
            ("Docstring cov", f"{rpt.overall_docstring_coverage:.0%}"),
            ("TODOs", str(rpt.total_todos)),
            ("Long lines", str(rpt.total_long_lines)),
        ]
        dash.panels.append(panel)
        dash.raw["health_score"] = rpt.overall_health_score
    except Exception as exc:
        dash.panels.append(DashboardPanel(title="Code Health", items=[("status", f"unavailable ({exc})")])) 

    # --- Stats panel ---
    try:
        from src.stats import compute_stats
        log_path = repo / "NIGHTSHIFT_LOG.md"
        stats = compute_stats(repo_path=repo, log_path=log_path)
        panel = DashboardPanel(title="Repository Stats")
        panel.items = [
            ("Nights active", str(stats.nights_active)),
            ("Total PRs", str(stats.total_prs)),
            ("Total commits", str(stats.total_commits)),
            ("Lines changed", str(stats.lines_changed)),
            ("Sessions logged", str(len(stats.sessions))),
        ]
        dash.panels.append(panel)
        dash.raw["stats"] = stats.to_dict()
    except Exception as exc:
        dash.panels.append(DashboardPanel(title="Repository Stats", items=[("status", f"unavailable ({exc})")])) 

    # --- Config panel ---
    try:
        from src.config import load_config
        cfg = load_config(repo)
        panel = DashboardPanel(title="Configuration")
        source = getattr(cfg, "_source", None) or "built-in defaults"
        panel.items = [
            ("Source", str(source).replace(str(repo) + "/", "") if source else "defaults"),
            ("Health min", str(cfg.thresholds.health_score_min)),
            ("Max line len", str(cfg.thresholds.max_line_length)),
            ("Output format", cfg.output.default_format),
            ("Unicode", str(cfg.output.unicode_symbols)),
        ]
        dash.panels.append(panel)
    except Exception as exc:
        dash.panels.append(DashboardPanel(title="Configuration", items=[("status", f"unavailable ({exc})")])) 

    # --- Session summary panel ---
    try:
        from src.stats import parse_nightshift_log
        log_path = repo / "NIGHTSHIFT_LOG.md"
        sessions = parse_nightshift_log(log_path)
        panel = DashboardPanel(title="Session Summary")
        if sessions:
            latest = sessions[-1]
            panel.items = [
                ("Latest session", f"#{latest['session']} ({latest['date']})"),
                ("Sessions total", str(len(sessions))),
                ("Latest PRs", str(latest.get("prs", 0))),
                ("Latest tasks", str(latest.get("tasks", 0))),
            ]
        else:
            panel.items = [("status", "No sessions in log")]
        dash.panels.append(panel)
    except Exception as exc:
        dash.panels.append(DashboardPanel(title="Session Summary", items=[("status", f"unavailable ({exc})")])) 

    return dash


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_DASH_WIDTH = 58


def render_dashboard(dash: DashboardData) -> str:
    """Render DashboardData as a rich terminal string using box-drawing chars."""
    header_line = "═" * _DASH_WIDTH
    title = f"  🌙 NIGHTSHIFT DASHBOARD  ·  {dash.generated_at}"

    sections = [
        f"╔{header_line}╗",
        f"║{title.center(_DASH_WIDTH)}║",
        f"╚{header_line}╝",
        "",
    ]

    for panel in dash.panels:
        inner_w = _DASH_WIDTH - 2
        title_str = f" {panel.title} "
        top_fill = inner_w - len(title_str)
        left = top_fill // 2
        right = top_fill - left
        sections.append(_TL + _H * left + title_str + _H * right + _TR)

        for label, value in panel.items:
            label_col = f" {label}:".ljust(25)
            value_col = str(value)
            # Special rendering for score metrics
            if "score" in label.lower() and "/" in value:
                try:
                    score_val, score_max = value.split("/")
                    bar = _bar(float(score_val), float(score_max), width=15)
                    line_content = f"{label_col}{bar}"
                except Exception:
                    line_content = f"{label_col}{value_col}"
            else:
                line_content = f"{label_col}{value_col}"

            # Pad to inner_w
            line_content = line_content[:inner_w].ljust(inner_w)
            sections.append(f"{_V}{line_content}{_V}")

        sections.append(_BL + _H * inner_w + _BR)
        sections.append("")

    # Footer
    sections.append(f"  Repo: {dash.repo_path}")
    sections.append("")

    return "\n".join(sections)
