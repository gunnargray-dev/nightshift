"""Plugin and hook architecture for Awake.

Allows users to register custom Python analyzer functions via ``awake.toml``.
These plugins are discovered, loaded, and executed alongside the built-in analyzers.

Configuration example (awake.toml)
----------------------------------------
[[plugins]]
name = "my_complexity_check"
module = "scripts.custom_checks"
function = "check_complexity"
description = "Custom complexity thresholds for our team"
hooks = ["pre_health", "post_health"]

[[plugins]]
name = "secret_scanner"
module = "scripts.security"
function = "scan_secrets"
hooks = ["pre_run"]

Plugin contract
---------------
Every plugin function receives a single ``PluginContext`` dict and returns a
``PluginResult`` dict.  This keeps the interface simple and forward-compatible.

    def my_plugin(ctx: dict) -> dict:
        # ctx keys: repo_path, config, session_number, trigger_hook
        return {
            "status": "ok",          # ok | warn | error
            "message": "All clear",
            "data": {},            # any JSON-serialisable payload
        }
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


@dataclass
class PluginDefinition:
    """A plugin entry as declared in awake.toml."""
    name: str
    module: str
    function: str
    description: str = ""
    hooks: list[str] = field(default_factory=list)
    enabled: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> "PluginDefinition":
        """Construct a PluginDefinition from a raw TOML dictionary"""
        return cls(
            name=d.get("name", "unknown"),
            module=d.get("module", ""),
            function=d.get("function", ""),
            description=d.get("description", ""),
            hooks=d.get("hooks", []),
            enabled=d.get("enabled", True),
        )

    def to_dict(self) -> dict:
        """Return a dictionary representation of the plugin definition"""
        return asdict(self)


@dataclass
class PluginResult:
    """Result returned by a plugin execution."""
    plugin_name: str
    hook: str
    status: str
    message: str = ""
    data: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        """Return a dictionary representation of the plugin result"""
        return asdict(self)


@dataclass
class PluginRunReport:
    """Aggregated results for all plugins run against a hook."""
    hook: str
    plugins_run: int = 0
    ok: int = 0
    warnings: int = 0
    errors: int = 0
    skipped: int = 0
    results: list[PluginResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the run report"""
        return asdict(self)

    def to_markdown(self) -> str:
        """Render the run report as a Markdown summary table"""
        lines = [
            f"## Plugin Run Report -- Hook: `{self.hook}`",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Plugins run | {self.plugins_run} |",
            f"| OK | {self.ok} |",
            f"| Warnings | {self.warnings} |",
            f"| Errors | {self.errors} |",
            f"| Skipped | {self.skipped} |",
            "",
        ]
        if self.results:
            lines += ["### Results", ""]
            for r in self.results:
                icon = {"ok": "[OK]", "warn": "[WARN]", "error": "[ERR]", "skipped": "[SKIP]"}.get(r.status, "[?]")
                lines.append(f"{icon} **{r.plugin_name}** ({r.duration_ms:.1f}ms) -- {r.message}")
                if r.error:
                    lines.append(f"  > Error: `{r.error}`")
        return "\n".join(lines)


def load_plugin_definitions(repo_root: Path) -> list[PluginDefinition]:
    """Read [[plugins]] entries from awake.toml."""
    toml_path = repo_root / "awake.toml"
    if not toml_path.exists() or tomllib is None:
        return []
    with toml_path.open("rb") as f:
        config = tomllib.load(f)
    raw_plugins = config.get("plugins", [])
    return [PluginDefinition.from_dict(p) for p in raw_plugins]


def _load_function(defn: PluginDefinition, repo_root: Path) -> Optional[Callable]:
    """Import a plugin module and retrieve the registered function."""
    module_name = defn.module
    func_name = defn.function
    candidate = repo_root / module_name.replace(".", "/")
    if not candidate.suffix:
        candidate = candidate.with_suffix(".py")
    if candidate.exists():
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
            return getattr(mod, func_name, None)
    repo_str = str(repo_root)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    try:
        mod = importlib.import_module(module_name)
        return getattr(mod, func_name, None)
    except ImportError:
        return None


def run_plugins(
    hook: str,
    *,
    repo_root: Path,
    session_number: int = 0,
    extra_context: Optional[dict] = None,
) -> PluginRunReport:
    """Discover and run all enabled plugins registered for *hook*."""
    import time
    definitions = load_plugin_definitions(repo_root)
    report = PluginRunReport(hook=hook)
    ctx: dict[str, Any] = {
        "repo_path": str(repo_root),
        "session_number": session_number,
        "trigger_hook": hook,
    }
    if extra_context:
        ctx.update(extra_context)
    for defn in definitions:
        if not defn.enabled:
            report.skipped += 1
            report.results.append(PluginResult(
                plugin_name=defn.name, hook=hook, status="skipped",
                message="Plugin disabled in awake.toml",
            ))
            continue
        if hook not in defn.hooks and defn.hooks:
            continue
        report.plugins_run += 1
        func = _load_function(defn, repo_root)
        if func is None:
            report.errors += 1
            report.results.append(PluginResult(
                plugin_name=defn.name, hook=hook, status="error",
                error=f"Could not load {defn.module}.{defn.function}",
            ))
            continue
        t0 = time.perf_counter()
        try:
            raw = func(dict(ctx))
            duration_ms = (time.perf_counter() - t0) * 1000
            if not isinstance(raw, dict):
                raw = {"status": "ok", "message": str(raw), "data": {}}
            status = raw.get("status", "ok")
            result = PluginResult(
                plugin_name=defn.name,
                hook=hook,
                status=status,
                message=raw.get("message", ""),
                data=raw.get("data", {}),
                duration_ms=duration_ms,
            )
            if status == "warn":
                report.warnings += 1
            elif status == "error":
                report.errors += 1
            else:
                report.ok += 1
            report.results.append(result)
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            report.errors += 1
            report.results.append(PluginResult(
                plugin_name=defn.name,
                hook=hook,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=duration_ms,
            ))
    return report


def list_plugins(repo_root: Path) -> str:
    """Return a Markdown table of registered plugins."""
    definitions = load_plugin_definitions(repo_root)
    if not definitions:
        return "_No plugins registered in awake.toml_\n"
    lines = [
        "| Name | Module | Function | Hooks | Enabled |",
        "|------|--------|----------|-------|---------|",
    ]
    for d in definitions:
        hooks_str = ", ".join(f"`{h}`" for h in d.hooks) if d.hooks else "_any_"
        enabled_str = "[YES]" if d.enabled else "[NO]"
        lines.append(
            f"| `{d.name}` | `{d.module}` | `{d.function}` | {hooks_str} | {enabled_str} |"
        )
    return "\n".join(lines)


EXAMPLE_TOML_SNIPPET = """
# Example plugin configuration in awake.toml
#
# [[plugins]]
# name        = "team_style_check"
# module      = "scripts.style"
# function    = "check_style"
# description = "Enforce team-specific style rules beyond PEP 8"
# hooks       = ["pre_health", "pre_run"]
# enabled     = true
#
# Plugin function signature:
#   def my_plugin(ctx: dict) -> dict:
#       # ctx: {repo_path, session_number, trigger_hook, ...}
#       return {"status": "ok", "message": "...", "data": {}}
""".strip()
