"""``awake init`` — bootstrap command — Session 16.

Sets up a new project with awake scaffolding in one command:

* Creates ``awake.toml`` with sensible defaults
* Creates ``docs/`` directory with placeholder plan
* Optionally writes ``.gitignore`` snippet
* Validates that git is already initialised (warns if not)

Design notes
------------
We deliberately keep this thin — no external deps beyond stdlib + tomli_w
(already a project dep for awake.toml round-trips).  Prompts are kept to
a minimum so the command works non-interactively in CI.
"""
from __future__ import annotations

import os
import sys
import textwrap
from datetime import date
from pathlib import Path
from typing import Optional

try:
    import tomli_w  # type: ignore
except ImportError:  # pragma: no cover
    tomli_w = None  # type: ignore[assignment]

import typer

app = typer.Typer()

# ---------------------------------------------------------------------------
# Defaults written into awake.toml on ``awake init``
# ---------------------------------------------------------------------------

DEFAULT_TOML: dict = {
    "project": {
        "name": "",           # filled in from cwd name
        "language": "python",
        "style": "focused",
    },
    "thresholds": {
        "min_score": 6,
        "warn_score": 8,
        "files_per_session": 8,
        "lines_per_session": 120,
    },
    "log": {
        "path": "docs/AWAKE_LOG.md",
    },
}

GITIGNORE_SNIPPET = textwrap.dedent("""\
    # Awake artefacts
    .awake_cache/
""")

PLAN_TEMPLATE = textwrap.dedent("""\
    # {date} — Project Bootstrap

    ## Goal
    Initial scaffolding created by `awake init`.

    ## Planned work
    - [ ] Define core modules
    - [ ] Write first tests
    - [ ] Document public API

    ## Notes
    *(fill in as the session progresses)*
""")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_root() -> Optional[Path]:
    """Return the git root above *cwd*, or None if not inside a repo."""
    p = Path.cwd()
    while True:
        if (p / ".git").exists():
            return p
        if p.parent == p:
            return None
        p = p.parent


def _write_toml(root: Path) -> Path:
    """Write awake.toml; return the path written."""
    dest = root / "awake.toml"
    if dest.exists():
        typer.echo(f"  [skip] {dest} already exists — not overwriting")
        return dest

    cfg = dict(DEFAULT_TOML)
    cfg["project"] = dict(cfg["project"])  # shallow copy
    cfg["project"]["name"] = root.name

    if tomli_w is None:  # pragma: no cover
        typer.echo(
            "  [warn] tomli_w not installed — writing minimal toml manually",
            err=True,
        )
        dest.write_text(
            f'[project]\nname = "{root.name}"\nlanguage = "python"\nstyle = "focused"\n',
            encoding="utf-8",
        )
    else:
        dest.write_bytes(tomli_w.dumps(cfg).encode())

    typer.echo(f"  [ok]   wrote {dest}")
    return dest


def _write_docs(root: Path) -> None:
    """Create docs/ directory with a starter plan file."""
    docs = root / "docs"
    docs.mkdir(exist_ok=True)

    plan_path = docs / f"{date.today().isoformat()}-bootstrap-plan.md"
    if plan_path.exists():
        typer.echo(f"  [skip] {plan_path} already exists")
        return

    plan_path.write_text(
        PLAN_TEMPLATE.format(date=date.today().isoformat()),
        encoding="utf-8",
    )
    typer.echo(f"  [ok]   wrote {plan_path}")


def _patch_gitignore(root: Path) -> None:
    """Append Awake snippet to .gitignore if the marker is absent."""
    gi = root / ".gitignore"
    marker = "# Awake artefacts"

    if gi.exists():
        existing = gi.read_text(encoding="utf-8")
        if marker in existing:
            typer.echo("  [skip] .gitignore already contains Awake snippet")
            return
        gi.write_text(existing + "\n" + GITIGNORE_SNIPPET, encoding="utf-8")
    else:
        gi.write_text(GITIGNORE_SNIPPET, encoding="utf-8")

    typer.echo(f"  [ok]   patched {gi}")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

@app.command()
def init(
    path: Path = typer.Argument(
        None,
        help="Directory to initialise (default: current directory).",
    ),
    gitignore: bool = typer.Option(
        True,
        "--gitignore/--no-gitignore",
        help="Patch .gitignore with Awake artefact exclusions.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing awake.toml.",
    ),
) -> None:
    """Bootstrap a new project with Awake scaffolding."""
    root = Path(path).resolve() if path else Path.cwd()

    typer.echo(f"Initialising Awake in {root} …")

    # --- git sanity check ---------------------------------------------------
    git_root = _git_root()
    if git_root is None:
        typer.echo(
            "  [warn] No git repository detected.  Run `git init` first.",
            err=True,
        )
    elif git_root != root:
        typer.echo(
            f"  [info] git root is {git_root} (not {root}) — continuing anyway"
        )

    # --- files --------------------------------------------------------------
    if force and (root / "awake.toml").exists():
        (root / "awake.toml").unlink()
        typer.echo("  [force] removed existing awake.toml")

    _write_toml(root)
    _write_docs(root)

    if gitignore:
        _patch_gitignore(root)

    typer.echo("\nDone.  Run `awake status` to verify your setup.")


if __name__ == "__main__":  # pragma: no cover
    app()
