"""Command-line interface for Awake."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .changelog import (
    ChangelogRelease,
    get_commits_between,
    render_markdown,
    write_changelog,
)
from .docstring_gen import DocstringConfig, batch_add_docstrings
from .module_graph import build_module_graph, render_dot, render_json
from .openapi import OpenAPIConfig, generate_openapi_spec
from .plugins import PluginManager
from .pr_scorer import ScoringConfig, score_pull_request
from .readme_updater import ReadmeConfig, update_readme
from .refactor import RefactorConfig, RefactorEngine
from .release_notes import ReleaseNotesConfig, generate_release_notes
from .report import ReportConfig, generate_report
from .session_replay import ReplayConfig, SessionReplayEngine
from .test_quality import TestQualityConfig, analyze_test_quality
from .trend_data import TrendConfig, record_trend_snapshot

app = typer.Typer(
    name="awake",
    help="Awake -- AI-powered repository health toolkit.",
    add_completion=False,
)
console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo(path: Optional[str]) -> Path:
    p = Path(path) if path else Path(".")
    if not p.exists():
        console.print(f"[red]Path not found: {p}[/red]")
        raise typer.Exit(1)
    return p


def _out(path: Optional[str]) -> Optional[Path]:
    return Path(path) if path else None


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the Awake version."""
    console.print(f"awake {__version__}")


# ---------------------------------------------------------------------------
# Changelog
# ---------------------------------------------------------------------------


