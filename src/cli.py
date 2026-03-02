"""Unified CLI entry point for Awake.

Provides a single ``awake`` command that dispatches to all sub-commands:

    awake health        -- repository health scan
    awake docstrings    -- missing docstring scanner / generator
    awake graph         -- module import graph
    awake openapi       -- OpenAPI spec generator
    awake plugins       -- plugin management
    awake refactor      -- code-quality checker / auto-fixer
    awake replay        -- session replay from git history
    awake test-quality  -- test quality analyzer
    awake pr-score      -- PR quality scorer
    awake changelog     -- release notes generator
    awake report        -- executive HTML report
    awake trend         -- historical metric trend collector
    awake automerge     -- auto-merge helper
    awake readme        -- README auto-updater

Each sub-command is implemented in its own module; this file only wires
them together and provides top-level ``--version`` / ``--help``.

Public API
----------
- ``main(argv)`` -- CLI entry point

CLI
---
    awake [--version] [--help] <subcommand> [args...]
"""

from __future__ import annotations

import sys
from typing import Callable

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

__version__ = "0.1.0"

# ---------------------------------------------------------------------------
# Sub-command registry
# ---------------------------------------------------------------------------

# Maps sub-command name -> (module_path, entry_function_name)
# We import lazily to keep startup fast.
_SUBCOMMANDS: dict[str, tuple[str, str]] = {
    "health":       ("health",        "main"),
    "docstrings":   ("docstring_gen",  "main"),
    "graph":        ("module_graph",   "main"),
    "openapi":      ("openapi",        "main"),
    "plugins":      ("plugins",        "main"),
    "refactor":     ("refactor",       "main"),
    "replay":       ("session_replay", "main"),
    "test-quality": ("test_quality",   "main"),
    "pr-score":     ("pr_scorer",      "main"),
    "changelog":    ("release_notes",  "main"),
    "report":       ("report",         "main"),
    "trend":        ("trend_data",     "main"),
    "automerge":    ("automerge",      "main"),
    "readme":       ("readme_updater", "main"),
}

_HELP_TEXT = f"""\
Awake {__version__} -- AI-assisted repository health tool

Usage:
    awake [--version] [--help] <subcommand> [args...]

Subcommands:
    health        Scan repository health and score files
    docstrings    Scan for and generate missing docstrings
    graph         Visualise module import relationships
    openapi       Generate an OpenAPI 3.1 spec from route decorators
    plugins       Manage Awake plugins
    refactor      Detect and fix code-quality issues
    replay        Reconstruct a developer session from git history
    test-quality  Grade test quality across the repository
    pr-score      Score a pull request or local branch diff
    changelog     Generate release notes from git history
    report        Generate an executive HTML report
    trend         Collect and store repository metric trends
    automerge     Auto-merge a pull request when conditions are met
    readme        Auto-update the README with live repo metrics

Run ``awake <subcommand> --help`` for subcommand-specific options.
"""


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _load_subcommand(name: str) -> Callable[[list[str] | None], int]:
    """Import and return the main() function for the named sub-command."""
    import importlib

    module_name, func_name = _SUBCOMMANDS[name]
    module = importlib.import_module(module_name)
    fn: Callable[[list[str] | None], int] = getattr(module, func_name)
    return fn


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Unified CLI entry point for Awake.

    Parameters
    ----------
    argv:
        Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns
    -------
    int
        Exit code.
    """
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help"):
        print(_HELP_TEXT)
        return 0

    if argv[0] in ("-V", "--version"):
        print(f"awake {__version__}")
        return 0

    subcommand = argv[0]
    rest = argv[1:]

    if subcommand not in _SUBCOMMANDS:
        print(f"awake: unknown subcommand '{subcommand}'\n", file=sys.stderr)
        print(_HELP_TEXT, file=sys.stderr)
        return 1

    try:
        fn = _load_subcommand(subcommand)
    except ImportError as exc:
        print(f"awake: could not load '{subcommand}': {exc}", file=sys.stderr)
        return 1

    return fn(rest)


if __name__ == "__main__":
    raise SystemExit(main())
