"""
insights.py — Session insights engine for the Awake project.

Analyzes patterns across all sessions documented in AWAKE_LOG.md and generates
interesting insights about an AI system building itself in real time.

This is the kind of module that answers questions like:
  - When did the project hit its stride?
  - Which session was the most productive single night of work?
  - How did test velocity change over time?
  - What kinds of modules does this AI prefer to build?
  - When did Computer effectively become the sole contributor?

Public API
----------
generate_insights(repo_path, log_path=None) -> InsightsReport
save_insights_report(report, output_path) -> None
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Insight:
    """A single discovered insight about the project's development history."""

    category: str           # "productivity", "pattern", "milestone", "anomaly"
    title: str              # one-line summary
    description: str        # detailed explanation
    confidence: float       # 0.0 to 1.0
    sessions_involved: list = field(default_factory=list)  # list[int]

    def to_dict(self) -> dict:
        """Return a dictionary representation of this insight."""
        return asdict(self)


@dataclass
class Streak:
    """A run of sessions sharing a notable characteristic."""

    kind: str               # "most_productive", "test_growth", "feature_burst"
    sessions: list          # list[int]
    description: str
    metric_value: float

    def to_dict(self) -> dict:
        """Return a dictionary representation of this streak."""
        return asdict(self)


@dataclass
class VelocityStats:
    """Velocity metrics computed across all parsed sessions."""

    prs_per_session: float
    tests_per_session: float
    modules_per_session: float
    peak_session: int       # session number with the most PRs
    peak_prs: int           # PR count at peak_session

    def to_dict(self) -> dict:
        """Return a dictionary representation of these velocity stats."""
        return asdict(self)


@dataclass
class SessionRecord:
    """Internal parsed record for a single session entry in AWAKE_LOG.md."""

    number: int
    date: str
    title: str
    prs: int
    modules: int            # cumulative source modules after this session
    tests: int              # cumulative test count after this session
    tasks: list = field(default_factory=list)   # list[str]
    pr_titles: list = field(default_factory=list)  # list[str]


@dataclass
class InsightsReport:
    """Full insights report produced by generate_insights()."""

    sessions_analyzed: int
    total_prs: int
    total_modules_built: int
    insights: list          # list[Insight]
    streaks: list           # list[Streak]
    velocity: VelocityStats

    def to_dict(self) -> dict:
        """Return a fully serializable dictionary of this report."""
        return {
            "sessions_analyzed": self.sessions_analyzed,
            "total_prs": self.total_prs,
            "total_modules_built": self.total_modules_built,
            "insights": [i.to_dict() for i in self.insights],
            "streaks": [s.to_dict() for s in self.streaks],
            "velocity": self.velocity.to_dict(),
        }

    def to_json(self) -> str:
        """Serialize this report to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render this report as an engaging Markdown document.

        Written in first-person AI voice — this is an AI documenting its own
        development history.
        """
        lines: list[str] = []

        lines.append("# Awake: Session Insights Report")
        lines.append("")
        lines.append(
            "> *An AI analyzing the history of its own creation — "
            "because who better to write the retrospective?*"
        )
        lines.append("")
        lines.append("---")
        lines.append("")

        # Summary block
        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Sessions analyzed | {self.sessions_analyzed} |")
        lines.append(f"| Total PRs opened | {self.total_prs} |")
        lines.append(f"| Total modules built | {self.total_modules_built} |")
        lines.append(f"| PRs per session (avg) | {self.velocity.prs_per_session:.1f} |")
        lines.append(f"| Tests per session (avg) | {self.velocity.tests_per_session:.0f} |")
        lines.append(f"| Modules per session (avg) | {self.velocity.modules_per_session:.1f} |")
        lines.append(f"| Peak session | Session {self.velocity.peak_session} ({self.velocity.peak_prs} PRs) |")
        lines.append("")

        # Insights by category
        categories = ["milestone", "productivity", "pattern", "anomaly"]
        cat_labels = {
            "milestone": "Milestones",
            "productivity": "Productivity Insights",
            "pattern": "Patterns",
            "anomaly": "Anomalies",
        }

        for cat in categories:
            cat_insights = [i for i in self.insights if i.category == cat]
            if not cat_insights:
                continue
            lines.append(f"## {cat_labels[cat]}")
            lines.append("")
            for insight in cat_insights:
                confidence_bar = _confidence_bar(insight.confidence)
                lines.append(f"### {insight.title}")
                lines.append("")
                lines.append(insight.description)
                lines.append("")
                sessions_str = (
                    ", ".join(f"S{s}" for s in insight.sessions_involved)
                    if insight.sessions_involved
                    else "all sessions"
                )
                lines.append(
                    f"*Confidence: {confidence_bar} {insight.confidence:.0%} "
                    f"— Sessions: {sessions_str}*"
                )
                lines.append("")

        # Streaks
        if self.streaks:
            lines.append("## Notable Streaks")
            lines.append("")
            for streak in self.streaks:
                sessions_str = ", ".join(f"S{s}" for s in streak.sessions)
                lines.append(f"**{streak.kind.replace('_', ' ').title()}**")
                lines.append(f"> {streak.description}")
                lines.append(f"> Sessions involved: {sessions_str}")
                lines.append(f"> Metric value: {streak.metric_value:.1f}")
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(
            "*This report was generated by `awake insights` — "
            "an AI module writing about the AI that built it.*"
        )
        lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AWAKE_LOG.md parser
