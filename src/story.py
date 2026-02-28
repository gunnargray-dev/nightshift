"""Repo Story — narrative prose summary of the entire repository's evolution.

Reads NIGHTSHIFT_LOG.md and generates a compelling long-form narrative that
describes *how* the project grew: what problems each session solved, what
architectural decisions were made, and how the codebase matured over time.

The story is structured as chapters (one per session) plus an epilogue that
describes the current state of the system.  Each chapter is written in second-
person voice ("In session 3, you added...") to make it feel like a personal
guided tour of the repo's history.

Output formats:
- Markdown (default, --write writes to docs/story.md)
- JSON (metadata only, --json)

CLI:
    nightshift story [--write] [--json]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionChapter:
    """A single narrative chapter covering one session."""

    session_number: int
    date: str
    theme: str                        # derived from session notes
    features: list[str] = field(default_factory=list)
    pr_count: int = 0
    test_count: int = 0
    lines_changed: int = 0
    decisions: list[str] = field(default_factory=list)
    narrative: str = ""               # generated prose paragraph

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepoStory:
    """The full narrative of the repository's evolution."""

    repo_name: str
    generated_at: str = ""
    total_sessions: int = 0
    total_prs: int = 0
    total_tests: int = 0
    total_lines: int = 0
    chapters: list[SessionChapter] = field(default_factory=list)
    prologue: str = ""
    epilogue: str = ""

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        """Render the full story as Markdown."""
        lines: list[str] = [
            f"# {self.repo_name} — The Story So Far",
            "",
            f"*Generated {self.generated_at}*",
            "",
            "---",
            "",
        ]

        if self.prologue:
            lines += [self.prologue, "", "---", ""]

        for chapter in self.chapters:
            lines += [
                f"## Chapter {chapter.session_number}: {chapter.theme}",
                f"*{chapter.date}*",
                "",
                chapter.narrative,
                "",
            ]
            if chapter.features:
                lines.append("**What was built:**")
                lines.append("")
                for feat in chapter.features:
                    lines.append(f"- {feat}")
                lines.append("")
            if chapter.decisions:
                lines.append("**Key decisions:**")
                lines.append("")
                for dec in chapter.decisions[:2]:  # Top 2 decisions
                    lines.append(f"- _{dec}_")
                lines.append("")
            # Stats for this chapter
            stats_parts = []
            if chapter.pr_count:
                stats_parts.append(f"{chapter.pr_count} PR{'s' if chapter.pr_count != 1 else ''}")
            if chapter.lines_changed:
                stats_parts.append(f"~{chapter.lines_changed:,} lines")
            if chapter.test_count:
                stats_parts.append(f"{chapter.test_count} tests")
            if stats_parts:
                lines.append(f"*Session stats: {' · '.join(stats_parts)}*")
                lines.append("")
            lines.append("---")
            lines.append("")

        if self.epilogue:
            lines += [
                "## Epilogue: The System Today",
                "",
                self.epilogue,
                "",
            ]

        # Aggregate stats footer
        lines += [
            "---",
            "",
            "## By the Numbers",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Sessions | {self.total_sessions} |",
            f"| Pull Requests | {self.total_prs} |",
            f"| Tests | {self.total_tests:,} |",
            f"| Lines Changed | ~{self.total_lines:,} |",
            "",
        ]

        return "\n".join(lines)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_SESSION_HEADER_RE = re.compile(
    r"^## Session (\d+) — (.+)$", re.MULTILINE
)
_THEME_RE = re.compile(r"\*\*Notes:\*\* Session \d+ theme: (.+?)\.", re.IGNORECASE)
_NOTES_RE = re.compile(r"\*\*Notes:\*\*(.+?)(?=\n\n|---|\Z)", re.DOTALL)
_PR_COUNT_RE = re.compile(r"Total PRs:\s*([\d~,]+)")
_TEST_COUNT_RE = re.compile(r"Test suite:\s*([\d,]+)")
_LINES_RE = re.compile(r"Lines changed:\s*~?([\d,]+)")
_TASKS_RE = re.compile(
    r"- [✅⚠️⏭️❓]\s+\*\*(.+?)\*\*.*?—\s+(.+?)(?=\n- [✅⚠️⏭️❓]|\n\n|\Z)",
    re.DOTALL,
)
_DECISION_RE = re.compile(r"^\s*- (.+)$", re.MULTILINE)


def _parse_int(s: str) -> int:
    """Parse a potentially comma-separated or tilde-prefixed integer."""
    cleaned = re.sub(r"[^0-9]", "", s)
    return int(cleaned) if cleaned else 0


