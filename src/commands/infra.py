"""Infrastructure command group for Nightshift CLI.

Commands: dashboard (terminal), server (web), init, deps, config, plugins, openapi.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.commands import _repo, _print_header, _print_ok, _print_warn, _print_info


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------


def cmd_dashboard(args) -> int:
    """Launch the live React dashboard (API server + UI)."""
    from src.server import start_server
    _print_header("Nightshift Dashboard")
    repo = _repo(getattr(args, "repo", None))
    port = getattr(args, "port", 8710)
    _print_ok(f"Starting API server on port {port} ...")
    _print_info("Open http://127.0.0.1:8710 in your browser.")
    _print_info("Press Ctrl+C to stop.")
    start_server(port=port, repo_path=repo, open_browser=not getattr(args, "no_browser", False))
    return 0


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def cmd_init(args) -> int:
    """Bootstrap project scaffolding and nightshift.toml."""
    from src.init_cmd import init_project
    _print_header("Nightshift Init")
    repo = _repo(getattr(args, "repo", None))
    result = init_project(repo, force=getattr(args, "force", False))
    for msg in result.messages:
        _print_ok(msg)
    for warn in result.warnings:
        _print_warn(warn)
    return 0


# ---------------------------------------------------------------------------
# deps
# ---------------------------------------------------------------------------


def cmd_deps(args) -> int:
    """Check Python dependency freshness via PyPI."""
    try:
        from src.deps import check_deps, render_deps_report
    except ImportError:
        _print_warn("deps module not available")
        return 1
    _print_header("Dependency Freshness Check")
    repo = _repo(getattr(args, "repo", None))
    report = check_deps(repo)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    print(render_deps_report(report))
    stale = [d for d in report.deps if d.is_stale]
    if stale:
        _print_warn(f"{len(stale)} stale dependencies")
    else:
        _print_ok("All dependencies up-to-date")
    return 0


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def cmd_config(args) -> int:
    """Show or write nightshift.toml configuration."""
    from src.config import NightshiftConfig, DEFAULT_CONFIG_TOML
    _print_header("Nightshift Config")
    repo = _repo(getattr(args, "repo", None))
    config_path = repo / "nightshift.toml"
    if args.write:
        if config_path.exists():
            _print_warn(f"Config already exists at {config_path}")
            _print_info("Use --force to overwrite.")
            return 1
        config_path.write_text(DEFAULT_CONFIG_TOML)
        _print_ok(f"Written default config to {config_path}")
        return 0
    if config_path.exists():
        cfg = NightshiftConfig.from_toml(config_path)
        if args.json:
            print(json.dumps(cfg.to_dict(), indent=2))
            return 0
        print(cfg.to_markdown())
    else:
        _print_warn(f"No nightshift.toml found at {config_path}")
        _print_info("Run `nightshift config --write` to create a default config.")
    return 0


# ---------------------------------------------------------------------------
# plugins
# ---------------------------------------------------------------------------


def cmd_plugins(args) -> int:
    """Manage plugin/hook registry from nightshift.toml."""
    from src.plugins import load_plugin_definitions, list_plugins, run_plugins, EXAMPLE_TOML_SNIPPET
    _print_header("Plugin Registry")
    repo = _repo(getattr(args, "repo", None))
    if getattr(args, "example", False):
        print(EXAMPLE_TOML_SNIPPET)
        return 0
    if getattr(args, "run", None):
        hook = args.run
        report = run_plugins(hook, repo_root=repo)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
            return 0
        print(report.to_markdown())
        _print_info(
            f"Hook: {hook}  ·  Ran: {report.plugins_run}  ·  "
            f"OK: {report.ok}  Warnings: {report.warnings}  Errors: {report.errors}"
        )
        return 0
    if args.json:
        defs = load_plugin_definitions(repo)
        print(json.dumps([d.to_dict() for d in defs], indent=2))
        return 0
    print(list_plugins(repo))
    return 0


# ---------------------------------------------------------------------------
# openapi
# ---------------------------------------------------------------------------


def cmd_openapi(args) -> int:
    """Generate OpenAPI 3.1 spec from all API endpoints."""
    from src.openapi import generate_openapi_spec
    _print_header("OpenAPI 3.1 Spec Generator")
    repo = _repo(getattr(args, "repo", None))
    spec = generate_openapi_spec(repo)
    if args.json or getattr(args, "format", "json") == "json":
        print(json.dumps(spec.to_dict(), indent=2))
        if getattr(args, "write", False):
            out = repo / "docs" / "openapi.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps(spec.to_dict(), indent=2), encoding="utf-8")
            _print_ok(f"JSON spec written to {out}")
        return 0
    if getattr(args, "format", None) == "yaml":
        print(spec.to_yaml())
        if getattr(args, "write", False):
            out = repo / "docs" / "openapi.yaml"
            out.parent.mkdir(exist_ok=True)
            out.write_text(spec.to_yaml(), encoding="utf-8")
            _print_ok(f"YAML spec written to {out}")
        return 0
    print(spec.to_markdown())
    _print_info(f"Endpoints: {len(spec.paths)}")
    return 0


# ---------------------------------------------------------------------------
# run (full pipeline)
# ---------------------------------------------------------------------------


def cmd_run(args) -> int:
    """Run the full end-of-session pipeline."""
    from src.stats import compute_stats
    from src.health import generate_health_report
    _print_header(f"Full Pipeline — Session {args.session}")
    repo = _repo(getattr(args, "repo", None))
    log_path = repo / "NIGHTSHIFT_LOG.md"
    _print_info("Running health analysis ...")
    health_report = generate_health_report(repo_path=repo)
    _print_ok(f"Health score: {health_report.overall_health_score}/100")
    _print_info("Computing stats ...")
    stats = compute_stats(repo_path=repo, log_path=log_path)
    _print_ok(f"Sessions tracked: {len(stats.sessions)}")
    _print_ok("Pipeline complete.")
    return 0
