"""Nightshift Compare — session-to-session diff engine.

Compares any two Nightshift sessions side-by-side, highlighting what
changed between them in terms of tasks, PRs, modules, stats, and decisions.

Public API
----------
compare_sessions(log_path, session_a, session_b) -> SessionComparison
render_comparison(comparison) -> str  (Markdown)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.session_replay import replay, SessionReplay


@dataclass
class StatDelta:
    """Numeric change between two sessions."""
    label: str
    before: Optional[int]
    after: Optional[int]

    @property
    def delta(self) -> Optional[int]:
        if self.before is None or self.after is None:
            return None
        return self.after - self.before

    @property
    def delta_str(self) -> str:
        if self.delta is None:
            return "?"
        if self.delta > 0:
            return f"+{self.delta}"
        return str(self.delta)

    @property
    def symbol(self) -> str:
        if self.delta is None:
            return "·"
        if self.delta > 0:
            return "▲"
        if self.delta < 0:
            return "▼"
        return "="


@dataclass
class SessionComparison:
    """Side-by-side comparison of two sessions."""
    session_a: int
    session_b: int
    replay_a: Optional[SessionReplay]
    replay_b: Optional[SessionReplay]
    tasks_added: list[str] = field(default_factory=list)
    tasks_removed: list[str] = field(default_factory=list)
    modules_added: list[str] = field(default_factory=list)
    modules_removed: list[str] = field(default_factory=list)
    prs_in_a: list[str] = field(default_factory=list)
    prs_in_b: list[str] = field(default_factory=list)
    stat_deltas: list[StatDelta] = field(default_factory=list)
    decisions_a: list[str] = field(default_factory=list)
    decisions_b: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        return render_comparison(self)

    def to_dict(self) -> dict:
        return {
            "session_a": self.session_a,
            "session_b": self.session_b,
            "tasks_added": self.tasks_added,
            "tasks_removed": self.tasks_removed,
            "modules_added": self.modules_added,
            "modules_removed": self.modules_removed,
            "stat_deltas": [
                {"label": sd.label, "before": sd.before, "after": sd.after, "delta": sd.delta}
                for sd in self.stat_deltas
            ],
        }


def _extract_stat_int(replay: Optional[SessionReplay], stat_name: str) -> Optional[int]:
    """Pull a named integer stat from a SessionReplay stats dict."""
    if replay is None:
        return None
    stats = replay.stats_snapshot or {}
    if isinstance(stats, dict):
        key_map = {
            "nights active": "nights_active",
            "total prs": "total_prs",
            "total commits": "total_commits",
            "lines changed": "lines_changed",
            "test suite": "test_suite",
        }
        key = key_map.get(stat_name.lower())
        if key and key in stats:
            val = stats[key]
            clean = re.sub(r"[~,]", "", str(val)).strip()
            m = re.search(r"\d+", clean)
            if m:
                return int(m.group())
        return None
    stats_text = str(stats)
    pattern = re.compile(rf"{re.escape(stat_name)}[:\s]+(\d[\d,]*)", re.IGNORECASE)
    m = pattern.search(stats_text)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _task_labels(replay: Optional[SessionReplay]) -> list[str]:
    """Return normalised task names from a SessionReplay."""
    if replay is None:
        return []
    return [t.name.lower().strip() for t in replay.tasks]


def _module_names(replay: Optional[SessionReplay]) -> list[str]:
    """Return module names added in a session."""
    if replay is None:
        return []
    return [m.lower().strip() for m in (replay.modules_added or [])]


def _pr_labels(replay: Optional[SessionReplay]) -> list[str]:
    """Return PR reference strings."""
    if replay is None:
        return []
    return [f"#{pr.number}: {pr.title}" for pr in replay.prs]


def _bar(value: Optional[int], max_val: int, width: int = 20) -> str:
    """Horizontal bar for stat visualization."""
    FULL = "█"
    EMPTY = "░"
    if value is None or max_val == 0:
        return EMPTY * width
    filled = round(min(value / max_val, 1.0) * width)
    return FULL * filled + EMPTY * (width - filled)


def compare_sessions(
    log_path: Path,
    session_a: int,
    session_b: int,
) -> SessionComparison:
    """Compare two sessions loaded from NIGHTSHIFT_LOG.md."""
    ra = replay(log_path, session_a)
    rb = replay(log_path, session_b)

    tasks_a = set(_task_labels(ra))
    tasks_b = set(_task_labels(rb))
    modules_a = set(_module_names(ra))
    modules_b = set(_module_names(rb))

    stat_names = ["nights active", "total prs", "total commits", "lines changed", "test suite"]
    stat_deltas: list[StatDelta] = []
    for stat in stat_names:
        before = _extract_stat_int(ra, stat)
        after = _extract_stat_int(rb, stat)
        stat_deltas.append(StatDelta(label=stat.title(), before=before, after=after))

    return SessionComparison(
        session_a=session_a,
        session_b=session_b,
        replay_a=ra,
        replay_b=rb,
        tasks_added=sorted(tasks_b - tasks_a),
        tasks_removed=sorted(tasks_a - tasks_b),
        modules_added=sorted(modules_b - modules_a),
        modules_removed=sorted(modules_a - modules_b),
        prs_in_a=_pr_labels(ra),
        prs_in_b=_pr_labels(rb),
        stat_deltas=stat_deltas,
        decisions_a=(ra.decisions if ra else []),
        decisions_b=(rb.decisions if rb else []),
    )


def render_comparison(cmp: SessionComparison) -> str:
    """Render a SessionComparison as a rich Markdown report."""
    lines: list[str] = []
    sa = f"Session {cmp.session_a}"
    sb = f"Session {cmp.session_b}"

    lines += [f"# Session Comparison: {sa} vs {sb}", ""]

    date_a = cmp.replay_a.date if cmp.replay_a else "?"
    date_b = cmp.replay_b.date if cmp.replay_b else "?"
    lines += [
        f"| | {sa} | {sb} |",
        "| --- | --- | --- |",
        f"| Date | {date_a} | {date_b} |",
        f"| Tasks | {cmp.replay_a.task_count if cmp.replay_a else '?'} | {cmp.replay_b.task_count if cmp.replay_b else '?'} |",
        f"| PRs | {cmp.replay_a.pr_count if cmp.replay_a else '?'} | {cmp.replay_b.pr_count if cmp.replay_b else '?'} |",
        "",
    ]

    lines += ["## Stats Delta", ""]
    lines += ["| Metric | Before | After | Change |", "| --- | ---: | ---: | --- |"]
    for sd in cmp.stat_deltas:
        lines.append(
            f"| {sd.label} | {sd.before or '—'} | {sd.after or '—'} | {sd.symbol} {sd.delta_str} |"
        )
    lines.append("")

    for sd in cmp.stat_deltas:
        if sd.before is None and sd.after is None:
            continue
        max_v = max(sd.before or 0, sd.after or 0, 1)
        bar_a = _bar(sd.before, max_v)
        bar_b = _bar(sd.after, max_v)
        lines.append(f"**{sd.label}**  ")
        lines.append(f"  `{sa}` {bar_a} {sd.before or 0}")
        lines.append(f"  `{sb}` {bar_b} {sd.after or 0}")
        lines.append("")

    lines += ["## Task Diff", ""]
    if cmp.tasks_added:
        lines.append(f"**New in {sb}** ({len(cmp.tasks_added)}):")
        for t in cmp.tasks_added:
            lines.append(f"  + {t}")
        lines.append("")
    if cmp.tasks_removed:
        lines.append(f"**Only in {sa}** ({len(cmp.tasks_removed)}):")
        for t in cmp.tasks_removed:
            lines.append(f"  - {t}")
        lines.append("")
    if not cmp.tasks_added and not cmp.tasks_removed:
        lines += ["_Identical task set across both sessions._", ""]

    if cmp.modules_added or cmp.modules_removed:
        lines += ["## Module Changes", ""]
        if cmp.modules_added:
            lines.append(f"**Added in {sb}:**")
            for m in cmp.modules_added:
                lines.append(f"  + `{m}`")
            lines.append("")
        if cmp.modules_removed:
            lines.append(f"**Only in {sa}:**")
            for m in cmp.modules_removed:
                lines.append(f"  - `{m}`")
            lines.append("")

    if cmp.decisions_a or cmp.decisions_b:
        lines += ["## Decisions", ""]
        if cmp.decisions_a:
            lines.append(f"**{sa}:**")
            for d in cmp.decisions_a[:5]:
                lines.append(f"  · {d[:120]}")
            lines.append("")
        if cmp.decisions_b:
            lines.append(f"**{sb}:**")
            for d in cmp.decisions_b[:5]:
                lines.append(f"  · {d[:120]}")
            lines.append("")

    return "\n".join(lines)