def _split_sessions(content: str) -> list[tuple[int, str, str]]:
    """Return list of (session_number, date, section_text) tuples."""
    results = []
    matches = list(_SESSION_HEADER_RE.finditer(content))
    for i, m in enumerate(matches):
        number = int(m.group(1))
        date = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        results.append((number, date, content[start:end]))
    return results


def _extract_features(section: str) -> list[str]:
    """Extract feature names from a session section."""
    features = []
    for m in re.finditer(
        r"- [✅⚠️⏭️❓]\s+\*\*(.+?)\*\*",
        section,
    ):
        name = m.group(1).strip()
        # Remove arrows and PR refs
        name = re.sub(r"\s*→.*$", "", name).strip()
        if name:
            features.append(name)
    return features


def _extract_decisions(section: str) -> list[str]:
    """Extract decisions bullet points."""
    decisions_block_m = re.search(
        r"\*\*Decisions.*?:\*\*(.*?)(?=\*\*Stats snapshot|\*\*Notes|---|\Z)",
        section,
        re.DOTALL,
    )
    if not decisions_block_m:
        return []
    block = decisions_block_m.group(1)
    return [
        m.group(1).strip()
        for m in _DECISION_RE.finditer(block)
        if len(m.group(1).strip()) > 20
    ]


def _extract_theme(section: str, features: list[str]) -> str:
    """Extract or infer the session theme."""
    # Look for explicit "Session N theme:" note
    m = _THEME_RE.search(section)
    if m:
        return m.group(1).strip().title()
    # Infer from notes
    notes_m = _NOTES_RE.search(section)
    if notes_m:
        notes = notes_m.group(1).strip()
        # Grab first sentence
        first = re.split(r"\.\s", notes)[0]
        if len(first) < 80:
            return first.strip(".")
    # Fall back to first feature name
    if features:
        return features[0]
    return f"Session Advances"


def _generate_chapter_narrative(
    session_number: int,
    date: str,
    theme: str,
    features: list[str],
    decisions: list[str],
    pr_count: int,
    lines_changed: int,
    test_count_delta: int,
) -> str:
    """Generate a prose paragraph for a chapter."""

    # Build feature sentence
    if not features:
        feature_sentence = "no new features were logged for this session."
    elif len(features) == 1:
        feature_sentence = f"the focus was entirely on **{features[0]}**."
    elif len(features) == 2:
        feature_sentence = (
            f"two capabilities arrived: **{features[0]}** and **{features[1]}**."
        )
    else:
        listed = ", ".join(f"**{f}**" for f in features[:-1])
        feature_sentence = (
            f"{len(features)} new capabilities arrived: {listed}, and **{features[-1]}**."
        )

    # Build decision flavour
    decision_flavour = ""
    if decisions:
        d = decisions[0]
        # Truncate long decisions
        if len(d) > 120:
            d = d[:117] + "..."
        decision_flavour = f" A guiding principle: _{d}_"

    # Build impact line
    impact_parts = []
    if lines_changed:
        impact_parts.append(f"~{lines_changed:,} lines of code")
    if pr_count:
        impact_parts.append(f"{pr_count} pull request{'s' if pr_count != 1 else ''}")
    if test_count_delta:
        impact_parts.append(f"{test_count_delta} new tests")
    impact = ""
    if impact_parts:
        impact = " The session delivered " + ", ".join(impact_parts) + "."

    # Ordinal for first/last sessions
    ordinals = {
        1: "first",
        2: "second",
        3: "third",
        4: "fourth",
        5: "fifth",
        6: "sixth",
        7: "seventh",
        8: "eighth",
        9: "ninth",
        10: "tenth",
    }
    ordinal = ordinals.get(session_number, f"session {session_number}")

    opening_options = [
        f"On {date}, the {ordinal} session began — and {feature_sentence}",
        f"The {ordinal} session ran on {date}. Its theme was **{theme}**, and {feature_sentence}",
        f"By {date}, the project had grown enough to demand **{theme}**. The {ordinal} session delivered: {feature_sentence}",
        f"Session {session_number} ({date}) tackled **{theme}**. {feature_sentence}",
    ]
    # Pick deterministically by session number
    opening = opening_options[session_number % len(opening_options)]

    return f"{opening}{decision_flavour}{impact}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_story(
    repo_path: Path,
    repo_name: str = "Nightshift",
) -> RepoStory:
    """Generate the full narrative story of the repository.

    Args:
        repo_path: Path to the repository root.
        repo_name: Display name for the repository.

    Returns:
        A RepoStory instance ready for rendering.
    """
    log_path = repo_path / "NIGHTSHIFT_LOG.md"
    if not log_path.exists():
        return RepoStory(
            repo_name=repo_name,
            total_sessions=0,
            prologue="No session history found yet. Run your first nightshift session to start the story.",
        )

    content = log_path.read_text(encoding="utf-8")
    sessions_raw = _split_sessions(content)

    chapters: list[SessionChapter] = []
    cumulative_prs = 0
    prev_tests = 0

    for session_number, date, section in sessions_raw:
        features = _extract_features(section)
        decisions = _extract_decisions(section)
        theme = _extract_theme(section, features)

        # Parse snapshot stats
        prs_total = 0
        m = _PR_COUNT_RE.search(section)
        if m:
            prs_total = _parse_int(m.group(1))

        lines_changed = 0
        m = _LINES_RE.search(section)
        if m:
            lines_changed = _parse_int(m.group(1))

        tests_total = 0
        m = _TEST_COUNT_RE.search(section)
        if m:
            tests_total = _parse_int(m.group(1))

        pr_count = max(0, prs_total - cumulative_prs)
        test_delta = max(0, tests_total - prev_tests)

        narrative = _generate_chapter_narrative(
            session_number=session_number,
            date=date,
            theme=theme,
            features=features,
            decisions=decisions,
            pr_count=pr_count,
            lines_changed=lines_changed,
            test_count_delta=test_delta,
        )

        chapters.append(
            SessionChapter(
                session_number=session_number,
                date=date,
                theme=theme,
                features=features,
                pr_count=pr_count,
                test_count=test_delta,
                lines_changed=lines_changed,
                decisions=decisions[:3],
                narrative=narrative,
            )
        )

        cumulative_prs = max(cumulative_prs, prs_total)
        prev_tests = max(prev_tests, tests_total)

    # Aggregate totals from last snapshot
    last_prs = cumulative_prs
    last_tests = prev_tests
    last_lines = sum(c.lines_changed for c in chapters)

    prologue = _build_prologue(repo_name, len(chapters), last_prs)
    epilogue = _build_epilogue(repo_name, chapters, last_tests, last_prs)

    return RepoStory(
        repo_name=repo_name,
        total_sessions=len(chapters),
        total_prs=last_prs,
        total_tests=last_tests,
        total_lines=last_lines,
        chapters=chapters,
        prologue=prologue,
        epilogue=epilogue,
    )


