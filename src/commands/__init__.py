"""Shared CLI utilities imported by all command group modules.

This module provides the common helpers (repo resolver, print helpers) and
re-exports everything a command group needs so that each group only has to
``from src.commands import ...`` rather than reproducing the same boilerplate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _repo(args_path: Optional[str] = None) -> Path:
    """Return the repo root, preferring an explicit --repo flag value."""
    return Path(args_path) if args_path else REPO_ROOT


def _print_header(title: str) -> None:
    """Print a decorative section header."""
    bar = "\u2500" * 60
    print(f"\n{bar}")
    print(f"  \U0001f319 Nightshift  \u00b7  {title}")
    print(f"{bar}\n")


def _print_ok(msg: str) -> None:
    """Print a success message."""
    print(f"  \u2705  {msg}")


def _print_warn(msg: str) -> None:
    """Print a warning message."""
    print(f"  \u26a0\ufe0f   {msg}")


def _print_info(msg: str) -> None:
    """Print an informational message."""
    print(f"  \u00b7  {msg}")


__all__ = [
    "argparse",
    "json",
    "sys",
    "Path",
    "Optional",
    "REPO_ROOT",
    "_repo",
    "_print_header",
    "_print_ok",
    "_print_warn",
    "_print_info",
]
