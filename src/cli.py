"""Unified CLI entry point for Nightshift.

Provides a single ``nightshift`` command that ties together all analysis
modules into a coherent developer experience.  Every subcommand corresponds
to one (or more) modules in ``src/``.

This file is a thin dispatcher — all command implementations live in
``src/commands/``:

  src/commands/analysis.py  — health, complexity, coupling, deadcode, security,
                               coveragemap, blame, maturity
  src/commands/meta.py      — stats, changelog, story, reflect, evolve, status,
                               session_score, timeline, replay, compare, diff,
                               diff_sessions
  src/commands/tools.py     — doctor, todos, benchmark, gitstats, badges, audit,
                               predict, teach, dna, report, export, coverage,
                               score, test_quality, refactor, commits, semver,
                               modules, trends, plan (brain), triage, depgraph, arch
  src/commands/infra.py     — dashboard, init, deps, config, plugins, openapi, run

Subcommands
-----------
nightshift health      — Run code health analysis across src/
nightshift stats       — Show repo stats (commits, PRs, lines changed)
nightshift diff        — Visualise the last session's git changes
nightshift changelog   — Render CHANGELOG.md from git history
nightshift coverage    — Show test coverage trend
nightshift score       — Score the most recent PR
nightshift arch        — Generate / refresh docs/ARCHITECTURE.md
nightshift refactor    — Identify refactor candidates in src/
nightshift run         — Run the full end-of-session pipeline
nightshift depgraph    — Visualise module dependency graph
nightshift todos       — Hunt stale TODO/FIXME annotations
nightshift doctor      — Run full repo health diagnostic
nightshift timeline    — ASCII visual timeline of all sessions
nightshift coupling    — Module coupling analyzer (Ca, Ce, instability)
nightshift complexity  — Cyclomatic complexity tracker
nightshift export      — Export any analysis to JSON/Markdown/HTML
nightshift config      — Show or write nightshift.toml config
nightshift compare     — Diff two sessions side-by-side
nightshift dashboard   — Launch live React dashboard (web server)
nightshift deps        — Check Python dependency freshness via PyPI
nightshift modules     — Module interconnection visualizer (Mermaid/ASCII)
nightshift trends      — Historical trend data for the React dashboard
nightshift commits     — Smart commit message quality analyzer
nightshift diff-sessions — Compare any two sessions with rich delta analysis
nightshift test-quality — Grade tests by assertion density and edge coverage
nightshift report      — Generate executive HTML report combining all analyses
nightshift openapi     — Generate OpenAPI 3.1 spec from all API endpoints
nightshift plugins     — Manage plugin/hook registry from nightshift.toml
nightshift changelog --release — Generate polished GitHub Releases notes
nightshift blame       — Human vs AI contribution attribution (git blame)
nightshift deadcode    — Dead code detector: unused functions/imports
nightshift security    — Security audit: common Python anti-patterns
nightshift coveragemap — Test coverage heat map ranked by weakness

Usage
-----
    python -m nightshift.cli <command> [options]
    # or after ``pip install -e .``
    nightshift <command> [options]
"""

from __future__ import annotations

import argparse
import sys

# ---------------------------------------------------------------------------
# Command imports — pulled from domain-specific submodules
# ---------------------------------------------------------------------------

from src.commands import (
    _repo,
    _print_header,
    _print_ok,
    _print_warn,
    _print_info,
    REPO_ROOT,
)

from src.commands.analysis import (
    cmd_health,
    cmd_complexity,
    cmd_coupling,
    cmd_deadcode,
    cmd_security,
    cmd_coveragemap,
    cmd_blame,
    cmd_maturity,
)

from src.commands.meta import (
    cmd_stats,
    cmd_changelog,
    cmd_story,
    cmd_reflect,
    cmd_evolve,
    cmd_status,
    cmd_session_score,
    cmd_timeline,
    cmd_replay,
    cmd_compare,
    cmd_diff,
    cmd_diff_sessions,
)

