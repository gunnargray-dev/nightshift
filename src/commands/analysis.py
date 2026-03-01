"""Analysis command handlers for the Awake CLI.

Each function in this module corresponds to one `awake <subcommand>` that
performs repo analysis.  Functions follow the signature::

    def cmd_<name>(argv: list[str]) -> int: ...

Return 0 on success, non-zero on error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def cmd_health(argv: list[str]) -> int:
    """Run health analysis on all src/ modules.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.health import analyze_repo

    parser = argparse.ArgumentParser(prog="awake health")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--path", default=".", help="Repo root (default: .)")
    args = parser.parse_args(argv)

    results = analyze_repo(Path(args.path))
    if args.json:
        print(json.dumps({"files": results}, indent=2))
    else:
        _print_health_table(results)
    return 0


def _print_health_table(results: list[dict]) -> None:
    """Print health results as a formatted table."""
    print(f"{'Module':<40} {'Score':>7} {'Long':>5} {'TODO':>5} {'Docstr':>7}")
    print("-" * 68)
    for r in sorted(results, key=lambda x: x.get("score", 0)):
        name = r.get("file", "?")
        score = r.get("score", "err")
        long_l = r.get("long_lines", 0)
        todos = r.get("todo_count", 0)
        docstr = r.get("docstring_coverage", 0)
        docstr_pct = f"{docstr * 100:.0f}%" if isinstance(docstr, float) else "n/a"
        print(f"{name:<40} {str(score):>7} {long_l:>5} {todos:>5} {docstr_pct:>7}")


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def cmd_stats(argv: list[str]) -> int:
    """Compute and display git history statistics.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.stats import compute_stats

    parser = argparse.ArgumentParser(prog="awake stats")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--path", default=".", help="Repo root")
    args = parser.parse_args(argv)

    stats = compute_stats(Path(args.path))
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        for k, v in stats.items():
            print(f"{k:<30} {v}")
    return 0


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


def cmd_audit(argv: list[str]) -> int:
    """Run a full repo audit (health + stats + security).

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    print("[awake audit] Running full repo audit...")
    cmd_health([])
    cmd_stats([])
    cmd_security([])
    return 0


# ---------------------------------------------------------------------------
# predict
# ---------------------------------------------------------------------------


def cmd_predict(argv: list[str]) -> int:
    """Predict next session priorities based on current repo state.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.brain import prioritize

    parser = argparse.ArgumentParser(prog="awake predict")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    tasks = prioritize(Path(args.path))
    if args.json:
        print(json.dumps([t.__dict__ for t in tasks], indent=2))
    else:
        print("Predicted priorities for next session:")
        for i, t in enumerate(tasks[:10], 1):
            print(f"  {i:2}. [{t.score:3.0f}] {t.label}")
    return 0


# ---------------------------------------------------------------------------
# dna
# ---------------------------------------------------------------------------


def cmd_dna(argv: list[str]) -> int:
    """Display the repo DNA fingerprint.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.dna import fingerprint

    parser = argparse.ArgumentParser(prog="awake dna")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    fp = fingerprint(Path(args.path))
    if args.json:
        print(json.dumps(fp.__dict__, indent=2))
    else:
        print(fp.render())
    return 0


# ---------------------------------------------------------------------------
# complexity
# ---------------------------------------------------------------------------


