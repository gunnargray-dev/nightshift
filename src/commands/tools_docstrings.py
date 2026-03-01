"""Docstring generator command for Awake CLI.

This is a thin wrapper around :mod:`src.docstring_gen`.
"""

from __future__ import annotations

import json

from src.docstring_gen import (
    scan_missing_docstrings,
    apply_docstrings,
    save_docstring_report,
    render_markdown,
)
from src.commands import _repo, _print_header, _print_ok, _print_warn, _print_info


def cmd_docstrings(args) -> int:
    """Scan for missing docstrings and optionally generate them."""
    repo = _repo(getattr(args, "repo", None))
    _print_header("Docstring Generator")

    report = scan_missing_docstrings(repo)

    if getattr(args, "apply", False) or getattr(args, "dry_run", False):
        dry = getattr(args, "dry_run", False)
        modified = apply_docstrings(report, repo, dry_run=dry)
        action = "Would modify" if dry else "Modified"
        for m in modified:
            _print_info(f"{action}: {m}")
        if not modified:
            _print_ok("No files to modify.")

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    if getattr(args, "write", False):
        docs = repo / "docs"
        docs.mkdir(exist_ok=True)
        save_docstring_report(report, docs / "docstring_report.json")
        md_path = docs / "docstring_report.md"
        md_path.write_text(render_markdown(report), encoding="utf-8")
        _print_ok("Wrote docs/docstring_report.json")
        _print_ok("Wrote docs/docstring_report.md")
        return 0

    print(render_markdown(report))

    if report.coverage_pct >= 90:
        _print_ok(f"Docstring coverage: {report.coverage_pct:.1f}%")
    elif report.coverage_pct >= 70:
        _print_warn(f"Docstring coverage: {report.coverage_pct:.1f}%")
    else:
        _print_warn(f"Docstring coverage: {report.coverage_pct:.1f}% (low)")

    return 0
