"""Unified CLI entry point for Nightshift.

Provides a single ``nightshift`` command that ties together all 8 analysis
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
nightshift triage      — Run issue triage (from docs/issues.json)
nightshift plan        — Rank roadmap tasks for next session (Brain)
nightshift replay      — Reconstruct a past session from NIGHTSHIFT_LOG.md

Usage
-----
    python -m nightshift.cli <command> [options]
    # or after ``pip install -e .``:
    nightshift <command> [options]
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
# Subcommand: triage
# ---------------------------------------------------------------------------


def cmd_triage(args: argparse.Namespace) -> int:
    """Run issue triage from a JSON export and print a ranked list."""
    from src.issue_triage import load_issues_from_file, triage_issues

    _print_header("Issue Triage")
    repo = _repo(getattr(args, "repo", None))
    issues_path = (repo / "docs" / "issues.json") if not args.issues else Path(args.issues)

    if not issues_path.exists():
        _print_warn(f"No issues file found at {issues_path}")
        _print_info("Export GitHub issues to JSON and pass --issues PATH (or commit docs/issues.json).")
        return 1

    raw = load_issues_from_file(issues_path)
    report = triage_issues(raw)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    print(report.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: plan
# ---------------------------------------------------------------------------


def cmd_plan(args: argparse.Namespace) -> int:
    """Plan a future session by ranking candidate tasks."""
    from src.brain import Brain

    _print_header(f"Session Plan — Session {args.session}")
    repo = _repo(getattr(args, "repo", None))
    brain = Brain(repo_path=repo)
    plan = brain.plan(session_number=args.session)

    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    print(plan.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: replay
# ---------------------------------------------------------------------------


def cmd_replay(args: argparse.Namespace) -> int:
    """Reconstruct a past session from NIGHTSHIFT_LOG.md."""
    from src.session_replay import replay

    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"

    _print_header(f"Session Replay — Session {args.session}")

    r = replay(log_path=log_path, session_number=args.session)
    if not r:
        _print_warn(f"Session {args.session} not found in {log_path}")
        return 1

    if args.json:
        print(json.dumps(r.to_dict(), indent=2))
        return 0

    print(r.to_markdown())
    return 0


# ---------------------------------------------------------------------------
# Subcommand: run (full pipeline)
# ---------------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Run the full end-of-session Nightshift pipeline.

    Executes in order:
      1. Code health analysis
      2. Test coverage measurement
      3. Changelog generation
      4. README stats update
      5. Refactor report
      6. Architecture doc refresh
    """
    _print_header("Full Session Pipeline")
    repo = _repo(getattr(args, "repo", None))
    session = getattr(args, "session", 4)
    errors: list[str] = []

    # 1. Health
    try:
        from src.health import generate_health_report, save_health_report
        report = generate_health_report(repo_path=repo)
        out = repo / "docs" / "health_report.md"
        out.parent.mkdir(exist_ok=True)
        save_health_report(report, out)
        _print_ok(f"Health report → {out}  (score: {report.overall_health_score}/100)")
    except Exception as exc:
        errors.append(f"health: {exc}")
        _print_warn(f"Health analysis failed: {exc}")

    # 2. Stats
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

    # 3. Changelog
    try:
        from src.changelog import generate_changelog, save_changelog
        cl = generate_changelog(repo_path=repo)
        save_changelog(cl, repo / "CHANGELOG.md")
        total = sum(s.total_commits() for s in cl.sections)
        _print_ok(f"CHANGELOG.md updated  ({total} commits across {len(cl.sections)} sessions)")
    except Exception as exc:
        errors.append(f"changelog: {exc}")
        _print_warn(f"Changelog failed: {exc}")

    # 4. Architecture doc
    try:
        from src.arch_generator import generate_architecture_doc, save_architecture_doc
        doc = generate_architecture_doc(repo_path=repo)
        save_architecture_doc(doc, repo / "docs" / "ARCHITECTURE.md")
        _print_ok("docs/ARCHITECTURE.md refreshed")
    except Exception as exc:
        _print_info(f"arch_generator not available: {exc}")

    # 5. Refactor report
    try:
        from src.refactor import RefactorEngine
        engine = RefactorEngine(repo_path=repo)
        ref_report = engine.analyze()
        out = repo / "docs" / "refactor_report.md"
        out.write_text(ref_report.to_markdown(), encoding="utf-8")
        _print_ok(f"Refactor report → {out}  ({ref_report.total_suggestions} suggestions)")
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
  nightshift health              # health score for src/
  nightshift stats               # repo stats table
  nightshift changelog --write   # regenerate CHANGELOG.md
a  nightshift replay --session 3 # reconstruct a past session
  nightshift plan --session 6    # rank tasks for an upcoming session
  nightshift run --session 4     # full end-of-session pipeline
  nightshift refactor --apply    # apply safe auto-fixes
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
    p_arch = sub.add_parser("arch", help="Generate docs/ARCHITECTURE.md")
    p_arch.add_argument("--write", action="store_true", help="Write to docs/ARCHITECTURE.md")
    p_arch.set_defaults(func=cmd_arch)

    # refactor
    p_ref = sub.add_parser("refactor", help="Self-refactor engine")
    p_ref.add_argument("--apply", action="store_true", help="Apply safe auto-fixes")
    p_ref.add_argument("--json", action="store_true", help="Output raw JSON")
    p_ref.set_defaults(func=cmd_refactor)

    # triage
    p_triage = sub.add_parser("triage", help="Issue triage (from docs/issues.json)")
    p_triage.add_argument("--issues", help="Path to issues JSON export (default: docs/issues.json)")
    p_triage.add_argument("--json", action="store_true", help="Output raw JSON")
    p_triage.set_defaults(func=cmd_triage)

    # plan
    p_plan = sub.add_parser("plan", help="Plan a session by ranking tasks (Brain)")
    p_plan.add_argument("--session", type=int, default=6, help="Future session number (default: 6)")
    p_plan.add_argument("--json", action="store_true", help="Output raw JSON")
    p_plan.set_defaults(func=cmd_plan)

    # replay
    p_replay = sub.add_parser("replay", help="Replay a past session from NIGHTSHIFT_LOG.md")
    p_replay.add_argument("--session", type=int, required=True, help="Session number to replay")
    p_replay.add_argument("--json", action="store_true", help="Output raw JSON")
    p_replay.set_defaults(func=cmd_replay)

    # run
    p_run = sub.add_parser("run", help="Full end-of-session pipeline")
    p_run.add_argument(
        "--session", type=int, default=4, help="Current session number (default: 4)"
    )
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as exc:  # noqa: BLE001
        print(f"\n❌ Error: {exc}", file=sys.stderr)
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
