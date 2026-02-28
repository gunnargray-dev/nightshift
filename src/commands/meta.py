"""Meta/introspection command group for Nightshift CLI.

Commands: stats, changelog, story, reflect, evolve, status, session_score,
timeline, replay, compare, diff, diff_sessions.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.commands import _repo, _print_header, _print_ok, _print_warn, _print_info


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def cmd_stats(args) -> int:
    """Show repo stats (commits, PRs, lines changed)."""
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
# changelog
# ---------------------------------------------------------------------------


def cmd_changelog(args) -> int:
    """Render CHANGELOG.md from git history."""
    from src.changelog import generate_changelog, save_changelog
    _print_header("Changelog")
    repo = _repo(getattr(args, "repo", None))
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
# story
# ---------------------------------------------------------------------------


def cmd_story(args) -> int:
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
# reflect
# ---------------------------------------------------------------------------


def cmd_reflect(args) -> int:
    """Analyze all past sessions and produce meta-insights."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from reflect import generate_reflection, format_reflection, reflect_to_json, save_reflection

    report = generate_reflection()
    if args.json:
        print(reflect_to_json(report))
        return 0
    print(format_reflection(report))
    if getattr(args, "write", False):
        out = _repo(getattr(args, "repo", None)) / "docs" / "reflect.md"
        save_reflection(report, out)
        print(f"\nSaved to {out}")
    return 0


# ---------------------------------------------------------------------------
# evolve
# ---------------------------------------------------------------------------


def cmd_evolve(args) -> int:
    """Generate gap analysis and evolution proposals."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from evolve import generate_evolution, format_evolution, evolve_to_json, save_evolution

    report = generate_evolution()
    if args.json:
        print(evolve_to_json(report))
        return 0
    tier = getattr(args, "tier", None)
    if tier:
        tier_map = {1: report.tier1, 2: report.tier2, 3: report.tier3}
        proposals = tier_map.get(tier, report.proposals)
        print(f"TIER {tier} PROPOSALS")
        print("=" * 60)
        for p in proposals:
            print(f"\n  [{p.category}] {p.title}")
            print(f"  {p.description[:200]}")
            print(f"  Command: {p.example_command}")
        return 0
    print(format_evolution(report))
    if getattr(args, "write", False):
        out = _repo(getattr(args, "repo", None)) / "docs" / "evolve.md"
        save_evolution(report, out)
        print(f"\nSaved to {out}")
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_status(args) -> int:
    """Show comprehensive at-a-glance status of the repo."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from status import generate_status, format_status, status_to_json

    report = generate_status(_repo(getattr(args, "repo", None)))
    if args.json:
        print(status_to_json(report))
        return 0
    if getattr(args, "brief", False):
        print(report.summary)
        return 0
    print(format_status(report))
    return 0


# ---------------------------------------------------------------------------
# session_score
# ---------------------------------------------------------------------------


def cmd_session_score(args) -> int:
    """Score a session on five quality dimensions."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from session_scorer import (
        score_session, score_all_sessions,
        format_session_score, session_score_to_json, SESSION_DATA,
    )

    if getattr(args, "all", False):
        scores = score_all_sessions()
        if args.json:
            print(json.dumps(
                [{"session": s.session, "total": s.total, "grade": s.grade} for s in scores],
                indent=2,
            ))
            return 0
        for s in sorted(scores, key=lambda x: x.total, reverse=True):
            print(f"  S{s.session:>2}  {s.grade:>3}  {s.total:>5.1f}/100")
        return 0

    session_num = getattr(args, "session", None) or 18
    row = next((r for r in SESSION_DATA if r[0] == session_num), None)
    if row is None:
        print(f"No data for session {session_num}. Use --all to see all sessions.")
        return 1

    _, features, tests, cli, api, health = row
    score = score_session(session_num, features, tests, cli, api, health)
    if args.json:
        print(session_score_to_json(score))
        return 0
    print(format_session_score(score))
    return 0


# ---------------------------------------------------------------------------
# timeline
# ---------------------------------------------------------------------------


def cmd_timeline(args) -> int:
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
# replay
# ---------------------------------------------------------------------------


def cmd_replay(args) -> int:
    """Replay a past Nightshift session from the log."""
    from src.session_replay import replay, replay_all
    _print_header("Session Replay")
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
# compare
# ---------------------------------------------------------------------------


def cmd_compare(args) -> int:
    """Compare two sessions side-by-side."""
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
# diff
# ---------------------------------------------------------------------------


def cmd_diff(args) -> int:
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
# diff-sessions
# ---------------------------------------------------------------------------


def cmd_diff_sessions(args) -> int:
    """Compare any two sessions with rich delta analysis."""
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