from src.commands.tools import (
    cmd_doctor,
    cmd_todos,
    cmd_benchmark,
    cmd_gitstats,
    cmd_badges,
    cmd_audit,
    cmd_predict,
    cmd_teach,
    cmd_dna,
    cmd_report,
    cmd_export,
    cmd_coverage,
    cmd_score,
    cmd_test_quality,
    cmd_refactor,
    cmd_commits,
    cmd_semver,
    cmd_modules,
    cmd_trends,
    cmd_plan,
    cmd_triage,
    cmd_depgraph,
    cmd_arch,
)

from src.commands.infra import (
    cmd_dashboard,
    cmd_init,
    cmd_deps,
    cmd_config,
    cmd_plugins,
    cmd_openapi,
    cmd_run,
)

# Keep backwards-compatible re-exports so any code that imported these
# symbols from src.cli continues to work.
__all__ = [
    "cmd_health", "cmd_complexity", "cmd_coupling", "cmd_deadcode",
    "cmd_security", "cmd_coveragemap", "cmd_blame", "cmd_maturity",
    "cmd_stats", "cmd_changelog", "cmd_story", "cmd_reflect", "cmd_evolve",
    "cmd_status", "cmd_session_score", "cmd_timeline", "cmd_replay",
    "cmd_compare", "cmd_diff", "cmd_diff_sessions",
    "cmd_doctor", "cmd_todos", "cmd_benchmark", "cmd_gitstats", "cmd_badges",
    "cmd_audit", "cmd_predict", "cmd_teach", "cmd_dna", "cmd_report",
    "cmd_export", "cmd_coverage", "cmd_score", "cmd_test_quality",
    "cmd_refactor", "cmd_commits", "cmd_semver", "cmd_modules", "cmd_trends",
    "cmd_plan", "cmd_triage", "cmd_depgraph", "cmd_arch",
    "cmd_dashboard", "cmd_init", "cmd_deps", "cmd_config", "cmd_plugins",
    "cmd_openapi", "cmd_run",
    "build_parser", "main",
]


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="nightshift",
        description="Nightshift — autonomous repo intelligence",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Common flag helpers
    def _add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="Output raw JSON")

    def _add_repo(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", default=None, help="Path to repo root")

    def _add_write(p: argparse.ArgumentParser) -> None:
        p.add_argument("--write", action="store_true", help="Write output to file")

    # ------------------------------------------------------------------
    # Analysis commands
    # ------------------------------------------------------------------

    # health
    p_health = sub.add_parser("health", help="Code health analysis")
    _add_json(p_health)
    _add_repo(p_health)
    p_health.set_defaults(func=cmd_health)

    # complexity
    p_complexity = sub.add_parser("complexity", help="Cyclomatic complexity")
    _add_write(p_complexity)
    _add_json(p_complexity)
    _add_repo(p_complexity)
    p_complexity.set_defaults(func=cmd_complexity)

    # coupling
    p_coupling = sub.add_parser("coupling", help="Module coupling analysis")
    _add_write(p_coupling)
    _add_json(p_coupling)
    _add_repo(p_coupling)
    p_coupling.set_defaults(func=cmd_coupling)

    # deadcode
    p_dc = sub.add_parser("deadcode", help="Dead code detector")
    _add_json(p_dc)
    _add_repo(p_dc)
    p_dc.set_defaults(func=cmd_deadcode)

    # security
    p_sec = sub.add_parser("security", help="Security audit")
    _add_json(p_sec)
    _add_repo(p_sec)
    p_sec.set_defaults(func=cmd_security)

    # coveragemap
    p_cmap = sub.add_parser("coveragemap", help="Coverage heat map")
    _add_json(p_cmap)
    _add_repo(p_cmap)
    p_cmap.set_defaults(func=cmd_coveragemap)

    # blame
    p_blame = sub.add_parser("blame", help="Human vs AI attribution")
    _add_json(p_blame)
    _add_repo(p_blame)
    p_blame.set_defaults(func=cmd_blame)

    # maturity
    p_mat = sub.add_parser("maturity", help="Module maturity scores")
    _add_json(p_mat)
    _add_repo(p_mat)
    p_mat.set_defaults(func=cmd_maturity)

    # ------------------------------------------------------------------
    # Meta commands
    # ------------------------------------------------------------------

    # stats
    p_stats = sub.add_parser("stats", help="Repository statistics")
    _add_json(p_stats)
    _add_repo(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    # changelog
    p_cl = sub.add_parser("changelog", help="Render CHANGELOG.md")
    p_cl.add_argument("--write", action="store_true", help="Write CHANGELOG.md")
    p_cl.add_argument("--json", action="store_true", help="Output raw JSON")
    p_cl.add_argument("--release", action="store_true", help="Generate polished GitHub Releases notes")
    p_cl.add_argument("--version", default=None, help="Version tag for release notes (e.g. v0.17.0)")
    _add_repo(p_cl)
    p_cl.set_defaults(func=cmd_changelog)

    # story
    p_story = sub.add_parser("story", help="Repo narrative")
    _add_json(p_story)
    _add_repo(p_story)
    p_story.set_defaults(func=cmd_story)

    # reflect
    p_reflect = sub.add_parser("reflect", help="Session meta-analysis: quality scores, patterns, and insights")
    p_reflect.add_argument("--write", action="store_true", help="Save report to docs/reflect.md")
    _add_json(p_reflect)
    _add_repo(p_reflect)
    p_reflect.set_defaults(func=cmd_reflect)

    # evolve
    p_evolve = sub.add_parser("evolve", help="Gap analysis and tiered evolution proposals")
    p_evolve.add_argument("--write", action="store_true", help="Save report to docs/evolve.md")
    p_evolve.add_argument("--tier", type=int, choices=[1, 2, 3],
                          help="Show only proposals from a specific tier (1=quick, 2=medium, 3=exploratory)")
    _add_json(p_evolve)
    _add_repo(p_evolve)
    p_evolve.set_defaults(func=cmd_evolve)

    # status
    p_status = sub.add_parser("status", help="One-command comprehensive status: health, tests, modules, next action")
    p_status.add_argument("--brief", action="store_true", help="One-line summary")
    _add_json(p_status)
    _add_repo(p_status)
    p_status.set_defaults(func=cmd_status)

    # session-score
    p_session_score = sub.add_parser("session-score", help="Score a session on 5 quality dimensions")
    p_session_score.add_argument("--session", type=int, help="Session number to score (default: current)")
    p_session_score.add_argument("--all", action="store_true", help="Score all historical sessions")
    _add_json(p_session_score)
    _add_repo(p_session_score)
    p_session_score.set_defaults(func=cmd_session_score)

    # timeline
    p_timeline = sub.add_parser("timeline", help="Session timeline")
    _add_write(p_timeline)
    _add_json(p_timeline)
    _add_repo(p_timeline)
    p_timeline.set_defaults(func=cmd_timeline)

    # replay
    p_replay = sub.add_parser("replay", help="Replay a session")
    p_replay.add_argument("--session", type=int, default=None, help="Session number")
    p_replay.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_replay)
    p_replay.set_defaults(func=cmd_replay)

    # compare
    p_compare = sub.add_parser("compare", help="Compare two sessions")
    p_compare.add_argument("session_a", type=int, help="Session A")
    p_compare.add_argument("session_b", type=int, help="Session B")
    p_compare.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_compare)
    p_compare.set_defaults(func=cmd_compare)

    # diff
    p_diff = sub.add_parser("diff", help="Visualise session diff")
    p_diff.add_argument("--session", type=int, default=None, help="Session number")
    p_diff.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_diff)
    p_diff.set_defaults(func=cmd_diff)

    # diff-sessions
    p_diffsessions = sub.add_parser("diff-sessions", help="Compare two sessions")
    p_diffsessions.add_argument("session_a", help="Session A number")
    p_diffsessions.add_argument("session_b", help="Session B number")
    _add_json(p_diffsessions)
    _add_repo(p_diffsessions)
    p_diffsessions.set_defaults(func=cmd_diff_sessions)

    # ------------------------------------------------------------------
    # Tools commands
    # ------------------------------------------------------------------

    # doctor
    p_doctor = sub.add_parser("doctor", help="Full repo health diagnostic")
    _add_write(p_doctor)
    _add_json(p_doctor)
    _add_repo(p_doctor)
    p_doctor.set_defaults(func=cmd_doctor)

    # todos
    p_todos = sub.add_parser("todos", help="TODO/FIXME hunter")
    _add_write(p_todos)
    _add_json(p_todos)
    p_todos.add_argument("--session", type=int, default=1, help="Current session number")
    p_todos.add_argument("--threshold", type=int, default=3, help="Stale threshold (sessions)")
    _add_repo(p_todos)
    p_todos.set_defaults(func=cmd_todos)

    # benchmark
    p_bench = sub.add_parser("benchmark", help="Performance benchmark suite")
    _add_json(p_bench)
    _add_repo(p_bench)
    p_bench.set_defaults(func=cmd_benchmark)

    # gitstats
    p_gitstats = sub.add_parser("gitstats", help="Git statistics deep-dive")
    _add_json(p_gitstats)
    _add_repo(p_gitstats)
    p_gitstats.set_defaults(func=cmd_gitstats)

    # badges
    p_badges = sub.add_parser("badges", help="Badge generator")
    _add_write(p_badges)
    _add_json(p_badges)
    _add_repo(p_badges)
    p_badges.set_defaults(func=cmd_badges)

    # audit
    p_audit = sub.add_parser("audit", help="Comprehensive repo audit")
    _add_json(p_audit)
    _add_repo(p_audit)
    p_audit.set_defaults(func=cmd_audit)

    # predict
    p_predict = sub.add_parser("predict", help="Predictive session planner")
    _add_json(p_predict)
    _add_repo(p_predict)
    p_predict.set_defaults(func=cmd_predict)

    # teach
    p_teach = sub.add_parser("teach", help="Module tutorial generator")
    p_teach.add_argument("module", help="Module name (e.g. health, stats)")
    p_teach.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_teach)
    p_teach.set_defaults(func=cmd_teach)

    # dna
    p_dna = sub.add_parser("dna", help="Repo DNA fingerprint")
    _add_json(p_dna)
    _add_repo(p_dna)
    p_dna.set_defaults(func=cmd_dna)

    # report
    p_report = sub.add_parser("report", help="Executive HTML report")
    p_report.add_argument("--output", default=None, help="Output path (default: docs/report.html)")
    p_report.add_argument("--open", action="store_true", help="Open in browser after generating")
    _add_json(p_report)
    _add_repo(p_report)
    p_report.set_defaults(func=cmd_report, open=True)

    # export
    p_export = sub.add_parser("export", help="Export analysis to JSON/Markdown/HTML")
    p_export.add_argument("--format", choices=["json", "markdown", "html"], default="json")
    _add_repo(p_export)
    p_export.set_defaults(func=cmd_export)

    # coverage
    p_cov = sub.add_parser("coverage", help="Test coverage trend")
    _add_json(p_cov)
    _add_repo(p_cov)
    p_cov.set_defaults(func=cmd_coverage)

    # score / pr-score
    p_score = sub.add_parser("score", help="PR quality leaderboard")
    _add_json(p_score)
    _add_repo(p_score)
    p_score.set_defaults(func=cmd_score)

    p_prscore = sub.add_parser("pr-score", help="PR quality leaderboard")
    _add_json(p_prscore)
    _add_repo(p_prscore)
    p_prscore.set_defaults(func=cmd_score)

    # test-quality
    p_testquality = sub.add_parser("test-quality", help="Test quality grader")
    _add_json(p_testquality)
    _add_repo(p_testquality)
    p_testquality.set_defaults(func=cmd_test_quality)

    # refactor
    p_refactor = sub.add_parser("refactor", help="Self-refactor engine")
    p_refactor.add_argument("--apply", action="store_true", help="Apply safe fixes")
    p_refactor.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_refactor)
    p_refactor.set_defaults(func=cmd_refactor)

    # commits
    p_commits = sub.add_parser("commits", help="Commit message quality analyzer")
    p_commits.add_argument("--top", type=int, default=500, help="Max commits to analyse (default: 500)")
    _add_json(p_commits)
    _add_repo(p_commits)
    p_commits.set_defaults(func=cmd_commits)

    # semver
    p_semver = sub.add_parser("semver", help="Semver bump recommender")
    _add_json(p_semver)
    _add_repo(p_semver)
    p_semver.set_defaults(func=cmd_semver)

    # modules
    p_modules = sub.add_parser("modules", help="Module interconnection graph")
    p_modules.add_argument("--ascii", action="store_true", help="ASCII output instead of Mermaid")
    p_modules.add_argument("--write", action="store_true", help="Write to docs/MODULE_GRAPH.md")
    _add_json(p_modules)
    _add_repo(p_modules)
    p_modules.set_defaults(func=cmd_modules)

    # trends
    p_trends = sub.add_parser("trends", help="Historical trend data")
    p_trends.add_argument("--write", action="store_true", help="Write to docs/trend_data.json")
    _add_json(p_trends)
    _add_repo(p_trends)
    p_trends.set_defaults(func=cmd_trends)

    # plan / brain
    p_plan = sub.add_parser("plan", help="Session task planner")
    p_plan.add_argument("--session", type=int, default=1, help="Session number")
    p_plan.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_brain = sub.add_parser("brain", help="Session task planner (alias for plan)")
    p_brain.add_argument("--session", type=int, default=1, help="Session number")
    p_brain.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_brain)
    p_brain.set_defaults(func=cmd_plan)

    # triage
    p_triage = sub.add_parser("triage", help="Issue triage")
    p_triage.add_argument("--issues", default=None, help="Path to issues JSON")
    p_triage.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_triage)
    p_triage.set_defaults(func=cmd_triage)

    # depgraph
    p_depgraph = sub.add_parser("depgraph", help="Module dependency graph")
    _add_write(p_depgraph)
    _add_json(p_depgraph)
    _add_repo(p_depgraph)
    p_depgraph.set_defaults(func=cmd_depgraph)

    # arch
    p_arch = sub.add_parser("arch", help="Architecture doc generator")
    p_arch.add_argument("--write", action="store_true")
    _add_repo(p_arch)
    p_arch.set_defaults(func=cmd_arch)

    # ------------------------------------------------------------------
    # Infrastructure commands
    # ------------------------------------------------------------------

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Launch React dashboard")
    p_dash.add_argument("--port", type=int, default=8710, help="Port (default: 8710)")
    p_dash.add_argument("--no-browser", action="store_true", help="Don't open browser")
    _add_repo(p_dash)
    p_dash.set_defaults(func=cmd_dashboard)

    # init
    p_init = sub.add_parser("init", help="Bootstrap project scaffolding")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing files")
    _add_repo(p_init)
    p_init.set_defaults(func=cmd_init)

    # deps
    p_deps = sub.add_parser("deps", help="Dependency freshness checker")
    p_deps.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_deps)
    p_deps.set_defaults(func=cmd_deps)

    # config
    p_config = sub.add_parser("config", help="Show or write nightshift.toml")
    p_config.add_argument("--write", action="store_true", help="Write default config")
    p_config.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_config)
    p_config.set_defaults(func=cmd_config)

    # plugins
    p_plugins = sub.add_parser("plugins", help="Plugin/hook registry")
    p_plugins.add_argument("--example", action="store_true", help="Show example nightshift.toml snippet")
    p_plugins.add_argument("--run", default=None, metavar="HOOK", help="Run all plugins for a hook")
    _add_json(p_plugins)
    _add_repo(p_plugins)
    p_plugins.set_defaults(func=cmd_plugins)

    # openapi
    p_openapi = sub.add_parser("openapi", help="Generate OpenAPI 3.1 spec")
    p_openapi.add_argument("--format", choices=["json", "yaml", "markdown"], default="json")
    p_openapi.add_argument("--write", action="store_true", help="Write to docs/openapi.json")
    _add_json(p_openapi)
    _add_repo(p_openapi)
    p_openapi.set_defaults(func=cmd_openapi)

    # run
    p_run = sub.add_parser("run", help="Full session pipeline")
    p_run.add_argument("--session", type=int, default=1, help="Session number")
    _add_repo(p_run)
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv=None) -> int:
    """Entry point for the nightshift CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
