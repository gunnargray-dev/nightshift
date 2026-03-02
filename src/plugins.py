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
            lines += ["## Results", ""]
            for r in self.results:
                status_icon = {"ok": "✓", "warn": "⚠", "error": "✗"}.get(r.status, "?")
                lines.append(f"- {status_icon} **{r.plugin_name}** ({r.hook}): {r.message}")
                if r.error:
                    lines.append(f"  - Error: `{r.error}`")
        return "\n".join(lines)


def load_plugins_from_config(repo_root: Path) -> list[PluginDefinition]:
    """Discover and load plugin definitions from ``awake.toml``."""
    config_path = repo_root / "awake.toml"
    if not config_path.exists():
        return []
    if tomllib is None:
        return []
    with config_path.open("rb") as fh:
        config = tomllib.load(fh)
    raw_plugins = config.get("plugins", [])
    if not isinstance(raw_plugins, list):
        return []
    return [PluginDefinition.from_dict(p) for p in raw_plugins if isinstance(p, dict)]


def _load_plugin_function(plugin: PluginDefinition, repo_root: Path) -> Optional[Callable]:
    """Import and return the callable for a plugin definition."""
    module_path = repo_root / plugin.module.replace(".", "/")
    py_file = module_path.with_suffix(".py")
    if py_file.exists():
        spec = importlib.util.spec_from_file_location(plugin.module, py_file)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[plugin.module] = mod
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return getattr(mod, plugin.function, None)
    try:
        mod = importlib.import_module(plugin.module)
        return getattr(mod, plugin.function, None)
    except ImportError:
        return None


def run_plugins(
    plugins: list[PluginDefinition],
    hook: str,
    context: dict,
    repo_root: Path,
) -> PluginRunReport:
    """Execute all plugins registered for ``hook`` and return a report."""
    import time

    report = PluginRunReport(hook=hook)
    for plugin in plugins:
        if not plugin.enabled:
            report.skipped += 1
            continue
        if hook not in plugin.hooks:
            continue
        report.plugins_run += 1
        fn = _load_plugin_function(plugin, repo_root)
        if fn is None:
            report.errors += 1
            report.results.append(
                PluginResult(
                    plugin_name=plugin.name,
                    hook=hook,
                    status="error",
                    error=f"Could not load {plugin.module}.{plugin.function}",
                )
            )
            continue
        t0 = time.perf_counter()
        try:
            raw = fn(context)
        except Exception:
            elapsed = (time.perf_counter() - t0) * 1000
            tb = traceback.format_exc()
            report.errors += 1
            report.results.append(
                PluginResult(
                    plugin_name=plugin.name,
                    hook=hook,
                    status="error",
                    duration_ms=elapsed,
                    error=tb,
                )
            )
            continue
        elapsed = (time.perf_counter() - t0) * 1000
        status = raw.get("status", "ok") if isinstance(raw, dict) else "ok"
        message = raw.get("message", "") if isinstance(raw, dict) else str(raw)
        data = raw.get("data", {}) if isinstance(raw, dict) else {}
        result = PluginResult(
            plugin_name=plugin.name,
            hook=hook,
            status=status,
            message=message,
            data=data,
            duration_ms=elapsed,
        )
        report.results.append(result)
        if status == "ok":
            report.ok += 1
        elif status == "warn":
            report.warnings += 1
        else:
            report.errors += 1
    return report


def plugins_to_api_response(plugins: list[PluginDefinition]) -> dict:
    """Serialize plugin definitions to the /api/plugins JSON response format."""
    return {
        "plugins": [p.to_dict() for p in plugins],
        "total": len(plugins),
        "enabled": sum(1 for p in plugins if p.enabled),
        "hooks": sorted({h for p in plugins for h in p.hooks}),
    }