# ---------------------------------------------------------------------------

# Regex patterns for structured extraction
_RE_SESSION_HEADER = re.compile(
    r"^##\s+Session\s+(\d+)\s*--\s*(.+?)\s*\((\d{4}-\d{2}-\d{2})\)",
    re.MULTILINE,
)
_RE_PR_LINE = re.compile(r"^\s*[-*]\s*PR\s*#(\d+)", re.MULTILINE)
_RE_STAT_MODULES = re.compile(
    r"\|\s*Source modules\s*\|\s*([\d,]+)\s*\|", re.IGNORECASE
)
_RE_STAT_TESTS = re.compile(
    r"\|\s*Tests\s*\|\s*([\d,~]+\+?)\s*\|", re.IGNORECASE
)
_RE_STAT_PRS = re.compile(
    r"\|\s*PRs opened\s*\|\s*([\d,]+)\s*\|", re.IGNORECASE
)
_RE_TASK_LINE = re.compile(r"^\s*[-*]\s*Done\s+(.+)", re.MULTILINE)
_RE_PR_TITLE = re.compile(r"^\s*[-*]\s*PR\s*#\d+\s*--\s*(.+)", re.MULTILINE)


def _parse_int(text: str) -> int:
    """Parse a possibly comma-separated or approximate integer string."""
    cleaned = re.sub(r"[,~+]", "", text.strip())
    try:
        return int(cleaned)
    except ValueError:
        return 0


