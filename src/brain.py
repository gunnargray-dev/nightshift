"""The Brain — Awake task prioritization engine.

Decides what to work on in the next session by scoring candidate tasks against
multiple signals: open issues (triaged), ROADMAP.md backlog items, recent code
health, and cross-module coverage gaps.

The scoring model is transparent: every TaskCandidate carries a breakdown of
exactly why it scored the way it did.  Computer runs ``src/brain.py`` at the
start of every session to get its ordered work queue.

Score components (0-100 total):
- Issue urgency score    (0-35): human-priority issues, bug severity, comment count
- Roadmap alignment      (0-25): item appears in ROADMAP.md backlog
- Health improvement     (0-20): target improves low-scoring health areas
- Complexity fit         (0-10): neither trivially small nor unreachably large
- Cross-module synergy   (0-10): touches multiple existing modules = higher leverage

Usage::

    from src.brain import Brain
    brain = Brain(repo_path=Path("."))
    plan = brain.plan(session_number=5)
    for task in plan.top_tasks:
        print(task.title, task.score)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """Transparent breakdown of how a TaskCandidate scored."""

    issue_urgency: float = 0.0
    roadmap_alignment: float = 0.0
    health_improvement: float = 0.0
    complexity_fit: float = 0.0
    cross_module_synergy: float = 0.0

    @property
    def total(self) -> float:
        """Sum of all score components."""
        return (
            self.issue_urgency
            + self.roadmap_alignment
            + self.health_improvement
            + self.complexity_fit
            + self.cross_module_synergy
        )

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "issue_urgency": self.issue_urgency,
            "roadmap_alignment": self.roadmap_alignment,
            "health_improvement": self.health_improvement,
            "complexity_fit": self.complexity_fit,
            "cross_module_synergy": self.cross_module_synergy,
            "total": self.total,
        }


@dataclass
class TaskCandidate:
    """A candidate task for the next session with its priority score."""

    title: str
    description: str
    source: str  # "issue", "roadmap", "health", "generated"
    score: float = 0.0
    breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    rationale: str = ""
    estimated_prs: int = 1
    related_modules: list[str] = field(default_factory=list)
    related_issue_numbers: list[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "score": round(self.score, 2),
            "breakdown": self.breakdown.to_dict(),
            "rationale": self.rationale,
            "estimated_prs": self.estimated_prs,
            "related_modules": self.related_modules,
            "related_issue_numbers": self.related_issue_numbers,
        }

    def to_markdown_row(self) -> str:
        """Single table row for the session plan."""
        source_badge = {
            "issue": "🔵 issue",
            "roadmap": "🗺️ roadmap",
            "health": "❤️ health",
            "generated": "🤖 generated",
        }.get(self.source, self.source)
        modules = ", ".join(f"`{m}`" for m in self.related_modules[:3]) or "—"
        return (
            f"| **{self.title}** | {round(self.score, 1)}/100 | {source_badge} "
            f"| {modules} | {self.rationale[:80]} |"
        )


@dataclass
class SessionPlan:
    """The complete plan for the next session."""

    session_number: int
    generated_at: str
    all_candidates: list[TaskCandidate]
    top_tasks: list[TaskCandidate]

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "session_number": self.session_number,
            "generated_at": self.generated_at,
            "top_tasks": [t.to_dict() for t in self.top_tasks],
            "all_candidates": [t.to_dict() for t in self.all_candidates],
        }

    def to_markdown(self) -> str:
        """Render as a Markdown session brief."""
        lines = [
            f"# Session {self.session_number} Plan",
            "",
            f"*Generated: {self.generated_at}*",
            f"*{len(self.all_candidates)} candidates evaluated, top {len(self.top_tasks)} selected*",
            "",
            "## Recommended Tasks",
            "",
            "| Task | Score | Source | Modules | Rationale |",
            "|------|-------|--------|---------|-----------|" ,
        ]
        for task in self.top_tasks:
            lines.append(task.to_markdown_row())
        lines += [
            "",
            "## Full Candidate List",
            "",
            "| Task | Score | Source | Modules | Rationale |",
            "|------|-------|--------|---------|-----------|" ,
        ]
        for task in sorted(self.all_candidates, key=lambda t: -t.score):
            lines.append(task.to_markdown_row())
        lines += ["", "---", "", "*Plan generated by `src/brain.py`.*"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_ROADMAP_BACKLOG_PATTERNS = [
    r"\bcontribut(ion|ing)\b",
    r"\bdashboard\b",
    r"\btriage\b",
    r"\bsession replay\b",
    r"\bbrain\b",
    r"\btask priorit\b",
    r"\bnightly digest\b",
    r"\bstale todo\b",
    r"\bhealth.*ci\b",
    r"\bauto.?merge\b",
    r"\bmulti.session diff\b",
    r"\bdependency\b",
]


def _score_roadmap_alignment(title: str, description: str, roadmap_text: str) -> float:
    """Score how well a task aligns with the current roadmap backlog (0-25)."""
    backlog_start = roadmap_text.find("## Backlog")
    if backlog_start == -1:
        backlog_text = roadmap_text
    else:
        completed_start = roadmap_text.find("## Completed", backlog_start)
        backlog_text = roadmap_text[backlog_start:completed_start if completed_start > 0 else None]

    text = f"{title} {description}".lower()
    score = 0.0

    for pattern in _ROADMAP_BACKLOG_PATTERNS:
        if re.search(pattern, text) and re.search(pattern, backlog_text.lower()):
            score += 8.0

    for line in backlog_text.splitlines():
        if not line.startswith("- ["):
            continue
        line_lower = line.lower()
        title_words = [w for w in title.lower().split() if len(w) > 4]
        matches = sum(1 for w in title_words if w in line_lower)
        if matches >= 2:
            score += 10.0
            break

    return min(score, 25.0)


def _score_issue_urgency(issues: list[dict]) -> float:
    """Convert triaged issues into an urgency score (0-35)."""
    if not issues:
        return 0.0

    score = 0.0
    for issue in issues:
        priority = issue.get("priority", 3)
        labels = issue.get("labels", [])
        if "human-priority" in labels:
            score += 15.0
        score += (6 - priority) * 3.0
        if issue.get("comment_count", 0) >= 3:
            score += 3.0

    return min(score, 35.0)


def _score_complexity_fit(description: str, estimated_prs: int) -> float:
    """Score whether the task fits a single session's capacity (0-10)."""
    if estimated_prs == 1:
        return 10.0
    elif estimated_prs == 2:
        return 8.0
    elif estimated_prs <= 3:
        return 5.0
    else:
        return 2.0


