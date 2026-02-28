"""Unified CLI entry point for Nightshift.

Provides a single ``nightshift`` command that ties together all analysis
modules into a coherent developer experience.  Every subcommand corresponds
to one (or more) modules in ``src/``.

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
    # or after ``pip install -e .``:
    nightshift <command> [options]

Note
----
Sessions 1-11 features are fully implemented in src/. The coupling,
complexity, and export subcommands below correspond to the Session 11
features that were re-landed (they were already present in main via
earlier merges). Session 12 adds config, compare, dashboard, and deps.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent


def _repo(args_path: Optional[str] = None) -> Path:
    """Return the repo root, preferring an explicit --repo flag."""
    return Path(args_path) if args_path else REPO_ROOT


def _print_header(title: str) -> None:
    bar = "─" * 60
    print(f"\n{bar}")
    print(f"  🌙 Nightshift  ·  {title}")
    print(f"{bar}\n")


def _print_ok(msg: str) -> None:
    print(f"  ✅  {msg}")


def _print_warn(msg: str) -> None:
    print(f"  ⚠️   {msg}")


def _print_info(msg: str) -> None:
    print(f"  ·  {msg}")


# ---------------------------------------------------------------------------
# Subcommand: health
# ---------------------------------------------------------------------------


def cmd_health(args: argparse.Namespace) -> int:
    from src.health import generate_health_report
    _print_header("Code Health Report")
    repo = _repo(getattr(args, "repo", None))
    report = generate_health_report(repo_path=repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(f"Overall score: {report.overall_health_score}/100")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: stats
# ---------------------------------------------------------------------------


def cmd_stats(args: argparse.Namespace) -> int:
    from src.stats import compute_stats
    _print_header("Repository Stats")
    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"
    stats = compute_stats(repo_path=repo, log_path=log_path)
    if args.json:
        print(json.dumps(stats.to_dict(), indent=2))
        return 0
    print(stats.readme_table())
    print()
    _print_info(f"Sessions in log: {len(stats.sessions)}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: diff
# ---------------------------------------------------------------------------


def cmd_diff(args: argparse.Namespace) -> int:
    from src.diff_visualizer import build_session_diff, render_session_diff
    _print_header(f"Session Diff — Session {args.session}")
    repo = _repo(getattr(args, "repo", None))
    diff = build_session_diff(repo_root=repo, session_number=args.session)
    md = render_session_diff(diff)
    if args.json:
        import dataclasses
        print(json.dumps(dataclasses.asdict(diff), indent=2))
        return 0
    print(md)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: changelog
# ---------------------------------------------------------------------------


def cmd_changelog(args: argparse.Namespace) -> int:
    from src.changelog import generate_changelog, save_changelog
    _print_header("Changelog")
    repo = _repo(getattr(args, "repo", None))
    # --release flag: generate polished GitHub Releases notes
    if getattr(args, "release", False):
        from src.release_notes import generate_release_notes
        version = getattr(args, "version", None)
        notes = generate_release_notes(repo, version=version)
        if args.json:
            print(json.dumps(notes.to_dict(), indent=2))
            return 0
        if args.write:
            out = repo / "RELEASE_NOTES.md"
            notes.save(out)
            _print_ok(f"Release notes written to {out}")
            return 0
        print(notes.to_markdown())
        return 0
    changelog = generate_changelog(repo_path=repo)
    if args.write:
        out = repo / "CHANGELOG.md"
        save_changelog(changelog, out)
        _print_ok(f"Written to {out}")
        return 0
    if args.json:
        print(json.dumps(changelog.to_dict(), indent=2))
        return 0
    print(changelog.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: coverage
# ---------------------------------------------------------------------------


def cmd_coverage(args: argparse.Namespace) -> int:
    from src.coverage_tracker import CoverageHistory
    _print_header("Test Coverage Trend")
    repo = _repo(getattr(args, "repo", None))
    history_path = repo / "docs" / "coverage_history.json"
    if not history_path.exists():
        _print_warn(f"No coverage history found at {history_path}")
        _print_info("Run `nightshift run` to generate initial coverage data.")
        return 1
    with history_path.open() as f:
        history = CoverageHistory.from_dict(json.load(f))
    if args.json:
        print(json.dumps(history.to_dict(), indent=2))
        return 0
    print(history.to_markdown())
    latest = history.latest()
    if latest:
        _print_info(f"Latest: {latest.coverage_badge} (Session {latest.session})")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: score
# ---------------------------------------------------------------------------


def cmd_score(args: argparse.Namespace) -> int:
    from src.pr_scorer import load_scores, render_leaderboard
    _print_header("PR Quality Leaderboard")
    repo = _repo(getattr(args, "repo", None))
    scores_path = repo / "docs" / "pr_scores.json"
    if not scores_path.exists():
        _print_warn(f"No PR scores found at {scores_path}")
        _print_info("Run `nightshift run` to score the latest PRs.")
        return 1
    scores = load_scores(scores_path)
    if args.json:
        print(json.dumps([s.__dict__ for s in scores], indent=2, default=str))
        return 0
    print(render_leaderboard(scores))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: arch
# ---------------------------------------------------------------------------


def cmd_arch(args: argparse.Namespace) -> int:
    try:
        from src.arch_generator import generate_architecture_doc, save_architecture_doc
    except ImportError:
        _print_warn("arch_generator module not available")
        return 1
    _print_header("Architecture Doc Generator")
    repo = _repo(getattr(args, "repo", None))
    doc = generate_architecture_doc(repo_path=repo)
    if args.write:
        out = repo / "docs" / "ARCHITECTURE.md"
        save_architecture_doc(doc, out)
        _print_ok(f"Written to {out}")
        return 0
    print(doc)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: refactor
# ---------------------------------------------------------------------------


def cmd_refactor(args: argparse.Namespace) -> int:
    try:
        from src.refactor import RefactorEngine
    except ImportError:
        _print_warn("refactor module not available")
        return 1
    _print_header("Self-Refactor Engine")
    repo = _repo(getattr(args, "repo", None))
    engine = RefactorEngine(repo_path=repo)
    report = engine.analyze()
    if args.apply:
        applied = engine.apply_safe_fixes(report)
        _print_ok(f"Applied {applied} safe fixes")
        return 0
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: replay
# ---------------------------------------------------------------------------


def cmd_replay(args: argparse.Namespace) -> int:
    from src.session_replay import replay, replay_all
    _print_header(f"Session Replay")
    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"
    if args.session is not None:
        r = replay(log_path, args.session)
        if r is None:
            _print_warn(f"Session {args.session} not found in {log_path}")
            return 1
        if args.json:
            print(json.dumps(r.to_dict(), indent=2, default=str))
        else:
            print(r.to_markdown())
    else:
        all_r = replay_all(log_path)
        if not all_r:
            _print_warn(f"No sessions found in {log_path}")
            return 1
        for r in all_r:
            print(f"Session {r.session_number}: {r.date} — {r.task_count} task(s), {r.pr_count} PR(s)")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: plan
# ---------------------------------------------------------------------------


def cmd_plan(args: argparse.Namespace) -> int:
    from src.brain import Brain
    _print_header(f"Session Plan — Session {args.session}")
    repo = _repo(getattr(args, "repo", None))
    brain = Brain(repo_root=repo)
    plan = brain.plan(
        session_number=args.session,
        roadmap_path=repo / "ROADMAP.md",
        issues_path=repo / "docs" / "triage.json",
        health_history_path=repo / "docs" / "health_history.json",
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, default=str))
        return 0
    print(plan.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: triage
# ---------------------------------------------------------------------------


def cmd_triage(args: argparse.Namespace) -> int:
    from src.issue_triage import load_issues, triage_issues, render_triage_report
    _print_header("Issue Triage")
    repo = _repo(getattr(args, "repo", None))
    issues_path = Path(args.issues) if args.issues else repo / "docs" / "issues.json"
    if not issues_path.exists():
        _print_warn(f"Issues file not found: {issues_path}")
        _print_info("Export issues with the GitHub CLI: gh issue list --json ... > docs/issues.json")
        return 1
    issues = load_issues(issues_path)
    triaged = triage_issues(issues)
    if args.json:
        print(json.dumps([t.to_dict() for t in triaged], indent=2, default=str))
        return 0
    print(render_triage_report(triaged))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: depgraph
# ---------------------------------------------------------------------------


def cmd_depgraph(args: argparse.Namespace) -> int:
    from src.dep_graph import build_dep_graph, render_dep_graph, save_dep_graph
    _print_header("Module Dependency Graph")
    repo = _repo(getattr(args, "repo", None))
    graph = build_dep_graph(repo / "src")
    if args.write:
        out = repo / "docs" / "dep_graph.md"
        save_dep_graph(graph, out)
        _print_ok(f"Written to {out} (+ JSON sidecar)")
        return 0
    if args.json:
        print(json.dumps(graph.to_dict(), indent=2, default=str))
        return 0
    print(render_dep_graph(graph))
    cycles = graph.find_cycles()
    if cycles:
        _print_warn(f"{len(cycles)} circular dependency chain(s) detected")
    else:
        _print_ok("No circular dependencies")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: todos
# ---------------------------------------------------------------------------


def cmd_todos(args: argparse.Namespace) -> int:
    from src.todo_hunter import hunt, render_todo_report, save_todo_report
    _print_header("TODO / FIXME Hunter")
    repo = _repo(getattr(args, "repo", None))
    items = hunt(repo / "src", current_session=args.session, threshold=args.threshold)
    if args.write:
        out = repo / "docs" / "todo_report.md"
        save_todo_report(items, out, current_session=args.session, threshold=args.threshold)
        _print_ok(f"Report written to {out}")
        return 0
    if args.json:
        print(json.dumps([i.to_dict() for i in items], indent=2, default=str))
        return 0
    print(render_todo_report(items, current_session=args.session, threshold=args.threshold))
    stale_count = sum(1 for i in items if i.is_stale)
    if stale_count:
        _print_warn(f"{stale_count} stale annotation(s) found")
    else:
        _print_ok("No stale annotations")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: doctor
# ---------------------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    from src.doctor import diagnose, render_report, save_report
    _print_header("Nightshift Doctor")
    repo = _repo(getattr(args, "repo", None))
    report = diagnose(repo)
    if args.write:
        out = repo / "docs" / "doctor_report.md"
        save_report(report, out)
        _print_ok(f"Report written to {out}")
        return 0
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0
    print(render_report(report))
    grade = report.grade
    if grade in ("A", "B"):
        _print_ok(f"Grade: {grade} — repo is healthy")
    elif grade in ("C", "D"):
        _print_warn(f"Grade: {grade} — some issues need attention")
    else:
        _print_warn(f"Grade: {grade} — critical issues detected")
    return 0 if report.fail_count == 0 else 1


# ---------------------------------------------------------------------------
# Subcommand: timeline
# ---------------------------------------------------------------------------


def cmd_timeline(args: argparse.Namespace) -> int:
    """Render an ASCII visual timeline of all Nightshift sessions."""
    from src.timeline import build_timeline, save_timeline
    _print_header("Session Timeline")
    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"
    timeline = build_timeline(log_path=log_path, repo_path=repo)
    if args.json:
        print(timeline.to_json())
        return 0
    if args.write:
        out = repo / "docs" / "timeline.md"
        save_timeline(timeline, out)
        _print_ok(f"Timeline written to {out}")
        _print_ok(f"JSON sidecar → {out.with_suffix('.json')}")
        return 0
    print(timeline.to_markdown())
    _print_info(
        f"Sessions: {timeline.total_sessions}  ·  Total PRs: {timeline.total_prs}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: coupling
# ---------------------------------------------------------------------------


def cmd_coupling(args: argparse.Namespace) -> int:
    """Analyze module coupling — afferent/efferent coupling, instability metric.

    Session 11 feature. Implemented in src/coupling.py.
    """
    from src.coupling import analyze_coupling, save_coupling_report
    _print_header("Module Coupling Analysis")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_coupling(repo_path=repo)
    if args.json:
        print(report.to_json())
        return 0
    if args.write:
        out = repo / "docs" / "coupling_report.md"
        save_coupling_report(report, out)
        _print_ok(f"Report written to {out}")
        _print_ok(f"JSON sidecar → {out.with_suffix('.json')}")
        return 0
    print(report.to_markdown())
    _print_info(
        f"Modules: {len(report.modules)}  ·  "
        f"Avg instability: {report.avg_instability:.2f}  ·  "
        f"HIGH: {report.high_count}  MEDIUM: {report.medium_count}  LOW: {report.low_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: complexity
# ---------------------------------------------------------------------------


def cmd_complexity(args: argparse.Namespace) -> int:
    """Analyze cyclomatic complexity — McCabe complexity per function.

    Session 11 feature. Implemented in src/complexity.py.
    """
    from src.complexity import analyze_complexity, save_complexity_report
    _print_header("Cyclomatic Complexity Analysis")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_complexity(repo_path=repo)
    if args.json:
        print(report.to_json())
        return 0
    if args.write:
        out = repo / "docs" / "complexity_report.md"
        save_complexity_report(report, out)
        _print_ok(f"Report written to {out}")
        _print_ok(f"JSON sidecar → {out.with_suffix('.json')}")
        return 0
    print(report.to_markdown())
    _print_info(
        f"Functions: {report.total_functions}  ·  "
        f"Avg complexity: {report.avg_complexity:.1f}  ·  "
        f"HIGH: {report.high_count}  MEDIUM: {report.medium_count}  LOW: {report.low_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: export
# ---------------------------------------------------------------------------


def cmd_export(args: argparse.Namespace) -> int:
    """Export any analysis output to JSON, Markdown, or HTML.

    Session 11 feature. Implemented in src/exporter.py.
    """
    from src.exporter import Exporter, ExportFormat
    _print_header("Analysis Exporter")
    repo = _repo(getattr(args, "repo", None))
    fmt_map = {"json": ExportFormat.JSON, "markdown": ExportFormat.MARKDOWN, "html": ExportFormat.HTML}
    fmt = fmt_map.get(args.format, ExportFormat.JSON)
    exporter = Exporter(repo_path=repo, output_dir=repo / "docs" / "exports")
    exported = exporter.export_all(fmt)
    _print_ok(f"Exported {len(exported)} reports to {repo / 'docs' / 'exports'}")
    for path in exported:
        _print_info(str(path))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: config
# ---------------------------------------------------------------------------


def cmd_config(args: argparse.Namespace) -> int:
    """Show or write nightshift.toml configuration.

    Session 12 feature. Implemented in src/config.py.
    """
    from src.config import NightshiftConfig, DEFAULT_CONFIG_TOML
    _print_header("Nightshift Config")
    repo = _repo(getattr(args, "repo", None))
    config_path = repo / "nightshift.toml"
    if args.write:
        if config_path.exists():
            _print_warn(f"Config already exists at {config_path}")
            _print_info("Use --force to overwrite.")
            return 1
        config_path.write_text(DEFAULT_CONFIG_TOML)
        _print_ok(f"Written default config to {config_path}")
        return 0
    if config_path.exists():
        cfg = NightshiftConfig.from_toml(config_path)
        if args.json:
            print(json.dumps(cfg.to_dict(), indent=2))
            return 0
        print(cfg.to_markdown())
    else:
        _print_warn(f"No nightshift.toml found at {config_path}")
        _print_info("Run `nightshift config --write` to create a default config.")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: compare
# ---------------------------------------------------------------------------


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare two sessions side-by-side.

    Session 12 feature. Implemented in src/compare.py.
    """
    from src.compare import compare_sessions, render_comparison
    _print_header(f"Session Comparison — {args.session_a} vs {args.session_b}")
    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"
    comparison = compare_sessions(log_path=log_path, session_a=args.session_a, session_b=args.session_b)
    if args.json:
        print(json.dumps(comparison.to_dict(), indent=2, default=str))
        return 0
    print(render_comparison(comparison))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: dashboard
