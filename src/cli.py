"""Awake CLI -- unified entry point.

Routes `awake <subcommand>` to the appropriate command module or legacy
handler.  All new subcommands should be added as modules under
``src/commands/`` and registered in ``COMMAND_REGISTRY`` below.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------
# Maps subcommand name -> (module_path, function_name) for commands that
# live in src/commands/.  Legacy commands are handled inline in _run().
# ---------------------------------------------------------------------------

COMMAND_REGISTRY: dict[str, tuple[str, str]] = {
    # analysis commands
    "health": ("src.commands.analysis", "cmd_health"),
    "stats": ("src.commands.analysis", "cmd_stats"),
    "audit": ("src.commands.analysis", "cmd_audit"),
    "predict": ("src.commands.analysis", "cmd_predict"),
    "dna": ("src.commands.analysis", "cmd_dna"),
    "complexity": ("src.commands.analysis", "cmd_complexity"),
    "coupling": ("src.commands.analysis", "cmd_coupling"),
    "dead": ("src.commands.analysis", "cmd_dead"),
    "security": ("src.commands.analysis", "cmd_security"),
    "coverage": ("src.commands.analysis", "cmd_coverage"),
    "blame": ("src.commands.analysis", "cmd_blame"),
    "benchmark": ("src.commands.analysis", "cmd_benchmark"),
    "gitstats": ("src.commands.analysis", "cmd_gitstats"),
    "maturity": ("src.commands.analysis", "cmd_maturity"),
    # meta / self-improvement commands
    "brain": ("src.commands.meta", "cmd_brain"),
    "reflect": ("src.commands.meta", "cmd_reflect"),
    "evolve": ("src.commands.meta", "cmd_evolve"),
    "story": ("src.commands.meta", "cmd_story"),
    "status": ("src.commands.meta", "cmd_status"),
    "automerge": ("src.commands.meta", "cmd_automerge"),
    "docstrings": ("src.commands.meta", "cmd_docstrings"),
    # tooling / utility commands
    "changelog": ("src.commands.tools", "cmd_changelog"),
    "coverage-map": ("src.commands.tools", "cmd_coverage_map"),
    "refactor": ("src.commands.tools", "cmd_refactor"),
    "readme": ("src.commands.tools", "cmd_readme"),
    "diff": ("src.commands.tools", "cmd_diff"),
    "arch": ("src.commands.tools", "cmd_arch"),
    "export": ("src.commands.tools", "cmd_export"),
    "badges": ("src.commands.tools", "cmd_badges"),
    "teach": ("src.commands.tools", "cmd_teach"),
    "docstring": ("src.commands.tools", "cmd_docstring"),
    # infra / repo-management commands
    "log": ("src.commands.infra", "cmd_log"),
    "compare": ("src.commands.infra", "cmd_compare"),
    "timeline": ("src.commands.infra", "cmd_timeline"),
    "replay": ("src.commands.infra", "cmd_replay"),
    "depgraph": ("src.commands.infra", "cmd_depgraph"),
    "todos": ("src.commands.infra", "cmd_todos"),
    "doctor": ("src.commands.infra", "cmd_doctor"),
    "triage": ("src.commands.infra", "cmd_triage"),
    "score": ("src.commands.infra", "cmd_score"),
    "deps": ("src.commands.infra", "cmd_deps"),
    "config": ("src.commands.infra", "cmd_config"),
    "server": ("src.commands.infra", "cmd_server"),
    "dashboard": ("src.commands.infra", "cmd_dashboard"),
    "report": ("src.commands.infra", "cmd_report"),
    "ci-gate": ("src.commands.infra", "cmd_ci_gate"),
    "coverage-gate": ("src.commands.infra", "cmd_coverage_gate"),
}


# ---------------------------------------------------------------------------
# Dispatch helpers
# ---------------------------------------------------------------------------


def _dispatch(subcommand: str, argv: list[str]) -> int:
    """Import and call the handler registered for *subcommand*.

    Args:
        subcommand: The CLI subcommand string.
        argv: Remaining command-line arguments passed to the handler.

    Returns:
        Exit code (0 = success).
    """
    entry = COMMAND_REGISTRY.get(subcommand)
    if entry is None:
        print(f"awake: unknown command '{subcommand}'")
        print("Run `awake --help` for a list of commands.")
        return 1
    module_path, func_name = entry
    try:
        module = importlib.import_module(module_path)
        handler: Callable[[list[str]], int] = getattr(module, func_name)
        return handler(argv) or 0
    except ImportError as exc:
        print(f"awake: failed to load command '{subcommand}': {exc}")
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"awake: error running '{subcommand}': {exc}")
        return 1


# ---------------------------------------------------------------------------
# Top-level parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="awake",
        description="Awake -- autonomous self-improving dev system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_HELP_EPILOG,
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        help="Subcommand to run (see below)",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to the subcommand",
    )
    return parser


_HELP_EPILOG = """
Available subcommands
---------------------
Analysis
  health        Code health scores for all src/ modules
  stats         Git history statistics
  audit         Full repo audit (health + stats + security)
  predict       Predict next session priorities
  dna           Repo DNA fingerprint
  complexity    Cyclomatic complexity analysis
  coupling      Module coupling analysis
  dead          Dead code detection
  security      Security audit
  coverage      Test coverage report
  blame         Git blame attribution
  benchmark     Performance benchmarks
  gitstats      Detailed git statistics
  maturity      Module maturity scores

Meta / Self-improvement
  brain         Task prioritization engine
  reflect       Self-reflection on past sessions
  evolve        Gap analysis and evolution proposals
  story         Repo narrative generator
  status        Comprehensive health snapshot
  automerge     Auto-merge eligibility check
  docstrings    Auto-generate missing docstrings

Tooling / Utilities
  changelog     Generate CHANGELOG.md
  coverage-map  Coverage heat map
  refactor      AST-based refactor analysis
  readme        Update README.md with live stats
  diff          Session diff visualizer
  arch          Generate architecture docs
  export        Export analysis to JSON/Markdown/HTML
  badges        Generate README badges
  teach         Module tutorial generator
  docstring     Docstring quality report

Infra / Repo management
  log           Append a session log entry
  compare       Compare two sessions
  timeline      Visual session timeline
  replay        Replay a past session
  depgraph      Module dependency graph
  todos         Stale TODO hunter
  doctor        Full repo diagnostic
  triage        Issue triage
  score         PR quality scorer
  deps          Dependency freshness check
  config        Manage awake.toml config
  server        Start the API server
  dashboard     Terminal dashboard
  report        Generate full session report
  ci-gate       Health score CI gate
  coverage-gate Coverage CI gate
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the `awake` CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).

    Returns:
        Process exit code.
    """
    if argv is None:
        argv = sys.argv[1:]

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        try:
            import src  # type: ignore
            print(f"awake v{src.__version__}")
        except Exception:
            print("awake v0.0.0")
        return 0

    if args.subcommand is None:
        parser.print_help()
        return 0

    return _dispatch(args.subcommand, args.args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
