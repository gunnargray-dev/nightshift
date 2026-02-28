"""
evolve.py — Gap analysis and evolution proposal engine.

Analyzes the current system against a reference model of what a fully
matured autonomous-development platform should be. Produces tiered proposals
for the next evolution of the system.

CLI: nightshift evolve [--json] [--write] [--tier {1,2,3}]
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
    name: str
    current_state: str
    target_state: str
    gap_severity: str   # CRITICAL / SIGNIFICANT / MINOR
    sessions_to_close: int


@dataclass
class EvolutionReport:
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
        current_state="Analyzes a single repo only",
        target_state="Can analyze an entire GitHub org, compare repos, identify cross-repo patterns",
        gap_severity="SIGNIFICANT",
        sessions_to_close=3,
    ),
    GapArea(
        name="Persistent vector memory",
        current_state="Memory = NIGHTSHIFT_LOG.md (flat text)",
        target_state="Semantic search over all past sessions, decisions, patterns, and learnings",
        gap_severity="SIGNIFICANT",
        sessions_to_close=2,
    ),
    GapArea(
        name="Parallel session execution",
        current_state="All analysis is sequential",
        target_state="Analysis modules run in parallel; critical path is ~3x faster",
        gap_severity="SIGNIFICANT",
        sessions_to_close=1,
    ),
    GapArea(
        name="Self-modifying test generation",
        current_state="Tests are written manually per session",
        target_state="Coverage map + AST analysis generates test stubs automatically",
        gap_severity="SIGNIFICANT",
        sessions_to_close=2,
    ),
    GapArea(
        name="Natural language goal interface",
        current_state="Goals are implicit (brain.py decides)",
        target_state="nightshift run --goal 'improve security coverage' guides the session",
        gap_severity="MINOR",
        sessions_to_close=2,
    ),
    GapArea(
        name="CI/CD integration",
        current_state="No native CI/CD hooks",
        target_state="nightshift ci produces GitHub Actions workflow; health gate on PRs",
        gap_severity="SIGNIFICANT",
        sessions_to_close=1,
    ),
    GapArea(
        name="Real-time health webhooks",
        current_state="Health is computed on demand",
        target_state="Push health events to Slack/webhook on quality degradation",
        gap_severity="MINOR",
        sessions_to_close=1,
    ),
    GapArea(
        name="Module auto-retirement",
        current_state="Dead/redundant modules accumulate",
        target_state="System identifies modules that should be merged, split, or removed",
        gap_severity="MINOR",
        sessions_to_close=1,
    ),
    GapArea(
        name="Distributed analysis workers",
        current_state="Single-process analysis",
        target_state="Analysis farm: submit jobs, collect results, aggregate",
        gap_severity="MINOR",
        sessions_to_close=4,
    ),
    GapArea(
        name="Cross-language support",
        current_state="Python only",
        target_state="Analyze JavaScript/TypeScript, Go, Rust via AST adapters",
        gap_severity="MINOR",
        sessions_to_close=5,
    ),
]

# ---------------------------------------------------------------------------
# Evolution proposals
# ---------------------------------------------------------------------------

PROPOSALS = [
    # TIER 1
    EvolutionProposal(
        title="Parallel analysis execution",
        description=(
            "Run all independent analysis modules (health, security, dead-code, coverage, "
            "complexity, todo) concurrently using concurrent.futures.ThreadPoolExecutor. "
            "The full analysis pipeline currently takes 8-15 seconds; parallel execution "
            "reduces this to ~3 seconds."
        ),
        tier=1, impact="HIGH", effort="LOW", category="Performance",
        rationale="As module count has grown from 2 (S1) to 52 (S18), sequential analysis has become the bottleneck.",
        example_command="nightshift health --parallel",
        session_estimate=1,
    ),
    EvolutionProposal(
        title="CI/CD health gate",
        description=(
            "Generate a GitHub Actions workflow that runs `nightshift audit` on every PR "
            "and fails the check if the composite grade drops below a configured threshold."
        ),
        tier=1, impact="HIGH", effort="LOW", category="DevOps",
        rationale="The system has sophisticated quality scoring but no way to enforce it in CI.",
        example_command="nightshift ci --generate",
        session_estimate=1,
    ),
    EvolutionProposal(
        title="Auto-generated test stubs",
        description=(
            "Given a source file with no test file, generate a test stub with one test "
            "per public function (parametrized where applicable) and fixture scaffolding."
        ),
        tier=1, impact="HIGH", effort="MEDIUM", category="Testing",
        rationale="There are 4-6 modules currently without full test coverage. Auto-stubs remove the blank-page problem.",
        example_command="nightshift test-gen src/new_module.py",
        session_estimate=1,
    ),
    EvolutionProposal(
        title="Real-time health webhooks",
        description=(
            "POST to a configured webhook URL whenever health detects a quality regression. "
            "Payload: module name, previous score, current score, delta, remediation. "
            "Supports Slack incoming webhooks natively."
        ),
        tier=1, impact="MEDIUM", effort="LOW", category="Observability",
        rationale="The system requires polling to detect regressions. Push-based notifications close the feedback loop.",
        example_command="nightshift health --watch --webhook https://hooks.slack.com/...",
        session_estimate=1,
    ),
    # TIER 2
    EvolutionProposal(
        title="Self-modifying test generation",
        description=(
            "Combine coverage_map.py output with AST analysis to identify uncovered code paths "
            "and generate targeted tests. Reads own coverage report, identifies uncovered branches, "
            "generates assertions to cover them."
        ),
        tier=2, impact="HIGH", effort="HIGH", category="Intelligence",
        rationale="Self-modifying generation would make test coverage self-healing.",
        example_command="nightshift test-heal",
        session_estimate=2,
    ),
    EvolutionProposal(
        title="Multi-repo analysis",
        description=(
            "Extend all analysis modules to accept a list of repos. Compare health, coverage, "
            "complexity, and DNA fingerprints across repos. Identify shared patterns, "
            "cross-repo dependencies, and org-wide quality trends."
        ),
        tier=2, impact="HIGH", effort="HIGH", category="Scale",
        rationale="The stdlib-only architecture makes this tractable. Abstractions already work on any Python repo.",
        example_command="nightshift health --repos repo1,repo2,repo3 --compare",
        session_estimate=3,
    ),
    EvolutionProposal(
        title="Persistent semantic memory",
        description=(
            "Replace NIGHTSHIFT_LOG.md as sole memory store with a SQLite-backed semantic index. "
            "Every decision, pattern, and insight gets indexed for semantic search. "
            "`nightshift recall 'test coverage'` retrieves relevant past sessions."
        ),
        tier=2, impact="HIGH", effort="HIGH", category="Intelligence",
        rationale="The flat log works for 18 sessions. At 50+, semantic recall becomes necessary.",
        example_command="nightshift recall 'security improvements'",
        session_estimate=2,
    ),
    EvolutionProposal(
        title="Natural language session goals",
        description=(
            "Accept a `--goal` flag that biases the brain's scoring toward a specific objective. "
            "`nightshift run --goal 'improve security coverage'` re-weights brain signals."
        ),
        tier=2, impact="MEDIUM", effort="MEDIUM", category="UX",
        rationale="The current brain is purely data-driven. Human guidance can complement algorithmic scoring.",
        example_command="nightshift brain --goal 'reduce complexity in core modules'",
        session_estimate=2,
    ),
    # TIER 3
    EvolutionProposal(
        title="Distributed analysis workers",
        description=(
            "Submit analysis jobs to a pool of workers. Enables analysis of very large repos "
            "(100k+ LOC) where even parallel local execution is too slow."
        ),
        tier=3, impact="MEDIUM", effort="HIGH", category="Scale",
        rationale="Future-proofing for enterprise-scale repos.",
        example_command="nightshift health --workers 8 --distributed",
        session_estimate=4,
    ),
    EvolutionProposal(
        title="Cross-language AST adapters",
        description=(
            "Abstract the AST analysis layer behind a language-agnostic interface. "
            "Implement adapters for JavaScript/TypeScript (via tree-sitter), Go, and Rust."
        ),
        tier=3, impact="HIGH", effort="HIGH", category="Platform",
        rationale="Expanding to other languages would make it applicable to the majority of open-source repos.",
        example_command="nightshift health --lang typescript",
        session_estimate=5,
    ),
    EvolutionProposal(
        title="Autonomous PR review agent",
        description=(
            "Given a PR diff, run the full analysis suite on changed files, "
            "compare before/after scores, and post a structured review comment with "
            "health impact, coverage delta, complexity changes, and security findings."
        ),
        tier=3, impact="HIGH", effort="HIGH", category="Automation",
        rationale="The system already scores its own PRs (pr_scorer.py). Extending to arbitrary PRs turns it into a review assistant.",
        example_command="nightshift review-pr --pr 42",
        session_estimate=3,
    ),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_evolution(current_session=18):
    """Generate a full evolution report with gap analysis and proposals."""
    tier1 = [p for p in PROPOSALS if p.tier == 1]
    tier2 = [p for p in PROPOSALS if p.tier == 2]
    tier3 = [p for p in PROPOSALS if p.tier == 3]
    critical_gaps = [g for g in GAP_AREAS if g.gap_severity == "CRITICAL"]

    summary = (
        f"After {current_session} sessions, {len(GAP_AREAS)} gap areas identified. "
        f"{len(tier1)} Tier-1 proposals (high impact, executable next session), "
        f"{len(tier2)} Tier-2 proposals (2-3 sessions each), "
        f"{len(tier3)} Tier-3 exploratory proposals."
    )

    return EvolutionReport(
        current_session=current_session,
        gap_areas=GAP_AREAS,
        proposals=PROPOSALS,
        tier1=tier1,
        tier2=tier2,
        tier3=tier3,
        critical_gaps=critical_gaps,
        summary=summary,
    )


def format_evolution(report):
    """Render an EvolutionReport as a human-readable terminal string."""
    lines = []
    lines.append("EVOLUTION PROPOSALS")
    lines.append("=" * 60)
    lines.append(f"  Session context: {report.current_session}")
    lines.append(f"  {report.summary}")
    lines.append("")

    for tier_num, tier_name, proposals in [
        (1, "TIER 1 -- High Impact / Low Effort  (next session)", report.tier1),
        (2, "TIER 2 -- High Impact / Higher Effort  (2-3 sessions)", report.tier2),
        (3, "TIER 3 -- Exploratory / Long Horizon", report.tier3),
    ]:
        lines.append(tier_name)
        lines.append("-" * 60)
        for p in proposals:
            lines.append(f"  [{p.category}] {p.title}")
            words = p.description.split()
            current = "    "
            for w in words:
                if len(current) + len(w) + 1 > 72:
                    lines.append(current.rstrip())
                    current = "    " + w + " "
                else:
                    current += w + " "
            lines.append(current.rstrip())
            lines.append(f"    Command: {p.example_command}")
            lines.append(f"    Effort:  {p.effort}  |  Impact: {p.impact}  |  ~{p.session_estimate} session(s)")
            lines.append("")

    lines.append("GAP ANALYSIS")
    lines.append("-" * 60)
    for g in sorted(report.gap_areas, key=lambda x: ["CRITICAL", "SIGNIFICANT", "MINOR"].index(x.gap_severity)):
        lines.append(f"  [{g.gap_severity:11s}] {g.name}")
        lines.append(f"    Now:    {g.current_state}")
        lines.append(f"    Target: {g.target_state}")
        lines.append(f"    Close in ~{g.sessions_to_close} session(s)")
        lines.append("")

    return "\n".join(lines)


def evolve_to_json(report):
    """Serialize EvolutionReport to JSON."""
    def _to_dict(obj):
        if hasattr(obj, '__dict__'):
            return vars(obj)
        return obj

    data = {
        "current_session": report.current_session,
        "summary": report.summary,
        "gap_areas": [_to_dict(g) for g in report.gap_areas],
        "tier1": [_to_dict(p) for p in report.tier1],
        "tier2": [_to_dict(p) for p in report.tier2],
        "tier3": [_to_dict(p) for p in report.tier3],
    }
    return json.dumps(data, indent=2)


def save_evolution(report, path):
    """Save evolution report to docs/evolve.md."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "# Nightshift Evolution Proposals\n\nGenerated automatically by `nightshift evolve`.\n\n"
    content += "```\n" + format_evolution(report) + "\n```\n"
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    report = generate_evolution()
    print(format_evolution(report))