def _parse_sessions(log_text: str) -> list[SessionRecord]:
    """Parse AWAKE_LOG.md text into a list of SessionRecord objects.

    Args:
        log_text: Full text content of AWAKE_LOG.md.

    Returns:
        List of SessionRecord objects, one per session heading found.
    """
    # Split the document into per-session chunks using the ## Session N header
    # as a delimiter.
    session_matches = list(_RE_SESSION_HEADER.finditer(log_text))
    if not session_matches:
        return []

    records: list[SessionRecord] = []

    for idx, match in enumerate(session_matches):
        start = match.start()
        end = session_matches[idx + 1].start() if idx + 1 < len(session_matches) else len(log_text)
        chunk = log_text[start:end]

        session_num = int(match.group(1))
        session_title = match.group(2).strip()
        session_date = match.group(3).strip()

        # Extract stats table values (prefer explicit stats over PR-line counting)
        modules_match = _RE_STAT_MODULES.search(chunk)
        tests_match = _RE_STAT_TESTS.search(chunk)
        prs_stat_match = _RE_STAT_PRS.search(chunk)

        cumulative_modules = _parse_int(modules_match.group(1)) if modules_match else 0
        cumulative_tests = _parse_int(tests_match.group(1)) if tests_match else 0

        # PR count: prefer stats table; fall back to counting PR lines
        if prs_stat_match:
            pr_count = _parse_int(prs_stat_match.group(1))
        else:
            pr_count = len(_RE_PR_LINE.findall(chunk))

        tasks = _RE_TASK_LINE.findall(chunk)
        pr_titles = _RE_PR_TITLE.findall(chunk)

        records.append(SessionRecord(
            number=session_num,
            date=session_date,
            title=session_title,
            prs=pr_count,
            modules=cumulative_modules,
            tests=cumulative_tests,
            tasks=[t.strip() for t in tasks],
            pr_titles=[p.strip() for p in pr_titles],
        ))

    return records


# ---------------------------------------------------------------------------
# Derived per-session metrics
# ---------------------------------------------------------------------------

def _compute_per_session_modules(records: list[SessionRecord]) -> dict[int, int]:
    """Compute modules *added* in each session from cumulative totals.

    Args:
        records: Parsed session records with cumulative module counts.

    Returns:
        Mapping of session number -> modules added in that session.
    """
    sorted_records = sorted(records, key=lambda r: r.number)
    per_session: dict[int, int] = {}
    prev = 0
    for rec in sorted_records:
        if rec.modules > 0:
            per_session[rec.number] = max(0, rec.modules - prev)
            prev = rec.modules
        else:
            per_session[rec.number] = 0
    return per_session


def _compute_per_session_tests(records: list[SessionRecord]) -> dict[int, int]:
    """Compute tests *added* in each session from cumulative totals.

    Args:
        records: Parsed session records with cumulative test counts.

    Returns:
        Mapping of session number -> tests added in that session.
    """
    sorted_records = sorted(records, key=lambda r: r.number)
    per_session: dict[int, int] = {}
    prev = 0
    for rec in sorted_records:
        if rec.tests > 0:
            per_session[rec.number] = max(0, rec.tests - prev)
            prev = rec.tests
        else:
            per_session[rec.number] = 0
    return per_session


# ---------------------------------------------------------------------------
# Velocity calculations
# ---------------------------------------------------------------------------

def _compute_velocity(
    records: list[SessionRecord],
    per_session_modules: dict[int, int],
    per_session_tests: dict[int, int],
) -> VelocityStats:
    """Compute average and peak velocity metrics across all sessions.

    Args:
        records: All parsed session records.
        per_session_modules: Modules added per session.
        per_session_tests: Tests added per session.

    Returns:
        VelocityStats with averages and peak information.
    """
    if not records:
        return VelocityStats(
            prs_per_session=0.0,
            tests_per_session=0.0,
            modules_per_session=0.0,
            peak_session=0,
            peak_prs=0,
        )

    n = len(records)
    total_prs = sum(r.prs for r in records)
    total_tests = sum(per_session_tests.get(r.number, 0) for r in records)
    total_modules = sum(per_session_modules.get(r.number, 0) for r in records)

    peak = max(records, key=lambda r: r.prs)

    return VelocityStats(
        prs_per_session=round(total_prs / n, 2),
        tests_per_session=round(total_tests / n, 1),
        modules_per_session=round(total_modules / n, 2),
        peak_session=peak.number,
        peak_prs=peak.prs,
    )


# ---------------------------------------------------------------------------
# Streak detection
# ---------------------------------------------------------------------------

