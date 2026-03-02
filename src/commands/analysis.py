"""Analysis sub-commands for the Awake CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()
analysis_app = typer.Typer(name="analysis", help="Code analysis utilities.")


@analysis_app.command(name="complexity")
def complexity_cmd(
    path: str = typer.Argument(".", help="File or directory to analyse"),
    threshold: float = typer.Option(10.0, "--threshold", "-t"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
    fmt: str = typer.Option("table", "--format", "-f", help="table | json"),
) -> None:
    """Report cyclomatic complexity of Python functions."""
    from ..complexity import analyse_complexity

    root = Path(path)
    results = analyse_complexity(root, threshold=threshold)

    if fmt == "json" or output:
        out = json.dumps(results, indent=2, default=str)
        if output:
            Path(output).write_text(out)
            console.print(f"[green]Complexity results written to {output}[/green]")
        else:
            console.print_json(out)
        return

    # Table output
    t = Table("File", "Function", "Complexity", "Exceeds Threshold")
    for item in results:
        exceeds = str(item["complexity"] > threshold)
        t.add_row(item["file"], item["function"], str(item["complexity"]), exceeds)
    console.print(t)


@analysis_app.command(name="duplicates")
def duplicates_cmd(
    path: str = typer.Argument("."),
    min_lines: int = typer.Option(6, "--min-lines"),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Detect duplicate code blocks."""
    from ..duplicates import find_duplicates

    root = Path(path)
    dupes = find_duplicates(root, min_lines=min_lines)
    out = json.dumps(dupes, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Duplicates written to {output}[/green]")
    else:
        console.print_json(out)


@analysis_app.command(name="dead-code")
def dead_code_cmd(
    path: str = typer.Argument("."),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Find potentially unused functions and classes."""
    from ..dead_code import find_dead_code

    root = Path(path)
    results = find_dead_code(root)
    out = json.dumps(results, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Dead code results written to {output}[/green]")
    else:
        console.print_json(out)


@analysis_app.command(name="security")
def security_cmd(
    path: str = typer.Argument("."),
    output: Optional[str] = typer.Option(None, "--output", "-o"),
) -> None:
    """Run a basic security scan for common vulnerabilities."""
    from ..security import run_security_scan

    root = Path(path)
    issues = run_security_scan(root)
    out = json.dumps(issues, indent=2, default=str)
    if output:
        Path(output).write_text(out)
        console.print(f"[green]Security scan written to {output}[/green]")
    else:
        console.print_json(out)
