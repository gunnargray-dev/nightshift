"""Tools command group for Nightshift CLI.

Commands: doctor, todos, benchmark, gitstats, badges, audit, predict, teach,
dna, report, export, coverage, score, test_quality, refactor, commits,
semver, openapi, modules, trends, plan (brain), triage, depgraph, arch.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.commands import _repo, _print_header, _print_ok, _print_warn, _print_info


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


def cmd_doctor(args) -> int:
    """Run full repo health diagnostic."""
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
# todos
# ---------------------------------------------------------------------------


def cmd_todos(args) -> int:
    """Hunt stale TODO/FIXME annotations."""
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
# benchmark
# ---------------------------------------------------------------------------


def cmd_benchmark(args) -> int:
    """Run the performance benchmark suite."""
    from src.benchmark import run_benchmarks, save_benchmark_report
    _print_header("Performance Benchmark Suite")
    repo = _repo(getattr(args, "repo", None))
    report = run_benchmarks(repo)
    if args.write:
        out = repo / "docs" / "benchmark_report.md"
        save_benchmark_report(report, out)
        _print_ok(f"Report written to {out}")
        return 0
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
# gitstats
# ---------------------------------------------------------------------------


def cmd_gitstats(args) -> int:
    """Git statistics deep-dive: churn, velocity, commit frequency."""
    from src.gitstats import compute_git_stats, save_git_stats_report
    _print_header("Git Statistics Deep-Dive")
    repo = _repo(getattr(args, "repo", None))
    report = compute_git_stats(repo)
    if args.write:
        out = repo / "docs" / "gitstats_report.md"
        save_git_stats_report(report, out)
        _print_ok(f"Report written to {out}")
        return 0
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
# badges
# ---------------------------------------------------------------------------


def cmd_badges(args) -> int:
    """Generate Shields.io badge metadata from live metrics."""
    from src.badges import generate_badges
    _print_header("Badge Generator")
    repo = _repo(getattr(args, "repo", None))
    report = generate_badges(repo)
    if args.inject:
        from src.badges import write_badges_to_readme
        ok = write_badges_to_readme(report, repo / "README.md")
        if ok:
            _print_ok("Badges injected into README.md")
        else:
            _print_warn("Could not inject badges into README.md")
        return 0
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
# audit
# ---------------------------------------------------------------------------


def cmd_audit(args) -> int:
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
# predict
# ---------------------------------------------------------------------------


def cmd_predict(args) -> int:
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
# teach
# ---------------------------------------------------------------------------


def cmd_teach(args) -> int:
    """Generate an AST-based tutorial for a specific module."""
    from src.teach import teach_module, list_teachable_modules, save_tutorial
    repo = _repo(getattr(args, "repo", None))
    if args.module == "list":
        _print_header("Teachable Modules")
        modules = list_teachable_modules(repo)
        for m in modules:
            print(f"  {m}")
        return 0
    _print_header(f"Module Tutorial: {args.module}")
    try:
        tutorial = teach_module(args.module, repo)
    except FileNotFoundError as e:
        print(str(e))
        return 1
    if args.write:
        out = repo / "docs" / "tutorials" / f"{args.module}.md"
        save_tutorial(tutorial, out)
        _print_ok(f"Tutorial written to {out}")
        return 0
    if args.json:
        print(json.dumps(tutorial.to_dict(), indent=2))
        return 0
    print(tutorial.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# dna
# ---------------------------------------------------------------------------


def cmd_dna(args) -> int:
    """Generate 6-channel visual repo DNA fingerprint."""
    from src.dna import fingerprint_repo, save_dna_report
    _print_header("Repo DNA Fingerprint")
    repo = _repo(getattr(args, "repo", None))
    dna = fingerprint_repo(repo)
    if args.write:
        out = repo / "docs" / "dna.md"
        save_dna_report(dna, out)
        _print_ok(f"DNA report written to {out}")
        return 0
    if args.json:
        print(json.dumps(dna.to_dict(), indent=2))
        return 0
    print(dna.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def cmd_report(args) -> int:
    """Generate executive HTML report combining all analyses."""
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
# export
# ---------------------------------------------------------------------------


def cmd_export(args) -> int:
    """Export any analysis output to JSON, Markdown, or HTML."""
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
# coverage (coverage trend)
# ---------------------------------------------------------------------------


def cmd_coverage(args) -> int:
    """Show test coverage trend."""
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
# score (PR quality leaderboard)
# ---------------------------------------------------------------------------


def cmd_score(args) -> int:
    """Show PR quality leaderboard."""
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
# test-quality
# ---------------------------------------------------------------------------


def cmd_test_quality(args) -> int:
    """Grade tests by assertion density and edge coverage."""
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
# refactor
# ---------------------------------------------------------------------------


def cmd_refactor(args) -> int:
    """Self-refactor engine: identify and optionally apply safe fixes."""
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
# commits
# ---------------------------------------------------------------------------


def cmd_commits(args) -> int:
    """Smart commit message quality analyzer."""
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
# semver
# ---------------------------------------------------------------------------


def cmd_semver(args) -> int:
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
# modules
# ---------------------------------------------------------------------------


def cmd_modules(args) -> int:
    """Module interconnection graph (Mermaid or ASCII)."""
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
# trends
# ---------------------------------------------------------------------------


def cmd_trends(args) -> int:
    """Historical trend data for dashboards."""
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
# plan / brain
# ---------------------------------------------------------------------------


def cmd_plan(args) -> int:
    """Session task planner."""
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
# triage
# ---------------------------------------------------------------------------


def cmd_triage(args) -> int:
    """Issue triage and prioritization."""
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
# depgraph
# ---------------------------------------------------------------------------


def cmd_depgraph(args) -> int:
    """Visualise module dependency graph."""
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
# arch
# ---------------------------------------------------------------------------


def cmd_arch(args) -> int:
    """Architecture doc generator."""
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