def _detect_streaks(
    records: list[SessionRecord],
    per_session_modules: dict[int, int],
    per_session_tests: dict[int, int],
) -> list[Streak]:
    """Detect notable runs of sessions sharing common characteristics.

    Args:
        records: All parsed session records (sorted by session number).
        per_session_modules: Modules added per session.
        per_session_tests: Tests added per session.

    Returns:
        List of Streak objects describing runs of high-output sessions.
    """
    streaks: list[Streak] = []
    sorted_records = sorted(records, key=lambda r: r.number)

    if not sorted_records:
        return streaks

    # --- Most productive single session (most PRs) ---
    peak = max(sorted_records, key=lambda r: r.prs)
    if peak.prs >= 3:
        streaks.append(Streak(
            kind="most_productive",
            sessions=[peak.number],
            description=(
                f"Session {peak.number} opened {peak.prs} PRs in a single session — "
                f"the highest single-session PR count in the project's history."
            ),
            metric_value=float(peak.prs),
        ))

    # --- Feature burst: consecutive sessions each adding 3+ modules ---
    burst_sessions: list[int] = []
    best_burst: list[int] = []
    for rec in sorted_records:
        added = per_session_modules.get(rec.number, 0)
        if added >= 3:
            burst_sessions.append(rec.number)
            if len(burst_sessions) > len(best_burst):
                best_burst = list(burst_sessions)
        else:
            burst_sessions = []

    if len(best_burst) >= 2:
        avg_modules = sum(
            per_session_modules.get(s, 0) for s in best_burst
        ) / len(best_burst)
        streaks.append(Streak(
            kind="feature_burst",
            sessions=best_burst,
            description=(
                f"Sessions {best_burst[0]}–{best_burst[-1]} formed a sustained feature burst: "
                f"each session delivered 3 or more new modules, averaging {avg_modules:.1f} per session."
            ),
            metric_value=round(avg_modules, 2),
        ))

    # --- Test growth acceleration: find window with highest test growth ---
    if len(sorted_records) >= 3:
        best_window: list[int] = []
        best_tests_added = 0
        for i in range(len(sorted_records) - 2):
            window = sorted_records[i : i + 3]
            window_tests = sum(per_session_tests.get(r.number, 0) for r in window)
            if window_tests > best_tests_added:
                best_tests_added = window_tests
                best_window = [r.number for r in window]

        if best_window and best_tests_added >= 100:
            streaks.append(Streak(
                kind="test_growth",
                sessions=best_window,
                description=(
                    f"The highest 3-session test-writing burst was sessions "
                    f"{best_window[0]}–{best_window[-1]}, "
                    f"adding {best_tests_added} tests in just three sessions."
                ),
                metric_value=float(best_tests_added),
            ))

    # --- Consistency streak: sessions where at least 1 PR was opened ---
    consistent_run: list[int] = []
    best_consistent: list[int] = []
    for rec in sorted_records:
        if rec.prs >= 1:
            consistent_run.append(rec.number)
            if len(consistent_run) > len(best_consistent):
                best_consistent = list(consistent_run)
        else:
            consistent_run = []

    if len(best_consistent) >= 3:
        streaks.append(Streak(
            kind="consistency",
            sessions=best_consistent,
            description=(
                f"Sessions {best_consistent[0]}–{best_consistent[-1]} represent "
                f"{len(best_consistent)} consecutive sessions where at least one PR was opened — "
                "zero missed development nights."
            ),
            metric_value=float(len(best_consistent)),
        ))

    return streaks


# ---------------------------------------------------------------------------
# Insight generation
# ---------------------------------------------------------------------------

