"""evolve.py — Gap analysis and evolution proposal engine.

Analyzes the current system against a reference model of what a fully
matured autonomous-development platform should be. Produces tiered proposals
for the next evolution of the system.

CLI: awake evolve [--json] [--write] [--tier {1,2,3}]
API: GET /api/evolve
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvolutionProposal:
    """A single tiered evolution proposal with impact and effort ratings"""

    title: str
    description: str
    tier: int               # 1=high impact/low effort, 2=high/high, 3=exploratory
    impact: str             # HIGH / MEDIUM / LOW
    effort: str             # LOW / MEDIUM / HIGH
    category: str
    rationale: str
    example_command: str
    session_estimate: int


@dataclass
class GapArea:
    """A gap between current state and target state with severity rating"""

    name: str
    current_state: str
    target_state: str
    gap_severity: str   # CRITICAL / SIGNIFICANT / MINOR
    sessions_to_close: int


@dataclass
class EvolutionReport:
    """Aggregate evolution report containing gap areas and tiered proposals"""

    current_session: int
    gap_areas: list
    proposals: list
    tier1: list
    tier2: list
    tier3: list
    critical_gaps: list
    summary: str


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------

GAP_AREAS = [
    GapArea(
        name="Multi-repo intelligence",
        current_state="Analyzes a single repository in isolation",
        target_state="Cross-repo pattern recognition and knowledge transfer",
        gap_severity="SIGNIFICANT",
        sessions_to_close=6,
    ),
    GapArea(
        name="Predictive failure prevention",
        current_state="Reactive health monitoring and alerts",
        target_state="Proactive prediction of likely failure points before they occur",
        gap_severity="CRITICAL",
        sessions_to_close=4,
    ),
    GapArea(
        name="Natural language task ingestion",
        current_state="Structured CLI commands and API endpoints",
        target_state="Free-form natural language task specification with auto-decomposition",
        gap_severity="SIGNIFICANT",
        sessions_to_close=5,
    ),
    GapArea(
        name="Autonomous PR lifecycle",
        current_state="Creates branches and drafts; requires human merge",
        target_state="Full PR lifecycle: create, review, iterate, merge autonomously",
        gap_severity="CRITICAL",
        sessions_to_close=8,
    ),
    GapArea(
        name="Cost and token awareness",
        current_state="No visibility into AI API costs or token consumption",
        target_state="Per-session cost tracking, budget enforcement, and optimization",
        gap_severity="SIGNIFICANT",
        sessions_to_close=3,
    ),
    GapArea(
        name="Test generation",
        current_state="Relies on human-authored tests; no auto-generation",
        target_state="Automatic test generation for new code paths with coverage targets",
        gap_severity="SIGNIFICANT",
        sessions_to_close=5,
    ),
    GapArea(
        name="Self-healing capability",
        current_state="Identifies issues but cannot auto-remediate",
        target_state="Automatically fixes common issues: lint errors, type errors, failing tests",
        gap_severity="CRITICAL",
        sessions_to_close=6,
    ),
    GapArea(
        name="Knowledge persistence",
        current_state="Session logs exist but no structured knowledge extraction",
        target_state="Structured knowledge graph of decisions, patterns, and project context",
        gap_severity="SIGNIFICANT",
        sessions_to_close=4,
    ),
]


# ---------------------------------------------------------------------------
# Evolution proposals
# ---------------------------------------------------------------------------

PROPOSALS = [
    # ── Tier 1: High impact, low effort ──────────────────────────────────────
    EvolutionProposal(
        title="Token & cost tracking per session",
        description="Track token consumption and estimated API cost per awake session. Store in session log and expose via `awake stats`.",
        tier=1,
        impact="HIGH",
        effort="LOW",
        category="observability",
        rationale="Cost visibility is a precondition for budget enforcement and ROI measurement. Low implementation effort via litellm callbacks.",
        example_command="awake stats --cost --last 10",
        session_estimate=2,
    ),
    EvolutionProposal(
        title="Auto-fix lint and type errors post-session",
        description="After each coding session, automatically run ruff --fix and pyright; commit any auto-fixable issues with a standardized message.",
        tier=1,
        impact="HIGH",
        effort="LOW",
        category="self-healing",
        rationale="Prevents technical debt accumulation. Most lint/type errors are auto-fixable. Keeps codebase consistently clean without human intervention.",
        example_command="awake fix [--dry-run]",
        session_estimate=2,
    ),
    EvolutionProposal(
        title="Session knowledge extraction to structured log",
        description="Parse session logs to extract: decisions made, files changed, patterns used, TODOs left. Store in machine-readable knowledge base.",
        tier=1,
        impact="HIGH",
        effort="MEDIUM",
        category="knowledge",
        rationale="Structured knowledge enables cross-session learning and onboarding. Currently session value is locked in unstructured text.",
        example_command="awake knowledge extract --session 15",
        session_estimate=3,
    ),
    EvolutionProposal(
        title="GitHub Actions CI integration",
        description="Auto-generate or update .github/workflows/awake.yml to run health checks, tests, and security scans on every PR.",
        tier=1,
        impact="HIGH",
        effort="LOW",
        category="ci-cd",
        rationale="Shifts quality checks left. Prevents regressions from reaching main. One-time setup with high ongoing value.",
        example_command="awake ci setup [--provider github]",
        session_estimate=2,
    ),
    # ── Tier 2: High impact, high effort ─────────────────────────────────────
    EvolutionProposal(
        title="Autonomous PR lifecycle management",
        description="Full PR automation: create branch, implement feature, open PR, respond to review comments, iterate, and merge when approved.",
        tier=2,
        impact="HIGH",
        effort="HIGH",
        category="autonomy",
        rationale="Current ceiling: awake creates branches but humans must merge. Full autonomy requires review-response loop and conflict resolution.",
        example_command="awake pr create --feature 'add user auth' --auto-merge",
        session_estimate=8,
    ),
    EvolutionProposal(
        title="Natural language task decomposition",
        description="Accept free-form task descriptions and decompose into structured awake commands with dependency ordering and session estimates.",
        tier=2,
        impact="HIGH",
        effort="HIGH",
        category="interface",
        rationale="Removes the friction of learning CLI syntax. Enables non-technical stakeholders to direct development work.",
        example_command="awake do 'add rate limiting to the API with Redis'",
        session_estimate=5,
    ),
    EvolutionProposal(
        title="Predictive health degradation alerts",
        description="Train a simple model on health trend data to predict when metrics are likely to breach thresholds before they do.",
        tier=2,
        impact="HIGH",
        effort="HIGH",
        category="predictive",
        rationale="Reactive monitoring catches problems after they occur. Predictive alerting enables prevention rather than remediation.",
        example_command="awake predict --horizon 5 --alert",
        session_estimate=4,
    ),
    EvolutionProposal(
        title="Automatic test generation for new code",
        description="After each session, identify new or modified functions without test coverage and generate pytest test stubs with AI-assisted assertions.",
        tier=2,
        impact="HIGH",
        effort="HIGH",
        category="testing",
        rationale="Test coverage is a key maturity metric. Manual test authoring is the primary bottleneck to reaching >80% coverage.",
        example_command="awake test generate --changed-only",
        session_estimate=5,
    ),
    # ── Tier 3: Exploratory / research ───────────────────────────────────────
    EvolutionProposal(
        title="Multi-repo knowledge federation",
        description="Extend awake to analyze multiple repos simultaneously, identifying shared patterns, cross-repo dependencies, and knowledge transfer opportunities.",
        tier=3,
        impact="MEDIUM",
        effort="HIGH",
        category="scale",
        rationale="Single-repo focus limits applicability in organizations with many services. Federation enables portfolio-level intelligence.",
        example_command="awake federate --repos org/api,org/frontend,org/infra",
        session_estimate=10,
    ),
    EvolutionProposal(
        title="Voice-driven development interface",
        description="Accept voice commands via Whisper transcription, enabling hands-free coding direction during deep work sessions.",
        tier=3,
        impact="MEDIUM",
        effort="MEDIUM",
        category="interface",
        rationale="Reduces context switching. Enables development direction while reviewing code or documentation.",
        example_command="awake listen --continuous",
        session_estimate=4,
    ),
    EvolutionProposal(
        title="Formal verification of critical paths",
        description="Integrate with Z3 or similar SMT solvers to formally verify correctness properties of scoring and decision logic.",
        tier=3,
        impact="MEDIUM",
        effort="HIGH",
        category="quality",
        rationale="High-confidence correctness for core algorithms. Research-grade but applicable to scoring and constraint satisfaction logic.",
        example_command="awake verify --module scoring",
        session_estimate=8,
    ),
]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _get_current_session() -> int:
    """Read current session number from session log."""
    log_path = Path(".awake/session_log.json")
    if log_path.exists():
        try:
            data = json.loads(log_path.read_text())
            sessions = data.get("sessions", [])
            return len(sessions)
        except Exception:
            pass
    return 0


def generate_evolution_report(
    tier_filter: Optional[int] = None,
) -> EvolutionReport:
    """Generate a full evolution report with gap analysis and tiered proposals."""

    current_session = _get_current_session()

    proposals = PROPOSALS
    if tier_filter is not None:
        proposals = [p for p in proposals if p.tier == tier_filter]

    tier1 = [p for p in PROPOSALS if p.tier == 1]
    tier2 = [p for p in PROPOSALS if p.tier == 2]
    tier3 = [p for p in PROPOSALS if p.tier == 3]
    critical_gaps = [g for g in GAP_AREAS if g.gap_severity == "CRITICAL"]

    summary_parts = [
        f"Session {current_session} evolution analysis.",
        f"{len(GAP_AREAS)} gap areas identified ({len(critical_gaps)} critical).",
        f"{len(PROPOSALS)} proposals across 3 tiers.",
        f"Tier 1 (quick wins): {len(tier1)} proposals (~{sum(p.session_estimate for p in tier1)} sessions).",
        f"Tier 2 (major features): {len(tier2)} proposals (~{sum(p.session_estimate for p in tier2)} sessions).",
        f"Tier 3 (exploratory): {len(tier3)} proposals (~{sum(p.session_estimate for p in tier3)} sessions).",
        "Recommended starting point: token tracking + auto-fix (Tier 1, ~4 sessions total).",
    ]

    return EvolutionReport(
        current_session=current_session,
        gap_areas=GAP_AREAS,
        proposals=proposals,
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        critical_gaps=critical_gaps,
        summary=" ".join(summary_parts),
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def _severity_icon(severity: str) -> str:
    return {"CRITICAL": "🔴", "SIGNIFICANT": "🟡", "MINOR": "🟢"}.get(severity, "⚪")


def _tier_label(tier: int) -> str:
    return {
        1: "Tier 1 — Quick Win",
        2: "Tier 2 — Major Feature",
        3: "Tier 3 — Exploratory",
    }.get(tier, f"Tier {tier}")


def _impact_badge(impact: str) -> str:
    return {"HIGH": "⬆ HIGH", "MEDIUM": "➡ MED", "LOW": "⬇ LOW"}.get(impact, impact)


def _effort_badge(effort: str) -> str:
    return {"LOW": "✦ LOW", "MEDIUM": "✦✦ MED", "HIGH": "✦✦✦ HIGH"}.get(effort, effort)


def format_evolution_report(report: EvolutionReport) -> str:
    """Format an EvolutionReport as a human-readable string."""

    lines = [
        "═" * 70,
        "  AWAKE — EVOLUTION REPORT",
        "═" * 70,
        f"  Session:   {report.current_session}",
        f"  Summary:   {report.summary}",
        "",
    ]

    # Gap areas
    lines += [
        "─" * 70,
        "  GAP ANALYSIS",
        "─" * 70,
    ]
    for gap in report.gap_areas:
        icon = _severity_icon(gap.gap_severity)
        lines += [
            f"  {icon} {gap.name}  [{gap.gap_severity}]  ~{gap.sessions_to_close} sessions",
            f"     Current : {gap.current_state}",
            f"     Target  : {gap.target_state}",
            "",
        ]

    # Proposals grouped by tier
    lines += [
        "─" * 70,
        "  EVOLUTION PROPOSALS",
        "─" * 70,
    ]
    for tier_group in [report.tier1, report.tier2, report.tier3]:
        if not tier_group:
            continue
        tier_label = _tier_label(tier_group[0].tier)
        lines += [f"\n  ── {tier_label} ──"]
        for p in tier_group:
            lines += [
                f"\n  [{p.category.upper()}] {p.title}",
                f"  Impact: {_impact_badge(p.impact)}  Effort: {_effort_badge(p.effort)}  Est: {p.session_estimate} sessions",
                f"  {p.description}",
                f"  Rationale: {p.rationale}",
                f"  Example: {p.example_command}",
            ]

    lines += ["\n" + "═" * 70]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(args=None) -> int:
    """CLI entry point for `awake evolve`."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="awake evolve",
        description="Analyze evolution gaps and propose next steps",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--write", action="store_true", help="Write report to .awake/evolution.json")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], help="Filter to specific tier")

    parsed = parser.parse_args(args)

    report = generate_evolution_report(tier_filter=parsed.tier)

    if parsed.json or parsed.write:
        data = asdict(report)
        if parsed.write:
            out_path = Path(".awake/evolution.json")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(data, indent=2))
            print(f"Written to {out_path}")
        else:
            print(json.dumps(data, indent=2))
    else:
        print(format_evolution_report(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
