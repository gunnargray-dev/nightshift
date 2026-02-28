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
    """Print a formatted section header."""
    bar = "─" * 60
    print(f"\n{bar}")
    print(f"  🌙 Nightshift  ·  {title}")
    print(f"{bar}\n")


def _print_ok(msg: str) -> None:
    """Print a success message."""
    print(f"  ✅  {msg}")


def _print_warn(msg: str) -> None:
    """Print a warning message."""
    print(f"  ⚠️   {msg}")


def _print_info(msg: str) -> None:
    """Print an informational message."""
    print(f"  ·  {msg}")


# ---------------------------------------------------------------------------
# Subcommand: health
# ---------------------------------------------------------------------------


def cmd_health(args: argparse.Namespace) -> int:
    """Analyse code health across src/ and print a summary."""
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
    """Show repository statistics."""
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
    """Visualise the last session's git changes."""
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
    """Generate CHANGELOG.md from git history and optionally write it."""
    from src.changelog import generate_changelog, save_changelog

    _print_header("Changelog")
    repo = _repo(getattr(args, "repo", None))
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
    """Show test coverage trend from stored history."""
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
    """Show PR quality scores from stored leaderboard."""
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
    """Generate or refresh docs/ARCHITECTURE.md."""
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
    """Identify refactor candidates in src/ using health scores."""
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
    """Replay a past session from NIGHTSHIFT_LOG.md."""
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
    """Generate a session plan using Brain module scoring."""
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
    """Run issue triage from a saved JSON export."""
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
    """Visualise the module dependency graph for src/."""
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
    """Hunt stale TODO/FIXME/HACK/XXX annotations across src/."""
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
    """Run full repo health diagnostics — Nightshift's pre-flight check."""
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
    from src.timeline import build_timeline, render_timeline

    _print_header("Session Timeline")
    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"
    timeline = build_timeline(log_path)

    if args.json:
        print(json.dumps(timeline.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "timeline.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_timeline(timeline), encoding="utf-8")
        _print_ok(f"Timeline written to {out}")
        return 0

    print(render_timeline(timeline))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: coupling
# ---------------------------------------------------------------------------


def cmd_coupling(args: argparse.Namespace) -> int:
    """Analyse module coupling (afferent Ca, efferent Ce, instability I)."""
    from src.coupling import build_coupling_report, render_coupling_report

    _print_header("Module Coupling Analyzer")
    repo = _repo(getattr(args, "repo", None))
    report = build_coupling_report(repo / "src")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "coupling_report.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_coupling_report(report), encoding="utf-8")
        _print_ok(f"Coupling report written to {out}")
        return 0

    print(render_coupling_report(report))
    if report.violations:
        _print_warn(f"{len(report.violations)} coupling violation(s) detected")
    else:
        _print_ok("No coupling violations")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: complexity
# ---------------------------------------------------------------------------


def cmd_complexity(args: argparse.Namespace) -> int:
    """Track cyclomatic complexity across src/ and flag hot spots."""
    from src.complexity import build_complexity_report, render_complexity_report

    _print_header("Cyclomatic Complexity Tracker")
    repo = _repo(getattr(args, "repo", None))
    report = build_complexity_report(
        repo / "src",
        threshold=args.threshold,
        session=getattr(args, "session", None),
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "complexity_report.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_complexity_report(report), encoding="utf-8")
        _print_ok(f"Complexity report written to {out}")
        return 0

    print(render_complexity_report(report))
    hot = [f for f in report.functions if f.complexity > args.threshold]
    if hot:
        _print_warn(f"{len(hot)} function(s) exceed complexity threshold {args.threshold}")
    else:
        _print_ok(f"No functions exceed complexity threshold {args.threshold}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: export
# ---------------------------------------------------------------------------


def cmd_export(args: argparse.Namespace) -> int:
    """Export any Nightshift analysis to JSON, Markdown, or HTML."""
    from src.exporter import build_export_bundle, render_export

    _print_header("Analysis Exporter")
    repo = _repo(getattr(args, "repo", None))
    bundle = build_export_bundle(
        repo_path=repo,
        session=getattr(args, "session", None),
        include=args.include.split(",") if args.include else None,
    )

    fmt = args.format.lower() if args.format else "markdown"
    output = render_export(bundle, fmt)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        _print_ok(f"Export written to {out_path}")
        return 0

    print(output)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: config
# ---------------------------------------------------------------------------


def cmd_config(args: argparse.Namespace) -> int:
    """Show or write nightshift.toml config."""
    from src.config import load_config, render_config, write_default_config

    _print_header("Nightshift Config")
    repo = _repo(getattr(args, "repo", None))

    if args.write:
        out = repo / "nightshift.toml"
        write_default_config(out)
        _print_ok(f"Default config written to {out}")
        return 0

    config = load_config(repo)
    if args.json:
        print(json.dumps(config.to_dict(), indent=2, default=str))
        return 0

    print(render_config(config))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: compare
# ---------------------------------------------------------------------------


def cmd_compare(args: argparse.Namespace) -> int:
    """Diff two Nightshift sessions side-by-side."""
    from src.compare import build_comparison, render_comparison

    _print_header(f"Session Comparison — Session {args.session_a} vs {args.session_b}")
    repo = _repo(getattr(args, "repo", None))
    comparison = build_comparison(
        repo_path=repo,
        session_a=args.session_a,
        session_b=args.session_b,
    )

    if args.json:
        print(json.dumps(comparison.to_dict(), indent=2, default=str))
        return 0

    print(render_comparison(comparison))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: dashboard
# ---------------------------------------------------------------------------


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Launch the live React dashboard API server."""
    from src.server import start_server

    repo = _repo(getattr(args, "repo", None))
    _print_header("Dashboard")
    _print_info(f"Starting API server on port {args.port}...")
    start_server(port=args.port, repo_path=repo)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: deps
# ---------------------------------------------------------------------------


def cmd_deps(args: argparse.Namespace) -> int:
    """Check Python dependency freshness via PyPI."""
    from src.deps_checker import check_freshness
    _print_header("Dependency Freshness")
    repo = _repo(getattr(args, "repo", None))
    report = check_freshness(repo_path=repo, offline=getattr(args, "offline", False))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    if report.outdated_count > 0:
        _print_warn(f"{report.outdated_count} package(s) have newer versions available")
    elif report.packages:
        _print_ok("All packages are up to date")
    else:
        _print_info("No packages found in dependency files")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: run (full pipeline)
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Run the full end-of-session Nightshift pipeline."""
    _print_header("Full Session Pipeline")
    repo = _repo(getattr(args, "repo", None))
    session = getattr(args, "session", 4)
    errors: list[str] = []
    try:
        from src.health import generate_health_report, save_health_report
        report = generate_health_report(repo_path=repo)
        out = repo / "docs" / "health_report.md"
        out.parent.mkdir(exist_ok=True)
        save_health_report(report, out)
        _print_ok(f"Health report ➒ {out}  (score: {report.overall_health_score}/100)")
    except Exception as exc:
        errors.append(f"health: {exc}")
        _print_warn(f"Health analysis failed: {exc}")

    try:
        from src.stats import compute_stats, update_readme_stats
        stats = compute_stats(repo_path=repo, log_path=repo / "NIGHTSHIFT_LOG.md")
        readme_path = repo / "README.md"
        if readme_path.exists():
            new_content = update_readme_stats(readme_path, stats)
            readme_path.write_text(new_content, encoding="utf-8")
            _print_ok(f"README stats updated  (nights: {stats.nights_active}, PRs: {stats.total_prs})")
    except Exception as exc:
        errors.append(f"stats: {exc}")
        _print_warn(f"Stats update failed: {exc}")

    try:
        from src.changelog import generate_changelog, save_changelog
        cl = generate_changelog(repo_path=repo)
        save_changelog(cl, repo / "CHANGELOG.md")
        total = sum(s.total_commits() for s in cl.sections)
        _print_ok(f"CHANGELOG.md updated  ({total} commits across {len(cl.sections)} sessions)")
    except Exception as exc:
        errors.append(f"changelog: {exc}")
        _print_warn(f"Changelog failed: {exc}")

    try:
        from src.arch_generator import generate_architecture_doc, save_architecture_doc
        doc = generate_architecture_doc(repo_path=repo)
        save_architecture_doc(doc, repo / "docs" / "ARCHITECTURE.md")
        _print_ok("docs/ARCHITECTURE.md refreshed")
    except Exception as exc:
        _print_info(f"arch_generator not available: {exc}")

    try:
        from src.refactor import RefactorEngine
        engine = RefactorEngine(repo_path=repo)
        ref_report = engine.analyze()
        out = repo / "docs" / "refactor_report.md"
        out.write_text(ref_report.to_markdown(), encoding="utf-8")
        _print_ok(f"Refactor report ➒ {out}  ({ref_report.total_suggestions} suggestions)")
    except Exception as exc:
        _print_info(f"refactor module not available: {exc}")

    print()
    if errors:
        _print_warn(f"Pipeline completed with {len(errors)} error(s):")
        for e in errors:
            _print_info(f"  {e}")
        return 1

    _print_ok("Pipeline complete.")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: blame
# ---------------------------------------------------------------------------


def cmd_blame(args: argparse.Namespace) -> int:
    """Attribute lines of code to human vs AI contributions via git blame."""
    from src.blame import build_blame_report, render_blame_report

    _print_header("Human vs AI Blame Attribution")
    repo = _repo(getattr(args, "repo", None))
    report = build_blame_report(repo)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "blame_report.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_blame_report(report), encoding="utf-8")
        _print_ok(f"Blame report written to {out}")
        return 0

    print(render_blame_report(report))
    _print_info(f"Human: {report.human_pct:.1f}%  AI: {report.ai_pct:.1f}%")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: deadcode
# ---------------------------------------------------------------------------


def cmd_deadcode(args: argparse.Namespace) -> int:
    """Detect unused functions and imports across src/."""
    from src.deadcode import build_deadcode_report, render_deadcode_report

    _print_header("Dead Code Detector")
    repo = _repo(getattr(args, "repo", None))
    report = build_deadcode_report(repo / "src")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "deadcode_report.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_deadcode_report(report), encoding="utf-8")
        _print_ok(f"Dead code report written to {out}")
        return 0

    print(render_deadcode_report(report))
    if report.dead_count > 0:
        _print_warn(f"{report.dead_count} unused symbol(s) found")
    else:
        _print_ok("No unused symbols detected")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: security
# ---------------------------------------------------------------------------


def cmd_security(args: argparse.Namespace) -> int:
    """Audit src/ for common Python security anti-patterns."""
    from src.security import build_security_report, render_security_report

    _print_header("Security Audit")
    repo = _repo(getattr(args, "repo", None))
    report = build_security_report(repo / "src")

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "security_report.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_security_report(report), encoding="utf-8")
        _print_ok(f"Security report written to {out}")
        return 0

    print(render_security_report(report))
    if report.critical_count > 0:
        _print_warn(f"{report.critical_count} critical issue(s) found")
    elif report.issue_count > 0:
        _print_warn(f"{report.issue_count} security issue(s) found")
    else:
        _print_ok("No security issues detected")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: coveragemap
# ---------------------------------------------------------------------------


def cmd_coveragemap(args: argparse.Namespace) -> int:
    """Show a test coverage heat map ranked by weakest modules."""
    from src.coveragemap import build_coverage_map, render_coverage_map

    _print_header("Test Coverage Heat Map")
    repo = _repo(getattr(args, "repo", None))
    cmap = build_coverage_map(repo)

    if args.json:
        print(json.dumps(cmap.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "coverage_map.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_coverage_map(cmap), encoding="utf-8")
        _print_ok(f"Coverage map written to {out}")
        return 0

    print(render_coverage_map(cmap))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: story
# ---------------------------------------------------------------------------


def cmd_story(args: argparse.Namespace) -> int:
    """Generate a narrative prose summary of the repo's evolution."""
    from src.story import build_story, render_story

    _print_header("Repo Story")
    repo = _repo(getattr(args, "repo", None))
    story = build_story(repo)

    if args.json:
        print(json.dumps(story.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "story.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_story(story), encoding="utf-8")
        _print_ok(f"Story written to {out}")
        return 0

    print(render_story(story))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: maturity
# ---------------------------------------------------------------------------


def cmd_maturity(args: argparse.Namespace) -> int:
    """Score each module's maturity across five dimensions."""
    from src.maturity import build_maturity_report, render_maturity_report

    _print_header("Module Maturity Scorecard")
    repo = _repo(getattr(args, "repo", None))
    report = build_maturity_report(repo)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "maturity_report.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_maturity_report(report), encoding="utf-8")
        _print_ok(f"Maturity report written to {out}")
        return 0

    print(render_maturity_report(report))
    _print_info(f"Average maturity: {report.average_score:.1f}/100")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: teach
# ---------------------------------------------------------------------------


def cmd_teach(args: argparse.Namespace) -> int:
    """Generate a tutorial explaining how a specific module works."""
    from src.teach import build_tutorial, render_tutorial

    _print_header(f"Module Tutorial — {args.module}")
    repo = _repo(getattr(args, "repo", None))
    tutorial = build_tutorial(repo, module=args.module, depth=args.depth)

    if args.json:
        print(json.dumps(tutorial.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / f"tutorial_{args.module}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_tutorial(tutorial), encoding="utf-8")
        _print_ok(f"Tutorial written to {out}")
        return 0

    print(render_tutorial(tutorial))
    return 0


# ---------------------------------------------------------------------------
# Subcommand: dna
# ---------------------------------------------------------------------------


def cmd_dna(args: argparse.Namespace) -> int:
    """Print the repo's DNA fingerprint — a unique visual signature."""
    from src.dna import build_dna, render_dna

    _print_header("Repo DNA Fingerprint")
    repo = _repo(getattr(args, "repo", None))
    dna = build_dna(repo)

    if args.json:
        print(json.dumps(dna.to_dict(), indent=2, default=str))
        return 0

    if args.write:
        out = repo / "docs" / "dna.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(render_dna(dna), encoding="utf-8")
        _print_ok(f"DNA written to {out}")
        return 0

    print(render_dna(dna))
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="nightshift",
        description="🌙 Nightshift — autonomous dev system CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nightshift health                  # health score for src/
  nightshift stats                   # repo stats table
  nightshift changelog --write       # regenerate CHANGELOG.md
  nightshift run --session 4         # full end-of-session pipeline
  nightshift refactor --apply        # apply safe auto-fixes
        """,
    )
    parser.add_argument(
        "--repo",
        metavar="PATH",
        help="Path to repo root (default: auto-detected)",
    )

    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.required = True

    # health
    p_health = sub.add_parser("health", help="Code health analysis")
    p_health.add_argument("--json", action="store_true", help="Output raw JSON")
    p_health.set_defaults(func=cmd_health)

    # stats
    p_stats = sub.add_parser("stats", help="Repository statistics")
    p_stats.add_argument("--json", action="store_true", help="Output raw JSON")
    p_stats.set_defaults(func=cmd_stats)

    # diff
    p_diff = sub.add_parser("diff", help="Session diff visualiser")
    p_diff.add_argument(
        "--session", type=int, default=4, help="Session number to diff (default: 4)"
    )
    p_diff.add_argument("--json", action="store_true", help="Output raw JSON")
    p_diff.set_defaults(func=cmd_diff)

    # changelog
    p_cl = sub.add_parser("changelog", help="Generate CHANGELOG.md")
    p_cl.add_argument("--write", action="store_true", help="Write to CHANGELOG.md")
    p_cl.add_argument("--json", action="store_true", help="Output raw JSON")
    p_cl.set_defaults(func=cmd_changelog)

    # coverage
    p_cov = sub.add_parser("coverage", help="Test coverage trend")
    p_cov.add_argument("--json", action="store_true", help="Output raw JSON")
    p_cov.set_defaults(func=cmd_coverage)

    # score
    p_score = sub.add_parser("score", help="PR quality leaderboard")
    p_score.add_argument("--json", action="store_true", help="Output raw JSON")
    p_score.set_defaults(func=cmd_score)

    # arch
    p_arch = sub.add_parser("arch", help="Architecture doc generator")
    p_arch.add_argument("--write", action="store_true", help="Write to docs/ARCHITECTURE.md")
    p_arch.set_defaults(func=cmd_arch)

    # refactor
    p_ref = sub.add_parser("refactor", help="Self-refactor engine")
    p_ref.add_argument("--apply", action="store_true", help="Apply safe auto-fixes")
    p_ref.add_argument("--json", action="store_true", help="Output raw JSON")
    p_ref.set_defaults(func=cmd_refactor)

    # replay
    p_replay = sub.add_parser("replay", help="Session replay")
    p_replay.add_argument("--session", type=int, default=None, help="Session number (omit for all)")
    p_replay.add_argument("--json", action="store_true", help="Output raw JSON")
    p_replay.set_defaults(func=cmd_replay)

    # plan
    p_plan = sub.add_parser("plan", help="Session planning")
    p_plan.add_argument("--session", type=int, default=1, help="Session number to plan")
    p_plan.add_argument("--json", action="store_true", help="Output raw JSON")
    p_plan.set_defaults(func=cmd_plan)

    # triage
    p_triage = sub.add_parser("triage", help="Issue triage")
    p_triage.add_argument("--issues", metavar="FILE", help="Path to issues JSON export")
    p_triage.add_argument("--json", action="store_true", help="Output raw JSON")
    p_triage.set_defaults(func=cmd_triage)

    # depgraph
    p_depgraph = sub.add_parser("depgraph", help="Module dependency graph")
    p_depgraph.add_argument("--write", action="store_true", help="Write to docs/dep_graph.md")
    p_depgraph.add_argument("--json", action="store_true", help="Output raw JSON")
    p_depgraph.set_defaults(func=cmd_depgraph)

    # todos
    p_todos = sub.add_parser("todos", help="TODO/FIXME hunter")
    p_todos.add_argument("--session", type=int, default=None, help="Current session number")
    p_todos.add_argument("--threshold", type=int, default=3, help="Sessions before stale")
    p_todos.add_argument("--write", action="store_true", help="Write report to docs/todo_report.md")
    p_todos.add_argument("--json", action="store_true", help="Output raw JSON")
    p_todos.set_defaults(func=cmd_todos)

    # doctor
    p_doctor = sub.add_parser("doctor", help="Full repo health diagnostic")
    p_doctor.add_argument("--write", action="store_true", help="Write report to docs/doctor_report.md")
    p_doctor.add_argument("--json", action="store_true", help="Output raw JSON")
    p_doctor.set_defaults(func=cmd_doctor)

    # timeline
    p_timeline = sub.add_parser("timeline", help="Session timeline visualiser")
    p_timeline.add_argument("--write", action="store_true", help="Write to docs/timeline.md")
    p_timeline.add_argument("--json", action="store_true", help="Output raw JSON")
    p_timeline.set_defaults(func=cmd_timeline)

    # coupling
    p_coupling = sub.add_parser("coupling", help="Module coupling analyzer (Session 11)")
    p_coupling.add_argument("--write", action="store_true", help="Write to docs/coupling_report.md")
    p_coupling.add_argument("--json", action="store_true", help="Output raw JSON")
    p_coupling.set_defaults(func=cmd_coupling)

    # complexity
    p_complexity = sub.add_parser("complexity", help="Cyclomatic complexity tracker (Session 11)")
    p_complexity.add_argument("--threshold", type=int, default=10, help="Complexity threshold (default: 10)")
    p_complexity.add_argument("--session", type=int, default=None, help="Session number for history tracking")
    p_complexity.add_argument("--write", action="store_true", help="Write to docs/complexity_report.md")
    p_complexity.add_argument("--json", action="store_true", help="Output raw JSON")
    p_complexity.set_defaults(func=cmd_complexity)

    # export
    p_export = sub.add_parser("export", help="Export analysis to JSON/Markdown/HTML (Session 11)")
    p_export.add_argument("--format", choices=["json", "markdown", "html"], default="markdown", help="Output format")
    p_export.add_argument("--out", metavar="FILE", help="Output file path")
    p_export.add_argument("--session", type=int, default=None, help="Session number")
    p_export.add_argument("--include", metavar="LIST", help="Comma-separated list of analyses to include")
    p_export.set_defaults(func=cmd_export)

    # config
    p_config = sub.add_parser("config", help="Show or write nightshift.toml config")
    p_config.add_argument("--write", action="store_true", help="Write default config to nightshift.toml")
    p_config.add_argument("--json", action="store_true", help="Output raw JSON")
    p_config.set_defaults(func=cmd_config)

    # compare
    p_compare = sub.add_parser("compare", help="Diff two sessions side-by-side")
    p_compare.add_argument("session_a", type=int, help="First session number")
    p_compare.add_argument("session_b", type=int, help="Second session number")
    p_compare.add_argument("--json", action="store_true", help="Output raw JSON")
    p_compare.set_defaults(func=cmd_compare)

    # dashboard
    p_dashboard = sub.add_parser("dashboard", help="Launch live React dashboard")
    p_dashboard.add_argument("--port", type=int, default=8710, help="API server port (default: 8710)")
    p_dashboard.set_defaults(func=cmd_dashboard)

    p_deps = sub.add_parser("deps", help="Check Python dependency freshness via PyPI")
    p_deps.add_argument("--offline", action="store_true", help="Skip PyPI queries")
    p_deps.add_argument("--json", action="store_true", help="Output raw JSON")
    p_deps.set_defaults(func=cmd_deps)

    # run
    p_run = sub.add_parser("run", help="Run the full end-of-session pipeline")
    p_run.add_argument(
        "--session", type=int, default=4, help="Session number (default: 4)"
    )
    p_run.set_defaults(func=cmd_run)

    # blame
    p_blame = sub.add_parser("blame", help="Human vs AI contribution attribution")
    p_blame.add_argument("--json", action="store_true", help="Output raw JSON")
    p_blame.add_argument("--write", action="store_true", help="Write to docs/blame_report.md")
    p_blame.set_defaults(func=cmd_blame)

    # deadcode
    p_deadcode = sub.add_parser("deadcode", help="Dead code detector (unused functions/imports)")
    p_deadcode.add_argument("--json", action="store_true", help="Output raw JSON")
    p_deadcode.add_argument("--write", action="store_true", help="Write to docs/deadcode_report.md")
    p_deadcode.set_defaults(func=cmd_deadcode)

    # security
    p_security = sub.add_parser("security", help="Security audit — common Python anti-patterns")
    p_security.add_argument("--json", action="store_true", help="Output raw JSON")
    p_security.add_argument("--write", action="store_true", help="Write to docs/security_report.md")
    p_security.set_defaults(func=cmd_security)

    # coveragemap
    p_coveragemap = sub.add_parser("coveragemap", help="Test coverage heat map by module")
    p_coveragemap.add_argument("--json", action="store_true", help="Output raw JSON")
    p_coveragemap.add_argument("--write", action="store_true", help="Write to docs/coverage_map.md")
    p_coveragemap.set_defaults(func=cmd_coveragemap)

    # story
    p_story = sub.add_parser("story", help="Narrative prose summary of the repo's evolution")
    p_story.add_argument("--json", action="store_true", help="Output raw JSON")
    p_story.add_argument("--write", action="store_true", help="Write to docs/story.md")
    p_story.set_defaults(func=cmd_story)

    # maturity
    p_maturity = sub.add_parser("maturity", help="Score each module's maturity (tests/docs/complexity/age/coupling)")
    p_maturity.add_argument("--json", action="store_true", help="Output raw JSON")
    p_maturity.add_argument("--write", action="store_true", help="Write to docs/maturity_report.md")
    p_maturity.set_defaults(func=cmd_maturity)

    # teach
    p_teach = sub.add_parser("teach", help="Generate a tutorial for a specific module")
    p_teach.add_argument("module", help="Module name (e.g. health, stats, cli)")
    p_teach.add_argument("--depth", type=int, default=2, help="Tutorial depth (1-3, default: 2)")
    p_teach.add_argument("--json", action="store_true", help="Output raw JSON")
    p_teach.add_argument("--write", action="store_true", help="Write to docs/tutorial_<module>.md")
    p_teach.set_defaults(func=cmd_teach)

    # dna
    p_dna = sub.add_parser("dna", help="Repo DNA fingerprint — unique visual signature of codebase")
    p_dna.add_argument("--json", action="store_true", help="Output raw JSON")
    p_dna.add_argument("--write", action="store_true", help="Write to docs/dna.md")
    p_dna.set_defaults(func=cmd_dna)

    return parser



def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())


