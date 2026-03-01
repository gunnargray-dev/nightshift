"""Plugin registry and loader for Awake.

Provides a simple, file-based plugin system that lets third-party packages
extend Awake with custom commands, hooks, and middleware.

A plugin is any Python package that declares an entry point under the group
``awake.plugins``.  The registry discovers installed plugins at import time
and provides helper methods to list, load, and invoke them.

CLI
---
    awake plugins                  # List registered plugins
    awake plugins --json           # Emit JSON
    awake plugins --reload         # Force reload all plugins
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class PluginInfo:
    """Metadata about a single discovered plugin."""

    name: str
    version: str
    entry_point: str
    module: str
    loaded: bool = False
    error: str = ""
    commands: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the plugin info."""
        return asdict(self)


@dataclass
class PluginRegistry:
    """Registry of all discovered and loaded plugins."""

    plugins: list[PluginInfo] = field(default_factory=list)
    _loaded_modules: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict:
        """Return a dictionary representation of the plugin registry."""
        return {
            "total": len(self.plugins),
            "loaded": sum(1 for p in self.plugins if p.loaded),
            "failed": sum(1 for p in self.plugins if p.error),
            "plugins": [p.to_dict() for p in self.plugins],
        }

    def get(self, name: str) -> Optional[PluginInfo]:
        """Retrieve a plugin by name."""
        for p in self.plugins:
            if p.name == name:
                return p
        return None

    def loaded_module(self, name: str) -> Optional[Any]:
        """Return the loaded module object for a plugin."""
        return self._loaded_modules.get(name)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _discover_plugins() -> list[PluginInfo]:
    """Discover plugins via importlib.metadata entry points."""
    infos: list[PluginInfo] = []
    try:
        eps = importlib.metadata.entry_points(group="awake.plugins")
    except Exception:
        return []

    for ep in eps:
        dist = ep.dist
        version = "unknown"
        if dist is not None:
            try:
                version = dist.metadata["Version"]
            except Exception:
                pass
        infos.append(
            PluginInfo(
                name=ep.name,
                version=version,
                entry_point=str(ep.value),
                module=ep.value.split(":")[0],
            )
        )
    return infos


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _load_plugin(info: PluginInfo, registry: PluginRegistry) -> None:
    """Attempt to import and initialise a plugin module."""
    try:
        mod = importlib.import_module(info.module)
        registry._loaded_modules[info.name] = mod
        info.loaded = True

        # Introspect for commands and hooks
        if hasattr(mod, "AWAKE_COMMANDS"):
            info.commands = list(mod.AWAKE_COMMANDS)
        if hasattr(mod, "AWAKE_HOOKS"):
            info.hooks = list(mod.AWAKE_HOOKS)
    except Exception as exc:
        info.error = str(exc)
        info.loaded = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_plugins(force_reload: bool = False) -> PluginRegistry:
    """Discover and load all registered Awake plugins."""
    registry = PluginRegistry()
    infos = _discover_plugins()
    for info in infos:
        if force_reload and info.module in sys.modules:
            del sys.modules[info.module]
        _load_plugin(info, registry)
        registry.plugins.append(info)
    return registry


def list_plugins(registry: Optional[PluginRegistry] = None) -> PluginRegistry:
    """Return the plugin registry, loading plugins if needed."""
    if registry is None:
        registry = load_plugins()
    return registry


def invoke_hook(
    registry: PluginRegistry,
    hook_name: str,
    *args: Any,
    **kwargs: Any,
) -> list[Any]:
    """Invoke a named hook across all loaded plugins that declare it."""
    results: list[Any] = []
    for info in registry.plugins:
        if hook_name not in info.hooks:
            continue
        mod = registry.loaded_module(info.name)
        if mod is None:
            continue
        hook_fn: Optional[Callable] = getattr(mod, hook_name, None)
        if callable(hook_fn):
            try:
                results.append(hook_fn(*args, **kwargs))
            except Exception as exc:
                results.append({"error": str(exc)})
    return results


def render_markdown(registry: PluginRegistry) -> str:
    """Render the plugin list as a Markdown table."""
    lines = [
        "## Awake Plugins",
        "",
        "| Plugin | Version | Status | Commands | Hooks |",
        "|--------|---------|--------|----------|-------|",
    ]
    for p in registry.plugins:
        status = "loaded" if p.loaded else f"ERROR: {p.error[:40]}"
        cmds = ", ".join(p.commands) or "-"
        hooks = ", ".join(p.hooks) or "-"
        lines.append(f"| `{p.name}` | {p.version} | {status} | {cmds} | {hooks} |")
    if not registry.plugins:
        lines.append("| _No plugins installed_ | | | | |")
    return "\n".join(lines)
