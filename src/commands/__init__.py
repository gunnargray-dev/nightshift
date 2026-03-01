"""Shared helpers and terminal styling for the CLI command modules."""

from __future__ import annotations

import os
import sys

from pathlib import Path

# Repo root used by most modules
REPO_ROOT = Path(__file__).resolve().parents[2]


def _repo(path: str | None) -> Path:
    """Resolve and validate the repo root path."""
    if path is None:
        return REPO_ROOT
    p = Path(path).expanduser().resolve()
    if not (p / "src").exists():
        raise SystemExit(f"Invalid repo path: {p} (missing src/)")
    return p


# ANSI colours
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.getenv("TERM") not in {"dumb", None}


def _c(text: str, color: str) -> str:
    if not _supports_color():
        return text
    return f"{color}{text}{RESET}"


def _print_header(title: str) -> None:
    bar = "─" * 60
    print("\n" + bar)
    print(f"  🌙 Awake  ·  {title}")
    print(bar + "\n")


def _print_ok(msg: str) -> None:
    print(_c("  ✅  " + msg, GREEN))


def _print_warn(msg: str) -> None:
    print(_c("  ⚠️   " + msg, YELLOW))


def _print_info(msg: str) -> None:
    print(_c("  ℹ️   " + msg, CYAN))


# Re-exported for convenience
__all__ = [
    "REPO_ROOT",
    "_repo",
    "_print_header",
    "_print_ok",
    "_print_warn",
    "_print_info",
]


# Auto-merge gate
from src.commands.infra_automerge import cmd_automerge