@app.command()
def changelog(
    from_ref: str = typer.Argument(..., help="Git ref (tag/SHA) to start from"),
    to_ref: str = typer.Option("HEAD", help="Git ref to end at"),
    version_name: str = typer.Option("Unreleased", "--version", "-v"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
    no_hashes: bool = typer.Option(False, "--no-hashes"),
    prepend: bool = typer.Option(True, "--prepend/--no-prepend"),
) -> None:
    """Generate a changelog from conventional commits."""
    from datetime import date

    cwd = _repo(repo)
    entries = get_commits_between(from_ref, to_ref, repo=cwd)
    release = ChangelogRelease(
        version=version_name,
        release_date=date.today(),
        entries=entries,
    )
    md = render_markdown(release, include_hashes=not no_hashes)
    if output:
        out_path = Path(output)
        write_changelog(release, out_path, prepend=prepend, include_hashes=not no_hashes)
        console.print(f"[green]Changelog written to {out_path}[/green]")
    else:
        console.print(md)


# ---------------------------------------------------------------------------
# Module graph
# ---------------------------------------------------------------------------


@app.command(name="module-graph")
def module_graph(
    path: str = typer.Argument(".", help="Root directory to analyse"),
    fmt: str = typer.Option("dot", "--format", "-f", help="dot | json"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    exclude: list[str] = typer.Option([], "--exclude", "-e"),
) -> None:
    """Render the Python module dependency graph."""
    root = _repo(path)
    graph = build_module_graph(root, exclude=set(exclude))
    if fmt == "json":
        rendered = render_json(graph)
    else:
        rendered = render_dot(graph)
    if output:
        Path(output).write_text(rendered, encoding="utf-8")
        console.print(f"[green]Graph written to {output}[/green]")
    else:
        console.print(rendered)


# ---------------------------------------------------------------------------
# PR scorer
# ---------------------------------------------------------------------------


@app.command(name="score-pr")
def score_pr(
    pr_number: int = typer.Argument(..., help="Pull-request number"),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    weights: Optional[str] = typer.Option(None, "--weights", help="JSON weights object"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Score a pull request for quality and risk."""
    cwd = _repo(repo)
    cfg = ScoringConfig(model=model)
    if weights:
        cfg.weights = json.loads(weights)
    result = score_pull_request(pr_number, config=cfg, repo=cwd)
    out = json.dumps(result, indent=2)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Score written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# Docstrings
# ---------------------------------------------------------------------------


@app.command(name="add-docstrings")
def add_docstrings(
    path: str = typer.Argument(".", help="File or directory to process"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    style: str = typer.Option("google", "--style", help="google | numpy | sphinx"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Add AI-generated docstrings to Python source files."""
    root = Path(path)
    cfg = DocstringConfig(model=model, style=style, overwrite=overwrite, dry_run=dry_run)
    results = batch_add_docstrings(root, config=cfg)
    out = json.dumps(results, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Results written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# README updater
# ---------------------------------------------------------------------------


@app.command(name="update-readme")
def update_readme_cmd(
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    sections: list[str] = typer.Option([], "--section", "-s"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Refresh the README with up-to-date project information."""
    cwd = _repo(repo)
    cfg = ReadmeConfig(
        model=model,
        sections=sections or None,
        dry_run=dry_run,
    )
    result = update_readme(cwd, config=cfg)
    out = json.dumps(result, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]README update written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# OpenAPI spec
# ---------------------------------------------------------------------------


@app.command(name="gen-openapi")
def gen_openapi(
    path: str = typer.Argument(".", help="Directory containing FastAPI/Flask app"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    title: str = typer.Option("My API", "--title"),
    api_version: str = typer.Option("0.1.0", "--api-version"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Generate an OpenAPI specification for a Python web API."""
    root = Path(path)
    cfg = OpenAPIConfig(model=model, title=title, version=api_version)
    spec = generate_openapi_spec(root, config=cfg)
    out = json.dumps(spec, indent=2)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]OpenAPI spec written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# Release notes
# ---------------------------------------------------------------------------


@app.command(name="release-notes")
def release_notes(
    from_ref: str = typer.Argument(..., help="Starting git ref"),
    to_ref: str = typer.Option("HEAD"),
    version_name: str = typer.Option("Unreleased", "--version", "-v"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    audience: str = typer.Option("technical", "--audience"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
) -> None:
    """Generate human-friendly release notes with AI."""
    cwd = _repo(repo)
    cfg = ReleaseNotesConfig(model=model, audience=audience)
    notes = generate_release_notes(from_ref, to_ref, version=version_name, config=cfg, repo=cwd)
    if output:
        Path(output).write_text(notes, encoding="utf-8")
        console.print(f"[green]Release notes written to {output}[/green]")
    else:
        console.print(notes)


# ---------------------------------------------------------------------------
# Refactor
# ---------------------------------------------------------------------------


@app.command()
def refactor(
    path: str = typer.Argument("."),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    rule: list[str] = typer.Option([], "--rule", "-R"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Apply AI-powered refactoring suggestions to Python code."""
    root = Path(path)
    cfg = RefactorConfig(model=model, rules=rule or None, dry_run=dry_run)
    engine = RefactorEngine(cfg)
    results = engine.run(root)
    out = json.dumps(results, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Refactor results written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@app.command()
def report(
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    fmt: str = typer.Option("markdown", "--format", "-f"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    since: Optional[str] = typer.Option(None, "--since"),
) -> None:
    """Generate a comprehensive health report for the repository."""
    cwd = _repo(repo)
    cfg = ReportConfig(model=model, format=fmt, since=since)
    content = generate_report(cwd, config=cfg)
    if output:
        Path(output).write_text(content, encoding="utf-8")
        console.print(f"[green]Report written to {output}[/green]")
    else:
        console.print(content)


# ---------------------------------------------------------------------------
# Test quality
# ---------------------------------------------------------------------------


@app.command(name="test-quality")
def test_quality(
    path: str = typer.Argument("."),
    model: str = typer.Option("gpt-4o-mini", "--model"),
    threshold: float = typer.Option(0.7, "--threshold"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Analyse test quality and suggest improvements."""
    root = Path(path)
    cfg = TestQualityConfig(model=model, threshold=threshold)
    results = analyze_test_quality(root, config=cfg)
    out = json.dumps(results, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Test quality results written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# Trend data
# ---------------------------------------------------------------------------


@app.command(name="record-trends")
def record_trends(
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    db: Optional[str] = typer.Option(None, "--db"),
) -> None:
    """Record a snapshot of repository health metrics for trend tracking."""
    cwd = _repo(repo)
    cfg = TrendConfig(db_path=Path(db) if db else None)
    snapshot = record_trend_snapshot(cwd, config=cfg)
    out = json.dumps(snapshot, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Trend snapshot written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# Session replay
# ---------------------------------------------------------------------------


@app.command(name="replay")
def replay(
    session_file: str = typer.Argument(..., help="Path to the session JSON file"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    speed: float = typer.Option(1.0, "--speed"),
    model: str = typer.Option("gpt-4o-mini", "--model"),
) -> None:
    """Replay a recorded coding session with AI annotations."""
    cfg = ReplayConfig(speed=speed, model=model)
    engine = SessionReplayEngine(cfg)
    result = engine.replay(Path(session_file))
    out = json.dumps(result, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Replay result written to {output}[/green]")
    else:
        console.print_json(out)


# ---------------------------------------------------------------------------
# Plugin management
# ---------------------------------------------------------------------------


@app.command(name="plugin")
def plugin_cmd(
    action: str = typer.Argument(..., help="install | uninstall | list"),
    name: Optional[str] = typer.Argument(None),
    plugin_dir: Optional[str] = typer.Option(None, "--plugin-dir"),
) -> None:
    """Manage Awake plugins."""
    mgr = PluginManager(plugin_dir=Path(plugin_dir) if plugin_dir else None)
    if action == "list":
        plugins = mgr.list_plugins()
        if not plugins:
            console.print("No plugins installed.")
        else:
            t = Table("Name", "Version", "Description")
            for p in plugins:
                t.add_row(p.name, p.version, p.description)
            console.print(t)
    elif action == "install":
        if not name:
            console.print("[red]Plugin name required for install[/red]")
            raise typer.Exit(1)
        mgr.install(name)
        console.print(f"[green]Installed {name}[/green]")
    elif action == "uninstall":
        if not name:
            console.print("[red]Plugin name required for uninstall[/red]")
            raise typer.Exit(1)
        mgr.uninstall(name)
        console.print(f"[green]Uninstalled {name}[/green]")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# Analysis sub-commands (delegated)
# ---------------------------------------------------------------------------

from .commands.analysis import analysis_app  # noqa: E402

app.add_typer(analysis_app, name="analysis")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    app()


if __name__ == "__main__":
    main()
