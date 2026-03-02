"""README auto-updater for Awake.

Generates a dynamic README.md by stitching together:

1. A static header block (``README.header.md``) if it exists, otherwise
   a generated project title + description.
2. An auto-generated **Metrics** table with the latest values from
   ``docs/trend_data.json``.
3. A **Module Overview** table listing every ``src/*.py`` file with its
   one-line module docstring.
4. A static footer block (``README.footer.md``) if it exists.

The updater writes to ``README.md`` by default and can optionally commit
the change via ``git``.

Public API
----------
- ``ReadmeConfig``   -- configuration for the update
- ``update_readme(repo_path, config)``

CLI
---
    awake readme [--commit] [--dry-run] [--output PATH]
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class ReadmeConfig:
    """Configuration for the README update operation."""

    output_path: str = "README.md"
    trend_data_path: str = "docs/trend_data.json"
    header_path: str = "README.header.md"
    footer_path: str = "README.footer.md"
    commit: bool = False
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_optional(path: Path) -> str:
    """Read *path* and return its content, or empty string if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_module_docstring(py_file: Path) -> str:
    """Return the first line of the module-level docstring of *py_file*, or ''."""
    try:
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return ""
    if not tree.body:
        return ""
    first = tree.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        return first.value.value.splitlines()[0].strip()
    return ""


def _load_latest_metrics(trend_path: Path) -> dict[str, str]:
    """Load the latest metrics from the trend data JSON file."""
    try:
        data = json.loads(trend_path.read_text(encoding="utf-8"))
        samples = data.get("samples", [])
        if not samples:
            return {}
        latest = max(samples, key=lambda s: s.get("timestamp", ""))
        return {
            "health_score": f"{latest.get('health_score', 0.0):.1f}",
            "docstring_coverage": f"{latest.get('docstring_coverage', 0.0):.1%}",
            "refactor_issues": str(latest.get("refactor_issues", 0)),
            "test_quality": f"{latest.get('test_quality', 0.0):.1f}",
            "open_todos": str(latest.get("open_todos", 0)),
            "timestamp": latest.get("timestamp", "")[:19],
        }
    except (OSError, json.JSONDecodeError, KeyError):
        return {}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _build_metrics_table(metrics: dict[str, str]) -> str:
    """Return a Markdown metrics table from *metrics*."""
    if not metrics:
        return "_No trend data collected yet.  Run `awake trend --collect` to start._\n"
    rows = [
        ("Health Score", metrics.get("health_score", "N/A")),
        ("Docstring Coverage", metrics.get("docstring_coverage", "N/A")),
        ("Refactor Issues", metrics.get("refactor_issues", "N/A")),
        ("Test Quality", metrics.get("test_quality", "N/A")),
        ("Open TODOs", metrics.get("open_todos", "N/A")),
    ]
    lines = [
        "| Metric | Value |",
        "| --- | --- |",
    ]
    lines += [f"| {k} | {v} |" for k, v in rows]
    ts = metrics.get("timestamp", "")
    if ts:
        lines.append(f"\n_Last updated: {ts} UTC_")
    return "\n".join(lines) + "\n"


def _build_module_table(src_dir: Path) -> str:
    """Return a Markdown table of src/*.py files with their docstrings."""
    py_files = sorted(src_dir.glob("*.py"))
    if not py_files:
        return "_No source files found._\n"
    lines = [
        "| Module | Description |",
        "| --- | --- |",
    ]
    for pf in py_files:
        if pf.name.startswith("_"):
            continue
        doc = _extract_module_docstring(pf) or "—"
        lines.append(f"| `{pf.name}` | {doc} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def update_readme(repo_path: str | Path, config: ReadmeConfig | None = None) -> str:
    """Generate and write the README for *repo_path*.

    Parameters
    ----------
    repo_path:
        Root directory of the repository.
    config:
        Configuration.  Defaults to :class:`ReadmeConfig`.

    Returns
    -------
    str
        The generated README content.
    """
    if config is None:
        config = ReadmeConfig()

    root = Path(repo_path)
    parts: list[str] = []

    # 1. Header
    header = _read_optional(root / config.header_path)
    if header:
        parts.append(header.rstrip() + "\n")
    else:
        parts.append("# Awake\n\nAI-assisted repository health tool.\n")

    # 2. Metrics table
    parts.append("\n## Metrics\n\n")
    metrics = _load_latest_metrics(root / config.trend_data_path)
    parts.append(_build_metrics_table(metrics))

    # 3. Module overview
    parts.append("\n## Modules\n\n")
    parts.append(_build_module_table(root / "src"))

    # 4. Footer
    footer = _read_optional(root / config.footer_path)
    if footer:
        parts.append("\n" + footer.rstrip() + "\n")

    readme = "".join(parts)

    if config.dry_run:
        print(readme)
    else:
        out = root / config.output_path
        out.write_text(readme, encoding="utf-8")

    if config.commit and not config.dry_run:
        import subprocess

        subprocess.run(
            ["git", "add", config.output_path],
            cwd=str(root),
            check=False,
        )
        subprocess.run(
            ["git", "commit", "-m", "docs: auto-update README [skip ci]"],
            cwd=str(root),
            check=False,
        )

    return readme


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the README auto-updater.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake readme",
        description="Auto-update the README with live repo metrics.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--commit", action="store_true", help="Commit the updated README")
    parser.add_argument("--dry-run", action="store_true", help="Print README without writing")
    parser.add_argument(
        "--output",
        "-o",
        default="README.md",
        help="Output file path (default: README.md)",
    )
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    config = ReadmeConfig(
        output_path=args.output,
        commit=args.commit,
        dry_run=args.dry_run,
    )
    update_readme(root, config)

    if not args.dry_run:
        print(f"README written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
