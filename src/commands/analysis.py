"""Analysis command group for Awake CLI.

Commands: health, complexity, coupling, dead_code (deadcode), security,
coverage_map (coveragemap), blame, maturity.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.commands import _repo, _print_header, _print_ok, _print_warn, _print_info


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def cmd_health(args) -> int:
    """Run code health analysis across src/."""
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
# complexity
# ---------------------------------------------------------------------------


def cmd_complexity(args) -> int:
    """Analyze cyclomatic complexity -- McCabe complexity per function."""
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
        _print_ok(f"JSON sidecar -> {out.with_suffix('.json')}")
        return 0
    print(report.to_markdown())
    _print_info(
        f"Functions: {report.total_functions}  "
        f"Avg complexity: {report.avg_complexity:.1f}  "
        f"HIGH: {report.high_count}  MEDIUM: {report.medium_count}  LOW: {report.low_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# coupling
# ---------------------------------------------------------------------------


def cmd_coupling(args) -> int:
    """Analyze module coupling -- afferent/efferent coupling, instability metric."""
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
        _print_ok(f"JSON sidecar -> {out.with_suffix('.json')}")
        return 0
    print(report.to_markdown())
    _print_info(
        f"Modules: {len(report.modules)}  "
        f"Avg instability: {report.avg_instability:.2f}  "
        f"HIGH: {report.high_count}  MEDIUM: {report.medium_count}  LOW: {report.low_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# deadcode
# ---------------------------------------------------------------------------


def cmd_deadcode(args) -> int:
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
        f"Dead symbols: {report.dead_count}  "
        f"HIGH: {report.high_count}  MEDIUM: {report.medium_count}  LOW: {report.low_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# security
# ---------------------------------------------------------------------------


def cmd_security(args) -> int:
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
        _print_ok(f"Grade: {grade} -- no critical issues")
    else:
        _print_warn(f"Grade: {grade} -- HIGH: {report.high_count}  MEDIUM: {report.medium_count}")
    return 0


# ---------------------------------------------------------------------------
# coveragemap
# ---------------------------------------------------------------------------


def cmd_coveragemap(args) -> int:
    """Coverage heat map: weakest test files ranked first."""
    from src.coverage_map import build_coverage_map
    _print_header("Coverage Heat Map")
    repo = _repo(getattr(args, "repo", None))
    report = build_coverage_map(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    _print_info(f"Overall: {report.overall_pct:.1f}%  Files: {report.file_count}")
    return 0


# ---------------------------------------------------------------------------
# blame
# ---------------------------------------------------------------------------


def cmd_blame(args) -> int:
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
        f"Human: {report.human_pct:.1f}%  AI: {report.ai_pct:.1f}%  "
        f"Files analysed: {report.file_count}"
    )
    return 0


# ---------------------------------------------------------------------------
# maturity
# ---------------------------------------------------------------------------


def cmd_maturity(args) -> int:
    """Compute per-module maturity score (0-100)."""
    from src.maturity import assess_maturity, save_maturity_report
    _print_header("Module Maturity Scores")
    repo = _repo(getattr(args, "repo", None))
    report = assess_maturity(repo)
    if args.write:
        out = repo / "docs" / "maturity_report.md"
        save_maturity_report(report, out)
        _print_ok(f"Report written to {out}")
        return 0
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(report.to_markdown())
    module_count = len(report.modules)
    high = sum(1 for m in report.modules if m.total_score >= 80)
    medium = sum(1 for m in report.modules if 40 <= m.total_score < 80)
    low = sum(1 for m in report.modules if m.total_score < 40)
    _print_info(
        f"Modules: {module_count}  Avg: {report.avg_score:.1f}/100  "
        f"High: {high}  Medium: {medium}  Low: {low}"
    )
    return 0