def _score_cross_module_synergy(related_modules: list[str]) -> float:
    """Score how many existing modules the task connects (0-10)."""
    if len(related_modules) >= 4:
        return 10.0
    elif len(related_modules) >= 3:
        return 8.0
    elif len(related_modules) >= 2:
        return 6.0
    elif len(related_modules) == 1:
        return 3.0
    return 0.0


def _score_health_improvement(related_modules: list[str], health_data: dict) -> float:
    """Score whether the task would improve low-health modules (0-20)."""
    if not health_data or not related_modules:
        return 5.0

    scores = [health_data.get(m, 85) for m in related_modules]
    avg = sum(scores) / len(scores) if scores else 85.0

    if avg < 70:
        return 20.0
    elif avg < 80:
        return 15.0
    elif avg < 85:
        return 10.0
    elif avg < 90:
        return 7.0
    return 5.0


# ---------------------------------------------------------------------------
# Brain class
# ---------------------------------------------------------------------------

class Brain:
    """Task prioritization engine for Awake sessions.

    Reads the repository state (roadmap, issues, health history) and
    returns a scored, ranked list of TaskCandidates for the session.
    """

    def __init__(self, repo_path: Path = Path(".")):
        """Initialize with the path to the repo root."""
        self.repo_path = Path(repo_path)

    def _load_roadmap(self) -> str:
        """Load ROADMAP.md text, returning empty string if missing."""
        p = self.repo_path / "ROADMAP.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def _load_health_history(self) -> dict:
        """Load health scores from docs/health_history.json."""
        p = self.repo_path / "docs" / "health_history.json"
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            snapshots = data.get("snapshots", [])
            if not snapshots:
                return {}
            latest = snapshots[-1]
            return {
                entry["file"]: entry["score"]
                for entry in latest.get("files", [])
                if "file" in entry and "score" in entry
            }
        except (json.JSONDecodeError, KeyError):
            return {}

    def _load_triage_data(self) -> list[dict]:
        """Load triage JSON from docs/triage.json if available."""
        p = self.repo_path / "docs" / "triage.json"
        if not p.exists():
            return []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("issues", [])
        except (json.JSONDecodeError, KeyError):
            return []

    def _extract_backlog_items(self, roadmap_text: str) -> list[dict]:
        """Extract uncompleted backlog items from ROADMAP.md."""
        items = []
        in_backlog = False
        for line in roadmap_text.splitlines():
            if line.startswith("## Backlog"):
                in_backlog = True
                continue
            if line.startswith("## ") and in_backlog:
                in_backlog = False
                break
            if in_backlog and line.startswith("- [ ]"):
                match = re.match(r"- \[ \] \*\*(.+?)\*\*\s*[\u2014-]\s*(.+)", line)
                if match:
                    items.append({
                        "title": match.group(1).strip(),
                        "description": match.group(2).strip(),
                    })
                else:
                    items.append({
                        "title": line[5:].strip(),
                        "description": "",
                    })
        return items

    def _build_candidate_from_backlog(
        self,
        item: dict,
        roadmap_text: str,
        health_data: dict,
    ) -> TaskCandidate:
        """Build a scored TaskCandidate from a roadmap backlog item."""
        title = item["title"]
        description = item["description"]

        module_hints = {
            "dashboard": ["src/cli.py", "docs/index.html"],
            "triage": ["src/issue_triage.py", "src/brain.py"],
            "replay": ["src/session_replay.py", "src/session_logger.py"],
            "brain": ["src/brain.py", "src/issue_triage.py"],
            "contributing": ["CONTRIBUTING.md"],
            "ci": [".github/workflows/ci.yml", "src/coverage_tracker.py"],
            "health": ["src/health.py", "src/health_trend.py"],
            "dependency": ["pyproject.toml"],
            "todo": ["src/refactor.py"],
            "diff": ["src/diff_visualizer.py"],
        }
        related_modules: list[str] = []
        text_lower = f"{title} {description}".lower()
        for hint, modules in module_hints.items():
            if hint in text_lower:
                related_modules.extend(modules)
        related_modules = list(dict.fromkeys(related_modules))

        breakdown = ScoreBreakdown(
            issue_urgency=0.0,
            roadmap_alignment=_score_roadmap_alignment(title, description, roadmap_text),
            health_improvement=_score_health_improvement(related_modules, health_data),
            complexity_fit=_score_complexity_fit(description, 1),
            cross_module_synergy=_score_cross_module_synergy(related_modules),
        )

        candidate = TaskCandidate(
            title=title,
            description=description,
            source="roadmap",
            score=breakdown.total,
            breakdown=breakdown,
            estimated_prs=1,
            related_modules=related_modules,
        )
        candidate.rationale = (
            f"roadmap backlog item; "
            f"alignment={breakdown.roadmap_alignment:.0f}, "
            f"synergy={breakdown.cross_module_synergy:.0f}"
        )
        return candidate

    def _build_candidate_from_issue(
        self,
        issue: dict,
        roadmap_text: str,
        health_data: dict,
    ) -> TaskCandidate:
        """Build a scored TaskCandidate from a triaged issue."""
        title = issue.get("title", "Untitled issue")
        description = issue.get("body", "")[:200]
        labels = issue.get("labels", [])
        issue_number = issue.get("number", 0)

        urgency_score = _score_issue_urgency([issue])

        breakdown = ScoreBreakdown(
            issue_urgency=urgency_score,
            roadmap_alignment=_score_roadmap_alignment(title, description, roadmap_text),
            health_improvement=5.0,
            complexity_fit=8.0,
            cross_module_synergy=3.0,
        )

        candidate = TaskCandidate(
            title=f"[Issue #{issue_number}] {title}",
            description=description,
            source="issue",
            score=breakdown.total,
            breakdown=breakdown,
            estimated_prs=1,
            related_modules=[],
            related_issue_numbers=[issue_number],
        )
        labels_str = ", ".join(labels[:3]) if labels else "none"
        candidate.rationale = (
            f"open issue; urgency={urgency_score:.0f}; labels: {labels_str}"
        )
        return candidate

    def plan(
        self,
        session_number: int,
        max_tasks: int = 5,
        extra_candidates: Optional[list[TaskCandidate]] = None,
    ) -> SessionPlan:
        """Generate the session plan.

        Args:
            session_number: The upcoming session number.
            max_tasks: Maximum tasks to include in the plan.
            extra_candidates: Additional candidates to score.

        Returns:
            A SessionPlan with scored and ranked tasks.
        """
        roadmap_text = self._load_roadmap()
        health_data = self._load_health_history()
        triage_data = self._load_triage_data()

        candidates: list[TaskCandidate] = []

        for item in self._extract_backlog_items(roadmap_text):
            candidates.append(
                self._build_candidate_from_backlog(item, roadmap_text, health_data)
            )

        for issue in triage_data:
            if issue.get("priority", 5) <= 3:
                candidates.append(
                    self._build_candidate_from_issue(issue, roadmap_text, health_data)
                )

        if extra_candidates:
            candidates.extend(extra_candidates)

        candidates.sort(key=lambda c: -c.score)

        top = candidates[:max_tasks]

        return SessionPlan(
            session_number=session_number,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            all_candidates=candidates,
            top_tasks=top,
        )


def save_plan(plan: SessionPlan, output_path: Path) -> None:
    """Write the session plan as Markdown."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(plan.to_markdown(), encoding="utf-8")


def save_plan_json(plan: SessionPlan, output_path: Path) -> None:
    """Write the session plan as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")