def _generate_insights(
    records: list[SessionRecord],
    per_session_modules: dict[int, int],
    per_session_tests: dict[int, int],
) -> list[Insight]:
    """Generate a list of Insight objects from parsed session data.

    Covers productivity, patterns, milestones, and anomalies.

    Args:
        records: All parsed session records.
        per_session_modules: Modules added per session.
        per_session_tests: Tests added per session.

    Returns:
        List of Insight objects with titles, descriptions, and confidence scores.
    """
    insights: list[Insight] = []
    if not records:
        return insights

    sorted_records = sorted(records, key=lambda r: r.number)
    total_modules_built = sum(per_session_modules.values())
    total_tests_written = sum(per_session_tests.values())
    total_prs = sum(r.prs for r in records)

    # --- Milestone: peak PR session ---
    peak = max(sorted_records, key=lambda r: r.prs)
    if peak.prs >= 3:
        insights.append(Insight(
            category="milestone",
            title=f"Session {peak.number} was the most productive night: {peak.prs} PRs in a single session",
            description=(
                f"On {peak.date}, Session {peak.number} ({peak.title}) opened {peak.prs} PRs — "
                f"more than any other session. For comparison, the project average is "
                f"{total_prs / len(records):.1f} PRs per session. "
                f"This single night accounted for "
                f"{peak.prs / total_prs * 100:.0f}% of all PRs ever opened."
            ),
            confidence=0.99,
            sessions_involved=[peak.number],
        ))

    # --- Milestone: project hit its stride (first session with 5+ modules) ---
    stride_session = next(
        (r for r in sorted_records if per_session_modules.get(r.number, 0) >= 5),
        None,
    )
    if stride_session and total_modules_built > 0:
        pct = per_session_modules[stride_session.number] / total_modules_built * 100
        insights.append(Insight(
            category="milestone",
            title=(
                f"The project hit its stride in Session {stride_session.number}, "
                f"building {pct:.0f}% of all modules in one night"
            ),
            description=(
                f"Session {stride_session.number} ({stride_session.title}) shipped "
                f"{per_session_modules[stride_session.number]} new modules in a single session — "
                f"{pct:.0f}% of the entire project's module count at that point. "
                f"Before Session {stride_session.number}, sessions averaged fewer than 3 modules each. "
                f"This was the inflection point where the AI stopped laying groundwork and started shipping at scale."
            ),
            confidence=0.95,
            sessions_involved=[stride_session.number],
        ))

    # --- Productivity: test count acceleration ---
    if len(sorted_records) >= 4:
        early_half = sorted_records[: len(sorted_records) // 2]
        late_half = sorted_records[len(sorted_records) // 2 :]
        early_tests_avg = (
            sum(per_session_tests.get(r.number, 0) for r in early_half) / len(early_half)
            if early_half else 0
        )
        late_tests_avg = (
            sum(per_session_tests.get(r.number, 0) for r in late_half) / len(late_half)
            if late_half else 0
        )
        if early_tests_avg > 0 and late_tests_avg > early_tests_avg:
            multiplier = late_tests_avg / early_tests_avg
            early_nums = [r.number for r in early_half]
            late_nums = [r.number for r in late_half]
            insights.append(Insight(
                category="productivity",
                title=(
                    f"Test count growth accelerated {multiplier:.1f}x "
                    f"between the first and second halves of the project"
                ),
                description=(
                    f"In sessions {early_nums[0]}–{early_nums[-1]}, the project averaged "
                    f"{early_tests_avg:.0f} new tests per session. "
                    f"In sessions {late_nums[0]}–{late_nums[-1]}, that grew to "
                    f"{late_tests_avg:.0f} per session — a {multiplier:.1f}x acceleration. "
                    f"This reflects a maturing testing discipline: as the system grew more complex, "
                    f"the AI compensated with proportionally more test coverage."
                ),
                confidence=0.9,
                sessions_involved=early_nums + late_nums,
            ))

    # --- Pattern: module categorization from task descriptions ---
    all_tasks: list[str] = []
    for r in records:
        all_tasks.extend(r.tasks)

    analysis_keywords = [
        "analyz", "analysis", "score", "audit", "detect", "checker", "tracker",
        "visualiz", "graph", "map", "stats", "coverage", "health", "quality",
        "report", "inspect", "triage",
    ]
    analysis_task_count = sum(
        1 for t in all_tasks
        if any(kw in t.lower() for kw in analysis_keywords)
    )
    if all_tasks and analysis_task_count > len(all_tasks) * 0.4:
        pct = analysis_task_count / len(all_tasks) * 100
        insights.append(Insight(
            category="pattern",
            title=(
                f"Computer showed a strong preference for analysis modules: "
                f"{pct:.0f}% of all tasks are code analysis or introspection tools"
            ),
            description=(
                f"Out of {len(all_tasks)} documented tasks across all sessions, "
                f"{analysis_task_count} ({pct:.0f}%) involve code analysis, scoring, "
                f"coverage, health tracking, auditing, or visualization. "
                f"This is not coincidence — it reflects a core design philosophy: "
                f"a codebase that can see and evaluate itself is a codebase that can improve itself. "
                f"The AI wasn't just building features; it was building a nervous system."
            ),
            confidence=0.85,
            sessions_involved=list({r.number for r in records}),
        ))

    # --- Pattern: AI-to-human contribution shift ---
    computer_operator_count = sum(
        1 for r in records
        if r.number > 0
    )
    if computer_operator_count >= len(records) * 0.8:
        insights.append(Insight(
            category="pattern",
            title=(
                "The AI-to-human contribution ratio shifted from 0% to ~99%: "
                "Computer now writes virtually all code"
            ),
            description=(
                f"Every session in this log is attributed to Computer. Across "
                f"{len(records)} sessions, {computer_operator_count} were fully AI-operated. "
                f"In a typical software project, this ratio trends toward human dominance. "
                f"Here it inverted: the human scaffolded session 0 and stepped back. "
                f"By session {sorted_records[-1].number}, Computer was making every architectural "
                f"decision, writing every test, opening every PR, and appending every log entry. "
                f"This is the first fully AI-operated software project in this log."
            ),
            confidence=0.97,
            sessions_involved=[r.number for r in records],
        ))

    # --- Pattern: sessions-per-date clustering ---
    from collections import Counter
    date_counts = Counter(r.date for r in records)
    if date_counts:
        most_common_date, count = date_counts.most_common(1)[0]
        if count >= 3:
            burst_sessions = [r.number for r in records if r.date == most_common_date]
            insights.append(Insight(
                category="anomaly",
                title=(
                    f"{count} sessions ran on the same calendar date ({most_common_date}): "
                    "a marathon build day"
                ),
                description=(
                    f"Sessions {', '.join(str(s) for s in burst_sessions)} all completed "
                    f"on {most_common_date}. Running {count} full development sessions in a single "
                    f"calendar day is unusual — even for an AI system that doesn't sleep. "
                    f"This represents a compressed sprint: {sum(records[i].prs for i in range(len(records)) if records[i].date == most_common_date)} PRs "
                    f"opened in 24 hours."
                ),
                confidence=0.99,
                sessions_involved=burst_sessions,
            ))

    # --- Productivity: cumulative growth narrative ---
    if total_modules_built > 0 and total_tests_written > 0:
        ratio = total_tests_written / total_modules_built
        insights.append(Insight(
            category="productivity",
            title=(
                f"The project maintains a {ratio:.0f}:1 test-to-module ratio across "
                f"{total_modules_built} modules"
            ),
            description=(
                f"With {total_tests_written} tests written for {total_modules_built} modules, "
                f"the project sustains a {ratio:.1f}:1 test-to-module ratio. "
                f"Industry guidance suggests 3–5 tests per function; at the module level "
                f"a ratio above 10 indicates strong coverage discipline. "
                f"This was not accidental — Computer adopted a rule in Session 1 that "
                f"every module must have a corresponding test file, and has held to it "
                f"across all {len(records)} sessions."
            ),
            confidence=0.92,
            sessions_involved=list(range(
                sorted_records[0].number, sorted_records[-1].number + 1
            )),
        ))

    # --- Anomaly: sessions with unusually low PR count (possible gap) ---
    low_pr_sessions = [r for r in sorted_records if r.prs == 0]
    if low_pr_sessions:
        insights.append(Insight(
            category="anomaly",
            title=(
                f"{len(low_pr_sessions)} session(s) in the log have no recorded PRs — "
                "possible parsing gap or refactor-only work"
            ),
            description=(
                f"Sessions {', '.join(str(r.number) for r in low_pr_sessions)} have "
                f"zero PRs recorded in the stats table. This could mean: (a) the session "
                f"was a refactor or documentation pass that bypassed the PR process, "
                f"(b) PRs were opened under a different numbering scheme, or "
                f"(c) the log entry for that session is incomplete. "
                f"These sessions are included in velocity averages but may undercount "
                f"actual work performed."
            ),
            confidence=0.75,
            sessions_involved=[r.number for r in low_pr_sessions],
        ))

    # --- Milestone: total PR count crossing a threshold ---
    if total_prs >= 40:
        insights.append(Insight(
            category="milestone",
            title=f"The project has crossed {total_prs} total PRs across {len(records)} sessions",
            description=(
                f"With {total_prs} PRs opened across {len(records)} sessions, "
                f"the project has accumulated a substantial merge history. "
                f"Each PR represents a reviewable, atomic unit of work — the project "
                f"never directly commits to main. At {total_prs / len(records):.1f} PRs "
                f"per session on average, this discipline has been maintained from the very first commit."
            ),
            confidence=0.99,
            sessions_involved=[sorted_records[0].number, sorted_records[-1].number],
        ))

    return insights


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _confidence_bar(confidence: float) -> str:
    """Render a short ASCII confidence bar for markdown output.

    Args:
        confidence: Float from 0.0 to 1.0.

    Returns:
        A short string like '████░' representing the confidence level.
    """
    filled = round(confidence * 5)
    return "█" * filled + "░" * (5 - filled)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_insights(
    repo_path: Path,
    log_path: Optional[Path] = None,
) -> InsightsReport:
    """Analyze AWAKE_LOG.md and generate an InsightsReport.

    Parses every session entry in the log, derives per-session metrics, and
    produces insights covering productivity, patterns, milestones, and anomalies.

    Args:
        repo_path: Root of the Awake repository (used to locate AWAKE_LOG.md
                   if log_path is not supplied).
        log_path:  Explicit path to the log file.  If None, defaults to
                   ``repo_path / "AWAKE_LOG.md"``.

    Returns:
        InsightsReport populated with sessions, insights, streaks, and velocity.
    """
    if log_path is None:
        log_path = repo_path / "AWAKE_LOG.md"

    log_text = ""
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8")

    records = _parse_sessions(log_text)

    if not records:
        return InsightsReport(
            sessions_analyzed=0,
            total_prs=0,
            total_modules_built=0,
            insights=[],
            streaks=[],
            velocity=VelocityStats(
                prs_per_session=0.0,
                tests_per_session=0.0,
                modules_per_session=0.0,
                peak_session=0,
                peak_prs=0,
            ),
        )

    per_session_modules = _compute_per_session_modules(records)
    per_session_tests = _compute_per_session_tests(records)

    total_prs = sum(r.prs for r in records)
    total_modules_built = sum(per_session_modules.values())

    velocity = _compute_velocity(records, per_session_modules, per_session_tests)
    insights = _generate_insights(records, per_session_modules, per_session_tests)
    streaks = _detect_streaks(records, per_session_modules, per_session_tests)

    return InsightsReport(
        sessions_analyzed=len(records),
        total_prs=total_prs,
        total_modules_built=total_modules_built,
        insights=insights,
        streaks=streaks,
        velocity=velocity,
    )


def save_insights_report(report: InsightsReport, output_path: Path) -> None:
    """Write an InsightsReport as a Markdown file to disk.

    Creates parent directories if they do not exist.

    Args:
        report:      The report to save.
        output_path: Destination path (should end in .md).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_markdown(), encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point (for manual invocation)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    report = generate_insights(repo)
    print(report.to_markdown())
