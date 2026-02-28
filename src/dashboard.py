"""Nightshift Dashboard — rich terminal dashboard with box-drawing characters.

Renders a self-contained terminal dashboard showing all key Nightshift
metrics at a glance: health score, complexity, coupling, test stats,
session count, and recent session timeline.

Public API
----------
build_dashboard(repo_path) -> Dashboard
render_dashboard(dashboard) -> str
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


_BOX_HEAVY = {
    "tl": "┏", "tr": "┓", "bl": "┗", "br": "┛",
    "h": "━", "v": "┃", "ml": "┣", "mr": "┫", "mt": "┳", "mb": "┻", "mc": "╋",
}
_BOX_LIGHT = {
    "tl": "┌", "tr": "┐", "bl": "└", "br": "┘",
    "h": "─", "v": "│", "ml": "├", "mr": "┤", "mt": "┬", "mb": "┴", "mc": "┼",
}

_FULL_BLOCK = "█"
_LIGHT_BLOCK = "░"


def _hline(width: int, style: dict = _BOX_LIGHT) -> str:
    return style["h"] * width


def _top_border(width: int, title: str = "", style: dict = _BOX_LIGHT) -> str:
    if title:
        title_str = f" {title} "
        padding = width - 2 - len(title_str)
        left = padding // 2
        right = padding - left
        return style["tl"] + style["h"] * left + title_str + style["h"] * right + style["tr"]
    return style["tl"] + _hline(width - 2, style) + style["tr"]


def _bottom_border(width: int, style: dict = _BOX_LIGHT) -> str:
    return style["bl"] + _hline(width - 2, style) + style["br"]


def _mid_border(width: int, style: dict = _BOX_LIGHT) -> str:
    return style["ml"] + _hline(width - 2, style) + style["mr"]


def _row(content: str, width: int, style: dict = _BOX_LIGHT) -> str:
    inner = width - 2
    content_str = str(content)
    if len(content_str) > inner:
        content_str = content_str[: inner - 1] + "…"
    return style["v"] + content_str.ljust(inner) + style["v"]


def _bar_h(value: float, max_val: float, width: int = 20, label: str = "") -> str:
    """Horizontal bar from 0..max_val."""
    ratio = min(value / max(max_val, 1), 1.0)
    filled = round(ratio * width)
    bar = _FULL_BLOCK * filled + _LIGHT_BLOCK * (width - filled)
    pct = f"{ratio * 100:.0f}%"
    return f"{bar} {pct:>4}  {label}"


def _sparkline(values: list[float]) -> str:
    """Unicode sparkline from a list of values."""
    CHARS = " ▁▂▃▄▅▆▇█"
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo or 1
    return "".join(CHARS[round((v - lo) / span * (len(CHARS) - 1))] for v in values)


def _git(cmd: list[str], cwd: Path) -> str:
    import subprocess
    try:
        result = subprocess.run(["git"] + cmd, cwd=cwd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except Exception:
        return ""


def _count_lines(path: Path) -> int:
    try:
        return sum(1 for _ in path.open())
    except OSError:
        return 0


def _parse_log_sessions(log_path: Path) -> list[dict[str, Any]]:
    """Extract session numbers and PR counts from NIGHTSHIFT_LOG.md."""
    if not log_path.exists():
        return []
    text = log_path.read_text(encoding="utf-8")
    sessions = []
    for m in re.finditer(r"## Session (\d+).*?\n.*?Total PRs:\s*(\d+)", text, re.DOTALL):
        sessions.append({"number": int(m.group(1)), "total_prs": int(m.group(2))})
    return sorted(sessions, key=lambda s: s["number"])


def _load_health_history(repo_path: Path) -> list[dict[str, Any]]:
    hp = repo_path / "docs" / "health_history.json"
    if hp.exists():
        try:
            return json.loads(hp.read_text())
        except Exception:
            return []
    return []


def _load_complexity_history(repo_path: Path) -> list[dict[str, Any]]:
    cp = repo_path / "docs" / "complexity_history.json"
    if cp.exists():
        try:
            return json.loads(cp.read_text())
        except Exception:
            return []
    return []


@dataclass
class DashboardSection:
    title: str
    rows: list[str] = field(default_factory=list)


@dataclass
class Dashboard:
    """All data needed to render the terminal dashboard."""
    repo_name: str = "nightshift"
    nights_active: int = 0
    total_prs: int = 0
    total_commits: int = 0
    total_tests: int = 0
    src_files: int = 0
    src_lines: int = 0
    test_files: int = 0
    health_score: Optional[float] = None
    avg_complexity: Optional[float] = None
    avg_instability: Optional[float] = None
    health_trend: list[float] = field(default_factory=list)
    complexity_trend: list[float] = field(default_factory=list)
    recent_sessions: list[dict] = field(default_factory=list)
    sections: list[DashboardSection] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repo_name": self.repo_name,
            "nights_active": self.nights_active,
            "total_prs": self.total_prs,
            "total_commits": self.total_commits,
            "total_tests": self.total_tests,
            "src_files": self.src_files,
            "src_lines": self.src_lines,
            "health_score": self.health_score,
            "avg_complexity": self.avg_complexity,
            "avg_instability": self.avg_instability,
        }

    def to_markdown(self) -> str:
        return render_dashboard(self)


def build_dashboard(repo_path: Path) -> Dashboard:
    """Collect all metrics and return a Dashboard ready for rendering."""
    dash = Dashboard(repo_name=repo_path.name)

    commits = _git(["rev-list", "--count", "HEAD"], repo_path)
    dash.total_commits = int(commits) if commits.isdigit() else 0

    src_dir = repo_path / "src"
    if src_dir.exists():
        py_files = [f for f in src_dir.glob("*.py") if not f.name.startswith("_")]
        dash.src_files = len(py_files)
        dash.src_lines = sum(_count_lines(f) for f in py_files)

    tests_dir = repo_path / "tests"
    if tests_dir.exists():
        dash.test_files = len(list(tests_dir.glob("test_*.py")))

    log_path = repo_path / "NIGHTSHIFT_LOG.md"
    sessions = _parse_log_sessions(log_path)
    dash.nights_active = len(sessions)
    dash.recent_sessions = sessions[-5:]
    if sessions:
        dash.total_prs = sessions[-1].get("total_prs", 0)

    health_history = _load_health_history(repo_path)
    if health_history:
        scores = [h.get("overall_score", h.get("score", 0)) for h in health_history if h]
        scores = [s for s in scores if s]
        if scores:
            dash.health_score = scores[-1]
            dash.health_trend = scores[-10:]

    if dash.health_score is None:
        try:
            from src.health import generate_health_report
            report = generate_health_report(repo_path=repo_path)
            dash.health_score = report.overall_health_score
        except Exception:
            pass

    complexity_history = _load_complexity_history(repo_path)
    if complexity_history:
        avgs = [h.get("global_avg", 0) for h in complexity_history if h]
        avgs = [a for a in avgs if a]
        if avgs:
            dash.avg_complexity = avgs[-1]
            dash.complexity_trend = avgs[-10:]

    if dash.avg_complexity is None:
        try:
            from src.complexity import analyze_complexity
            report = analyze_complexity(repo_path=repo_path)
            dash.avg_complexity = report.global_avg
        except Exception:
            pass

    try:
        from src.coupling import analyze_coupling
        report = analyze_coupling(repo_path=repo_path)
        dash.avg_instability = report.avg_instability
    except Exception:
        pass

    total_tests = 0
    if tests_dir.exists():
        for tf in tests_dir.glob("test_*.py"):
            try:
                text = tf.read_text(encoding="utf-8")
                total_tests += len(re.findall(r"^\s*def test_", text, re.MULTILINE))
            except OSError:
                pass
    dash.total_tests = total_tests
    return dash


_DASH_WIDTH = 72


def render_dashboard(dash: Dashboard) -> str:
    """Render a Dashboard as a box-drawing terminal dashboard string."""
    W = _DASH_WIDTH
    S = _BOX_HEAVY
    L = _BOX_LIGHT
    lines: list[str] = []

    title = f"  🌙  NIGHTSHIFT DASHBOARD  ·  {dash.repo_name.upper()}  "
    pad = W - 2 - len(title)
    lpad = pad // 2
    rpad = pad - lpad
    lines.append(S["tl"] + S["h"] * lpad + title + S["h"] * rpad + S["tr"])
    lines.append(S["v"] + " " * (W - 2) + S["v"])

    card_w = (W - 2) // 4
    labels = ["Nights Active", "Total PRs", "Commits", "Test Cases"]
    values = [str(dash.nights_active), str(dash.total_prs), str(dash.total_commits), str(dash.total_tests)]

    card_tops = L["tl"] + L["h"] * (card_w - 2) + L["tr"]
    lines.append(S["v"] + " " + (card_tops * 4)[: W - 4] + " " + S["v"])

    val_rows = [L["v"] + v.center(card_w - 2)[:card_w - 2] + L["v"] for v in values]
    lines.append(S["v"] + " " + "".join(val_rows) + " " + S["v"])

    lbl_rows = [L["v"] + l.center(card_w - 2)[:card_w - 2] + L["v"] for l in labels]
    lines.append(S["v"] + " " + "".join(lbl_rows) + " " + S["v"])

    card_bots = L["bl"] + L["h"] * (card_w - 2) + L["br"]
    lines.append(S["v"] + " " + (card_bots * 4)[: W - 4] + " " + S["v"])
    lines.append(S["v"] + " " * (W - 2) + S["v"])

    lines.append(_mid_border(W, S))
    lines.append(_row("  SOURCE", W, S))
    lines.append(S["v"] + " " * (W - 2) + S["v"])
    lines.append(_row(f"  Modules  {_bar_h(dash.src_files, 30, 24, str(dash.src_files) + ' modules')}", W, S))
    lines.append(_row(f"  Lines    {_bar_h(dash.src_lines, 30000, 24, f'{dash.src_lines:,} lines')}", W, S))
    lines.append(_row(f"  Tests    {_bar_h(dash.test_files, 30, 24, str(dash.test_files) + ' test files')}", W, S))
    lines.append(S["v"] + " " * (W - 2) + S["v"])

    lines.append(_mid_border(W, S))
    lines.append(_row("  METRICS", W, S))
    lines.append(S["v"] + " " * (W - 2) + S["v"])

    health_val = dash.health_score or 0
    lines.append(_row(f"  Health      {_bar_h(health_val, 100, 24, f'{health_val:.0f}/100')}", W, S))
    if dash.health_trend:
        lines.append(_row(f"              trend {_sparkline(dash.health_trend)}", W, S))
    if dash.avg_complexity is not None:
        lines.append(_row(f"  Complexity  {_bar_h(dash.avg_complexity, 20, 24, f'avg CC {dash.avg_complexity:.1f}')}", W, S))
        if dash.complexity_trend:
            lines.append(_row(f"              trend {_sparkline(dash.complexity_trend)}", W, S))
    if dash.avg_instability is not None:
        lines.append(_row(f"  Coupling    {_bar_h(dash.avg_instability, 1.0, 24, f'avg I={dash.avg_instability:.2f}')}", W, S))
    lines.append(S["v"] + " " * (W - 2) + S["v"])

    if dash.recent_sessions:
        lines.append(_mid_border(W, S))
        lines.append(_row("  RECENT SESSIONS", W, S))
        lines.append(S["v"] + " " * (W - 2) + S["v"])
        for s in dash.recent_sessions[-5:]:
            num = s.get("number", "?")
            prs = s.get("total_prs", 0)
            bar_prs = _bar_h(int(prs) if isinstance(prs, int) else 0, 30, 20, f"PRs: {prs}")
            lines.append(_row(f"  Session {num:>2}  {bar_prs}", W, S))
        lines.append(S["v"] + " " * (W - 2) + S["v"])

    lines.append(S["bl"] + S["h"] * (W - 2) + S["br"])
    return "\n".join(lines)