def _build_prologue(repo_name: str, session_count: int, total_prs: int) -> str:
    """Build the opening prologue paragraph."""
    return (
        f"Every repository has a story. Some are written by committees over years; "
        f"others are hammered out in sprints. **{repo_name}** is different: it was "
        f"written at night, session by session, by an autonomous AI agent that reads "
        f"its own code, measures its own health, and decides what to build next.\n\n"
        f"What follows is that story — told across {session_count} sessions and "
        f"{total_prs} pull requests. It is the story of a system learning to improve "
        f"itself: how it began as a simple stats engine, grew a nervous system of tests "
        f"and health checks, and ultimately became a tool capable of narrating its own "
        f"evolution."
    )


def _build_epilogue(
    repo_name: str,
    chapters: list[SessionChapter],
    total_tests: int,
    total_prs: int,
) -> str:
    """Build the closing epilogue paragraph."""
    # Collect all features across all sessions
    all_features = []
    for c in chapters:
        all_features.extend(c.features)

    total_features = len(all_features)
    session_count = len(chapters)

    return (
        f"After {session_count} sessions, **{repo_name}** is no longer just a dev tool — "
        f"it is a self-documenting, self-measuring, self-improving system. It has "
        f"{total_features} named capabilities, {total_tests:,} tests guarding them, "
        f"and {total_prs} merged pull requests recording every decision.\n\n"
        f"The system can audit its own security, detect its own dead code, trace its own "
        f"architectural coupling, visualize its own dependency graph, and now — tell its "
        f"own story.\n\n"
        f"The next session begins where this one ends: with everything measured, "
        f"nothing assumed, and the question: *what should I build tonight?*"
    )


def save_story(story: RepoStory, output_path: Path) -> None:
    """Save the story as Markdown and a JSON sidecar.

    Args:
        story: The RepoStory to save.
        output_path: Path for the .md file (sibling .json will be created).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(story.to_markdown(), encoding="utf-8")
    output_path.with_suffix(".json").write_text(story.to_json(), encoding="utf-8")