def cmd_complexity(argv: list[str]) -> int:
    """Analyze cyclomatic complexity of all src/ modules.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.complexity import analyze_complexity

    parser = argparse.ArgumentParser(prog="awake complexity")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    results = analyze_complexity(Path(args.path))
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Module':<40} {'Avg':>6} {'Max':>6} {'Funcs':>6}")
        print("-" * 62)
        for r in results:
            print(
                f"{r['file']:<40} {r.get('avg_complexity', 0):>6.1f}"
                f" {r.get('max_complexity', 0):>6} {r.get('num_functions', 0):>6}"
            )
    return 0


# ---------------------------------------------------------------------------
# coupling
# ---------------------------------------------------------------------------


def cmd_coupling(argv: list[str]) -> int:
    """Analyze module coupling (afferent/efferent).

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.coupling import analyze_coupling

    parser = argparse.ArgumentParser(prog="awake coupling")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    results = analyze_coupling(Path(args.path))
    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        print(f"{'Module':<40} {'Ca':>4} {'Ce':>4} {'I':>6}")
        print("-" * 58)
        for r in results:
            print(
                f"{r.module:<40} {r.afferent:>4} {r.efferent:>4}"
                f" {r.instability:>6.2f}"
            )
    return 0


# ---------------------------------------------------------------------------
# dead
# ---------------------------------------------------------------------------


def cmd_dead(argv: list[str]) -> int:
    """Detect dead code in src/ modules.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.dead_code import find_dead_code

    parser = argparse.ArgumentParser(prog="awake dead")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    results = find_dead_code(Path(args.path))
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['file']}:{r['line']} -- {r['type']}: {r['name']}")
        if not results:
            print("No dead code found.")
    return 0


# ---------------------------------------------------------------------------
# security
# ---------------------------------------------------------------------------


def cmd_security(argv: list[str]) -> int:
    """Run a security audit on the repo.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.security import audit_security

    parser = argparse.ArgumentParser(prog="awake security")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    result = audit_security(Path(args.path))
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print(result.render())
    return 0


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def cmd_coverage(argv: list[str]) -> int:
    """Run test coverage analysis.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.coverage_tracker import run_coverage

    parser = argparse.ArgumentParser(prog="awake coverage")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    result = run_coverage(Path(args.path))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Coverage: {result.get('total', 'n/a')}%")
    return 0


# ---------------------------------------------------------------------------
# blame
# ---------------------------------------------------------------------------


def cmd_blame(argv: list[str]) -> int:
    """Show git blame attribution (human vs AI).

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.blame import blame_repo

    parser = argparse.ArgumentParser(prog="awake blame")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    result = blame_repo(Path(args.path))
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print(result.render())
    return 0


# ---------------------------------------------------------------------------
# benchmark
# ---------------------------------------------------------------------------


def cmd_benchmark(argv: list[str]) -> int:
    """Run performance benchmarks for all analysis modules.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.benchmark import run_benchmarks

    parser = argparse.ArgumentParser(prog="awake benchmark")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    results = run_benchmarks(Path(args.path))
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"{'Module':<40} {'Time (s)':>10}")
        print("-" * 52)
        for name, elapsed in sorted(results.items(), key=lambda x: x[1]):
            print(f"{name:<40} {elapsed:>10.3f}")
    return 0


# ---------------------------------------------------------------------------
# gitstats
# ---------------------------------------------------------------------------


def cmd_gitstats(argv: list[str]) -> int:
    """Display detailed git statistics.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.gitstats import compute_gitstats

    parser = argparse.ArgumentParser(prog="awake gitstats")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    stats = compute_gitstats(Path(args.path))
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        for k, v in stats.items():
            print(f"{k:<35} {v}")
    return 0


# ---------------------------------------------------------------------------
# maturity
# ---------------------------------------------------------------------------


def cmd_maturity(argv: list[str]) -> int:
    """Score module maturity across 5 dimensions.

    Args:
        argv: Command-line arguments for this subcommand.

    Returns:
        Exit code (0 = success).
    """
    from src.maturity import score_repo

    parser = argparse.ArgumentParser(prog="awake maturity")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--path", default=".")
    args = parser.parse_args(argv)

    results = score_repo(Path(args.path))
    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        print(f"{'Module':<40} {'Score':>6} {'Grade':>6}")
        print("-" * 56)
        for r in sorted(results, key=lambda x: x.score):
            print(f"{r.module:<40} {r.score:>6.1f} {r.grade:>6}")
    return 0