# ---------------------------------------------------------------------------


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch the live React dashboard (API server + UI).

    Session 12 feature. Starts the HTTP API server that the React
    frontend talks to.
    """
    from src.server import start_server
    _print_header("Nightshift Dashboard")
    repo = _repo(getattr(args, "repo", None))
    port = getattr(args, "port", 8710)
    _print_ok(f"Starting API server on port {port} ...")
    _print_info("Open http://127.0.0.1:8710 in your browser.")
    _print_info("Press Ctrl+C to stop.")
    start_server(port=port, repo_path=repo, open_browser=not getattr(args, "no_browser", False))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: deps
# ---------------------------------------------------------------------------


def cmd_deps(args: argparse.Namespace) -> int:
    """Check Python dependency freshness via PyPI.

    Session 12 feature. Implemented in src/deps.py.
    """
    try:
        from src.deps import check_deps, render_deps_report
    except ImportError:
        _print_warn("deps module not available")
        return 1
    _print_header("Dependency Freshness Check")
    repo = _repo(getattr(args, "repo", None))
    report = check_deps(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(render_deps_report(report))
    stale = [d for d in report.deps if d.is_stale]
    if stale:
        _print_warn(f"{len(stale)} stale dependencies")
    else:
        _print_ok("All dependencies up-to-date")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: blame  (Session 13)
# ---------------------------------------------------------------------------


def cmd_blame(args: argparse.Namespace) -> int:
    """Human vs AI contribution attribution via git blame."""
    from src.blame import analyze_blame
    _print_header("Blame Attribution")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_blame(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Human: {report.human_pct:.1f}%  ·  AI: {report.ai_pct:.1f}%  ·  "
        f"Files analysed: {report.file_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: security  (Session 13)
# ---------------------------------------------------------------------------


def cmd_security(args: argparse.Namespace) -> int:
    """Security audit: common Python anti-patterns."""
    from src.security import audit_security
    _print_header("Security Audit")
    repo = _repo(getattr(args, "repo", None))
    report = audit_security(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    grade = report.grade
    if grade in ("A+", "A", "B+"):
        _print_ok(f"Grade: {grade} — no critical issues")
    else:
        _print_warn(f"Grade: {grade} — HIGH: {report.high_count}  MEDIUM: {report.medium_count}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: deadcode  (Session 13)
# ---------------------------------------------------------------------------


def cmd_deadcode(args: argparse.Namespace) -> int:
    """Dead code detector: unused functions, classes, imports."""
    from src.dead_code import detect_dead_code
    _print_header("Dead Code Detector")
    repo = _repo(getattr(args, "repo", None))
    report = detect_dead_code(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Dead symbols: {report.dead_count}  ·  "
        f"HIGH: {report.high_count}  MEDIUM: {report.medium_count}  LOW: {report.low_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: coveragemap  (Session 13)
# ---------------------------------------------------------------------------


def cmd_coveragemap(args: argparse.Namespace) -> int:
    """Coverage heat map: weakest test files ranked first."""
    from src.coverage_map import build_coverage_map
    _print_header("Coverage Heat Map")
    repo = _repo(getattr(args, "repo", None))
    report = build_coverage_map(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(f"Overall: {report.overall_pct:.1f}%  ·  Files: {report.file_count}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: maturity  (Session 14)
# ---------------------------------------------------------------------------


def cmd_maturity(args: argparse.Namespace) -> int:
    """Compute per-module maturity score (0-100)."""
    from src.maturity import analyze_maturity
    _print_header("Module Maturity Scores")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_maturity(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Modules: {report.module_count}  ·  Avg: {report.avg_score:.1f}/100  ·  "
        f"High: {report.high_count}  Medium: {report.medium_count}  Low: {report.low_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: dna  (Session 14)
# ---------------------------------------------------------------------------


def cmd_dna(args: argparse.Namespace) -> int:
    """Generate 6-channel visual repo DNA fingerprint."""
    from src.dna import generate_dna
    _print_header("Repo DNA Fingerprint")
    repo = _repo(getattr(args, "repo", None))
    dna = generate_dna(repo)
    if args.json:
        print(json.dumps(dna.to_dict(), indent=2))
        return 0
    print(dna.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: story  (Session 14)
# ---------------------------------------------------------------------------


def cmd_story(args: argparse.Namespace) -> int:
    """Generate narrative prose summary of repo evolution."""
    from src.story import generate_story
    _print_header("Repo Story")
    repo = _repo(getattr(args, "repo", None))
    story = generate_story(repo)
    if args.json:
        print(json.dumps(story.to_dict(), indent=2))
        return 0
    print(story.to_markdown())
    _print_info(
        f"Sessions: {story.total_sessions}  ·  Total PRs: {story.total_prs}  ·  Tests: {story.total_tests}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: benchmark  (Session 15)
# ---------------------------------------------------------------------------


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run the performance benchmark suite."""
    from src.benchmark import run_benchmarks
    _print_header("Performance Benchmark Suite")
    repo = _repo(getattr(args, "repo", None))
    report = run_benchmarks(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    regressions = report.regressions
    if regressions:
        _print_warn(f"{len(regressions)} regression(s) detected")
    else:
        _print_ok("No regressions detected")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: gitstats  (Session 15)
# ---------------------------------------------------------------------------


def cmd_gitstats(args: argparse.Namespace) -> int:
    """Git statistics deep-dive: churn, velocity, commit frequency."""
    from src.gitstats import analyze_gitstats
    _print_header("Git Statistics Deep-Dive")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_gitstats(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Commits: {report.total_commits}  ·  "
        f"Contributors: {report.contributor_count}  ·  "
        f"Active days: {report.active_days}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: badges  (Session 15)
# ---------------------------------------------------------------------------


def cmd_badges(args: argparse.Namespace) -> int:
    """Generate Shields.io badge metadata from live metrics."""
    from src.badges import generate_badges
    _print_header("Badge Generator")
    repo = _repo(getattr(args, "repo", None))
    report = generate_badges(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    if args.write:
        out = repo / "docs" / "badges.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2))
        _print_ok(f"Written to {out}")
        return 0
    print(report.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: teach  (Session 15)
# ---------------------------------------------------------------------------


def cmd_teach(args: argparse.Namespace) -> int:
    """Generate an AST-based tutorial for a specific module."""
    from src.teach import generate_tutorial
    _print_header(f"Module Tutorial: {args.module}")
    repo = _repo(getattr(args, "repo", None))
    tutorial = generate_tutorial(repo, args.module)
    if args.json:
        print(json.dumps(tutorial.to_dict(), indent=2))
        return 0
    print(tutorial.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: audit  (Session 16)
# ---------------------------------------------------------------------------


def cmd_audit(args: argparse.Namespace) -> int:
    """Comprehensive repo audit: weighted composite A–F grade."""
    from src.audit import run_audit
    _print_header("Comprehensive Repo Audit")
    repo = _repo(getattr(args, "repo", None))
    report = run_audit(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    grade = report.overall_grade
    if grade in ("A+", "A", "B+"):
        _print_ok(f"Overall Grade: {grade}")
    elif grade in ("B", "B-", "C+"):
        _print_info(f"Overall Grade: {grade}")
    else:
        _print_warn(f"Overall Grade: {grade} — action required")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: semver  (Session 16)
# ---------------------------------------------------------------------------


def cmd_semver(args: argparse.Namespace) -> int:
    """Conventional Commits → semver bump recommendation."""
    from src.semver import analyze_semver
    _print_header("Semantic Version Analysis")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_semver(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Current: {report.current_version}  ·  "
        f"Recommended bump: {report.recommended_bump}  ·  "
        f"Next: {report.next_version}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: predict  (Session 16)
# ---------------------------------------------------------------------------


def cmd_predict(args: argparse.Namespace) -> int:
    """Five-signal predictor: which modules need attention next."""
    from src.predict import run_predict
    _print_header("Predictive Session Planner")
    repo = _repo(getattr(args, "repo", None))
    report = run_predict(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Top candidate: {report.top_module}  ·  "
        f"Confidence: {report.top_confidence:.0f}%"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: init  (Session 16)
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Bootstrap project scaffolding and nightshift.toml."""
    from src.init_cmd import init_project
    _print_header("Nightshift Init")
    repo = _repo(getattr(args, "repo", None))
    result = init_project(repo, force=getattr(args, "force", False))
    for msg in result.messages:
        _print_ok(msg)
    for warn in result.warnings:
        _print_warn(warn)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Run the full end-of-session pipeline."""
    from src.stats import compute_stats
    from src.health import generate_health_report
    _print_header(f"Full Pipeline — Session {args.session}")
    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"
    _print_info("Running health analysis ...")
    health_report = generate_health_report(repo_path=repo)
    _print_ok(f"Health score: {health_report.overall_health_score}/100")
    _print_info("Computing stats ...")
    stats = compute_stats(repo_path=repo, log_path=log_path)
    _print_ok(f"Sessions tracked: {len(stats.sessions)}")
    _print_ok("Pipeline complete.")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: modules (Session 17)
# ---------------------------------------------------------------------------


def cmd_modules(args: argparse.Namespace) -> int:
    from src.module_graph import generate_module_graph
    _print_header("Module Interconnection Graph")
    repo = _repo(getattr(args, "repo", None))
    graph = generate_module_graph(repo)
    if args.json:
        print(json.dumps(graph.to_dict(), indent=2))
        return 0
    if getattr(args, "ascii", False):
        print(graph.to_ascii())
        return 0
    if getattr(args, "write", False):
        out = repo / "docs" / "MODULE_GRAPH.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(graph.to_markdown(), encoding="utf-8")
        _print_ok(f"Written to {out}")
        return 0
    print(graph.to_mermaid())
    _print_info(f"Modules: {len(graph.nodes)}  Edges: {len(graph.edges)}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: trends (Session 17)
# ---------------------------------------------------------------------------


def cmd_trends(args: argparse.Namespace) -> int:
    from src.trend_data import generate_trend_data
    _print_header("Historical Trend Data")
    repo = _repo(getattr(args, "repo", None))
    td = generate_trend_data(repo)
    if args.json:
        print(json.dumps(td.to_dict(), indent=2))
        return 0
    if getattr(args, "write", False):
        out = repo / "docs" / "trend_data.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(td.to_dict(), indent=2), encoding="utf-8")
        _print_ok(f"Written to {out}")
        return 0
    print(td.to_markdown())
    _print_info(f"Sessions: {td.total_sessions}  Latest: {td.latest_session}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: commits (Session 17)
# ---------------------------------------------------------------------------


def cmd_commits(args: argparse.Namespace) -> int:
    from src.commit_analyzer import analyze_commits
    _print_header("Commit Message Quality Analyzer")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_commits(repo, max_commits=getattr(args, "top", 500))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Commits analyzed: {report.total_commits}  ·  "
        f"Avg quality: {report.avg_quality_score:.1f}/100  ·  Grade: {report.quality_grade}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: diff-sessions (Session 17)
# ---------------------------------------------------------------------------


def cmd_diff_sessions(args: argparse.Namespace) -> int:
    from src.diff_sessions import compare_sessions
    session_a = int(args.session_a)
    session_b = int(args.session_b)
    _print_header(f"Session Diff: {session_a} → {session_b}")
    repo = _repo(getattr(args, "repo", None))
    report = compare_sessions(repo, session_a, session_b)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    print()
    print(report.to_rich_table())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: test-quality (Session 17)
# ---------------------------------------------------------------------------


def cmd_test_quality(args: argparse.Namespace) -> int:
    from src.test_quality import analyze_test_quality
    _print_header("Test Quality Analyzer")
    repo = _repo(getattr(args, "repo", None))
    report = analyze_test_quality(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(
        f"Files: {report.total_test_files}  ·  "
        f"Tests: {report.total_tests}  ·  "
        f"Avg score: {report.avg_score:.1f}/100  ·  Grade: {report.overall_grade}"
    )
    return 0


# ---------------------------------------------------------------------------
# Subcommand: report (Session 17)
# ---------------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> int:
    from src.report import generate_report
    _print_header("Executive HTML Report")
    repo = _repo(getattr(args, "repo", None))
    output = Path(args.output) if getattr(args, "output", None) else repo / "docs" / "report.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    report = generate_report(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    html = report.to_html()
    output.write_text(html, encoding="utf-8")
    _print_ok(f"Report written to {output}")
    _print_info(
        f"Sections: {len(report.sections)}  ·  "
        f"Overall grade: {report.overall_grade}"
    )
    if getattr(args, "open", False):
        import webbrowser
        webbrowser.open(output.as_uri())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: openapi (Session 17)
# ---------------------------------------------------------------------------


def cmd_openapi(args: argparse.Namespace) -> int:
    from src.openapi import generate_openapi_spec
    _print_header("OpenAPI 3.1 Spec Generator")
    repo = _repo(getattr(args, "repo", None))
    spec = generate_openapi_spec(repo)
    if args.json or getattr(args, "format", "json") == "json":
        print(json.dumps(spec.to_dict(), indent=2))
        if getattr(args, "write", False):
            out = repo / "docs" / "openapi.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps(spec.to_dict(), indent=2), encoding="utf-8")
            _print_ok(f"JSON spec written to {out}")
        return 0
    if getattr(args, "format", None) == "yaml":
        print(spec.to_yaml())
        if getattr(args, "write", False):
            out = repo / "docs" / "openapi.yaml"
            out.parent.mkdir(exist_ok=True)
            out.write_text(spec.to_yaml(), encoding="utf-8")
            _print_ok(f"YAML spec written to {out}")
        return 0
    # Default: markdown table
    print(spec.to_markdown())
    _print_info(f"Endpoints: {len(spec.paths)}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: plugins (Session 17)
# ---------------------------------------------------------------------------


def cmd_plugins(args: argparse.Namespace) -> int:
    from src.plugins import load_plugin_definitions, list_plugins, run_plugins, EXAMPLE_TOML_SNIPPET
    _print_header("Plugin Registry")
    repo = _repo(getattr(args, "repo", None))

    # --example: show TOML snippet
    if getattr(args, "example", False):
        print(EXAMPLE_TOML_SNIPPET)
        return 0

    # --run <hook>: execute plugins for a hook
    if getattr(args, "run", None):
        hook = args.run
        report = run_plugins(hook, repo_root=repo)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
            return 0
        print(report.to_markdown())
        _print_info(
            f"Hook: {hook}  ·  Ran: {report.plugins_run}  ·  "
            f"OK: {report.ok}  Warnings: {report.warnings}  Errors: {report.errors}"
        )
        return 0

    # Default: list plugins
    if args.json:
        defs = load_plugin_definitions(repo)
        print(json.dumps([d.to_dict() for d in defs], indent=2))
        return 0
    print(list_plugins(repo))
    return 0


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

    # Common flags
    def _add_json(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="Output raw JSON")

    def _add_repo(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo", default=None, help="Path to repo root")

    def _add_write(p: argparse.ArgumentParser) -> None:
        p.add_argument("--write", action="store_true", help="Write output to file")

    # health
    p_health = sub.add_parser("health", help="Code health analysis")
    _add_json(p_health)
    _add_repo(p_health)
    p_health.set_defaults(func=cmd_health)

    # stats
    p_stats = sub.add_parser("stats", help="Repository statistics")
    _add_json(p_stats)
    _add_repo(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    # diff
    p_diff = sub.add_parser("diff", help="Visualise session diff")
    p_diff.add_argument("--session", type=int, default=None, help="Session number")
    p_diff.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_diff)
    p_diff.set_defaults(func=cmd_diff)

    # changelog
    p_cl = sub.add_parser("changelog", help="Render CHANGELOG.md")
    p_cl.add_argument("--write", action="store_true", help="Write CHANGELOG.md")
    p_cl.add_argument("--json", action="store_true", help="Output raw JSON")
    p_cl.add_argument("--release", action="store_true", help="Generate polished GitHub Releases notes")
    p_cl.add_argument("--version", default=None, help="Version tag for release notes (e.g. v0.17.0)")
    _add_repo(p_cl)
    p_cl.set_defaults(func=cmd_changelog)

    # coverage
    p_cov = sub.add_parser("coverage", help="Test coverage trend")
    _add_json(p_cov)
    _add_repo(p_cov)
    p_cov.set_defaults(func=cmd_coverage)

    # score
    p_score = sub.add_parser("score", help="PR quality leaderboard")
    _add_json(p_score)
    _add_repo(p_score)
    p_score.set_defaults(func=cmd_score)

    # arch
    p_arch = sub.add_parser("arch", help="Architecture doc generator")
    p_arch.add_argument("--write", action="store_true")
    _add_repo(p_arch)
    p_arch.set_defaults(func=cmd_arch)

    # refactor
    p_refactor = sub.add_parser("refactor", help="Self-refactor engine")
    p_refactor.add_argument("--apply", action="store_true", help="Apply safe fixes")
    p_refactor.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_refactor)
    p_refactor.set_defaults(func=cmd_refactor)

    # replay
    p_replay = sub.add_parser("replay", help="Replay a session")
    p_replay.add_argument("--session", type=int, default=None, help="Session number")
    p_replay.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_replay)
    p_replay.set_defaults(func=cmd_replay)

    # plan / brain (alias)
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
    p_depgraph.add_argument("--write", action="store_true")
    p_depgraph.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_depgraph)
    p_depgraph.set_defaults(func=cmd_depgraph)

    # todos
    p_todos = sub.add_parser("todos", help="TODO/FIXME hunter")
    p_todos.add_argument("--write", action="store_true")
    p_todos.add_argument("--json", action="store_true", help="Output raw JSON")
    p_todos.add_argument("--session", type=int, default=1, help="Current session number")
    p_todos.add_argument("--threshold", type=int, default=3, help="Stale threshold (sessions)")
    _add_repo(p_todos)
    p_todos.set_defaults(func=cmd_todos)

    # doctor
    p_doctor = sub.add_parser("doctor", help="Full repo health diagnostic")
    p_doctor.add_argument("--write", action="store_true")
    p_doctor.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_doctor)
    p_doctor.set_defaults(func=cmd_doctor)

    # timeline
    p_timeline = sub.add_parser("timeline", help="Session timeline")
    p_timeline.add_argument("--write", action="store_true")
    p_timeline.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_timeline)
    p_timeline.set_defaults(func=cmd_timeline)

    # coupling
    p_coupling = sub.add_parser("coupling", help="Module coupling analysis")
    p_coupling.add_argument("--write", action="store_true")
    p_coupling.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_coupling)
    p_coupling.set_defaults(func=cmd_coupling)

    # complexity
    p_complexity = sub.add_parser("complexity", help="Cyclomatic complexity")
    p_complexity.add_argument("--write", action="store_true")
    p_complexity.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_complexity)
    p_complexity.set_defaults(func=cmd_complexity)

    # export
    p_export = sub.add_parser("export", help="Export analysis to JSON/Markdown/HTML")
    p_export.add_argument("--format", choices=["json", "markdown", "html"], default="json")
    _add_repo(p_export)
    p_export.set_defaults(func=cmd_export)

    # config
    p_config = sub.add_parser("config", help="Show or write nightshift.toml")
    p_config.add_argument("--write", action="store_true", help="Write default config")
    p_config.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_config)
    p_config.set_defaults(func=cmd_config)

    # compare
    p_compare = sub.add_parser("compare", help="Compare two sessions")
    p_compare.add_argument("session_a", type=int, help="Session A")
    p_compare.add_argument("session_b", type=int, help="Session B")
    p_compare.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_compare)
    p_compare.set_defaults(func=cmd_compare)

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Launch React dashboard")
    p_dash.add_argument("--port", type=int, default=8710, help="Port (default: 8710)")
    p_dash.add_argument("--no-browser", action="store_true", help="Don't open browser")
    _add_repo(p_dash)
    p_dash.set_defaults(func=cmd_dashboard)

    # deps
    p_deps = sub.add_parser("deps", help="Dependency freshness checker")
    p_deps.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_deps)
    p_deps.set_defaults(func=cmd_deps)

    # blame  (Session 13)
    p_blame = sub.add_parser("blame", help="Human vs AI attribution")
    _add_json(p_blame)
    _add_repo(p_blame)
    p_blame.set_defaults(func=cmd_blame)

    # security  (Session 13)
    p_sec = sub.add_parser("security", help="Security audit")
    _add_json(p_sec)
    _add_repo(p_sec)
    p_sec.set_defaults(func=cmd_security)

    # deadcode  (Session 13)
    p_dc = sub.add_parser("deadcode", help="Dead code detector")
    _add_json(p_dc)
    _add_repo(p_dc)
    p_dc.set_defaults(func=cmd_deadcode)

    # coveragemap  (Session 13)
    p_cmap = sub.add_parser("coveragemap", help="Coverage heat map")
    _add_json(p_cmap)
    _add_repo(p_cmap)
    p_cmap.set_defaults(func=cmd_coveragemap)

    # maturity  (Session 14)
    p_mat = sub.add_parser("maturity", help="Module maturity scores")
    _add_json(p_mat)
    _add_repo(p_mat)
    p_mat.set_defaults(func=cmd_maturity)

    # dna  (Session 14)
    p_dna = sub.add_parser("dna", help="Repo DNA fingerprint")
    _add_json(p_dna)
    _add_repo(p_dna)
    p_dna.set_defaults(func=cmd_dna)

    # story  (Session 14)
    p_story = sub.add_parser("story", help="Repo narrative")
    _add_json(p_story)
    _add_repo(p_story)
    p_story.set_defaults(func=cmd_story)

    # benchmark  (Session 15)
    p_bench = sub.add_parser("benchmark", help="Performance benchmark suite")
    _add_json(p_bench)
    _add_repo(p_bench)
    p_bench.set_defaults(func=cmd_benchmark)

    # gitstats  (Session 15)
    p_gitstats = sub.add_parser("gitstats", help="Git statistics deep-dive")
    _add_json(p_gitstats)
    _add_repo(p_gitstats)
    p_gitstats.set_defaults(func=cmd_gitstats)

    # badges  (Session 15)
    p_badges = sub.add_parser("badges", help="Badge generator")
    p_badges.add_argument("--write", action="store_true")
    _add_json(p_badges)
    _add_repo(p_badges)
    p_badges.set_defaults(func=cmd_badges)

    # teach  (Session 15)
    p_teach = sub.add_parser("teach", help="Module tutorial generator")
    p_teach.add_argument("module", help="Module name (e.g. health, stats)")
    p_teach.add_argument("--json", action="store_true", help="Output raw JSON")
    _add_repo(p_teach)
    p_teach.set_defaults(func=cmd_teach)

    # audit  (Session 16)
    p_audit = sub.add_parser("audit", help="Comprehensive repo audit")
    _add_json(p_audit)
    _add_repo(p_audit)
    p_audit.set_defaults(func=cmd_audit)

    # semver  (Session 16)
    p_semver = sub.add_parser("semver", help="Semver bump recommender")
    _add_json(p_semver)
    _add_repo(p_semver)
    p_semver.set_defaults(func=cmd_semver)

    # predict  (Session 16)
    p_predict = sub.add_parser("predict", help="Predictive session planner")
    _add_json(p_predict)
    _add_repo(p_predict)
    p_predict.set_defaults(func=cmd_predict)

    # init  (Session 16)
    p_init = sub.add_parser("init", help="Bootstrap project scaffolding")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing files")
    _add_repo(p_init)
    p_init.set_defaults(func=cmd_init)

    # run
    p_run = sub.add_parser("run", help="Full session pipeline")
    p_run.add_argument("--session", type=int, default=1, help="Session number")
    _add_repo(p_run)
    p_run.set_defaults(func=cmd_run)

    # modules  (Session 17)
    p_modules = sub.add_parser("modules", help="Module interconnection graph")
    p_modules.add_argument("--ascii", action="store_true", help="ASCII output instead of Mermaid")
    p_modules.add_argument("--write", action="store_true", help="Write to docs/MODULE_GRAPH.md")
    _add_json(p_modules)
    _add_repo(p_modules)
    p_modules.set_defaults(func=cmd_modules)

    # trends  (Session 17)
    p_trends = sub.add_parser("trends", help="Historical trend data")
    p_trends.add_argument("--write", action="store_true", help="Write to docs/trend_data.json")
    _add_json(p_trends)
    _add_repo(p_trends)
    p_trends.set_defaults(func=cmd_trends)

    # commits  (Session 17)
    p_commits = sub.add_parser("commits", help="Commit message quality analyzer")
    p_commits.add_argument("--top", type=int, default=500, help="Max commits to analyse (default: 500)")
    _add_json(p_commits)
    _add_repo(p_commits)
    p_commits.set_defaults(func=cmd_commits)

    # diff-sessions  (Session 17)
    p_diffsessions = sub.add_parser("diff-sessions", help="Compare two sessions")
    p_diffsessions.add_argument("session_a", help="Session A number")
    p_diffsessions.add_argument("session_b", help="Session B number")
    _add_json(p_diffsessions)
    _add_repo(p_diffsessions)
    p_diffsessions.set_defaults(func=cmd_diff_sessions)

    # test-quality  (Session 17)
    p_testquality = sub.add_parser("test-quality", help="Test quality grader")
    _add_json(p_testquality)
    _add_repo(p_testquality)
    p_testquality.set_defaults(func=cmd_test_quality)

    # report  (Session 17)
    p_report = sub.add_parser("report", help="Executive HTML report")
    p_report.add_argument("--output", default=None, help="Output path (default: docs/report.html)")
    p_report.add_argument("--open", action="store_true", help="Open in browser after generating")
    _add_json(p_report)
    _add_repo(p_report)
    p_report.set_defaults(func=cmd_report, open=True)

    # openapi  (Session 17)
    p_openapi = sub.add_parser("openapi", help="Generate OpenAPI 3.1 spec")
    p_openapi.add_argument("--format", choices=["json", "yaml", "markdown"], default="json")
    p_openapi.add_argument("--write", action="store_true", help="Write to docs/openapi.json")
    _add_json(p_openapi)
    _add_repo(p_openapi)
    p_openapi.set_defaults(func=cmd_openapi)

    # plugins  (Session 17)
    p_plugins = sub.add_parser("plugins", help="Plugin/hook registry")
    p_plugins.add_argument("--example", action="store_true", help="Show example nightshift.toml snippet")
    p_plugins.add_argument("--run", default=None, metavar="HOOK", help="Run all plugins for a hook")
    _add_json(p_plugins)
    _add_repo(p_plugins)
    p_plugins.set_defaults(func=cmd_plugins)

    # pr-score  (alias for score)
    p_prscore = sub.add_parser("pr-score", help="PR quality leaderboard")
    _add_json(p_prscore)
    _add_repo(p_prscore)
    p_prscore.set_defaults(func=cmd_score)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
