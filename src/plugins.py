"""Plugin and hook architecture for Awake.

Allows users to register custom Python callables that fire at well-defined
hook points in the Awake lifecycle. Plugins are discovered from:

1. Built-in hooks defined here (``on_session_start``, ``on_analysis_complete``,
   ``on_pr_opened``, etc.).
2. User-supplied modules listed in ``.awake/plugins.py`` or passed via
   ``--plugin`` on the CLI.

Design goals
------------
- Zero external dependencies.
- Hooks are synchronous; async wrappers can be added by callers.
- Errors in a hook are caught and logged, never allowed to crash the main flow.

CLI
---
    awake plugins              # List all registered hooks + handlers
    awake plugins --run <hook> # Fire a hook manually for testing
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import logging
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hook names (canonical)
# ---------------------------------------------------------------------------

HOOK_SESSION_START = "on_session_start"
HOOK_SESSION_END = "on_session_end"
HOOK_ANALYSIS_COMPLETE = "on_analysis_complete"
HOOK_PR_OPENED = "on_pr_opened"
HOOK_PR_MERGED = "on_pr_merged"
HOOK_HEALTH_DEGRADED = "on_health_degraded"
HOOK_HEALTH_IMPROVED = "on_health_improved"
HOOK_REFACTOR_APPLIED = "on_refactor_applied"
HOOK_README_UPDATED = "on_readme_updated"
HOOK_CHANGELOG_UPDATED = "on_changelog_updated"
HOOK_RELEASE_PUBLISHED = "on_release_published"
HOOK_ERROR = "on_error"

ALL_HOOKS: list[str] = [
    HOOK_SESSION_START,
    HOOK_SESSION_END,
    HOOK_ANALYSIS_COMPLETE,
    HOOK_PR_OPENED,
    HOOK_PR_MERGED,
    HOOK_HEALTH_DEGRADED,
    HOOK_HEALTH_IMPROVED,
    HOOK_REFACTOR_APPLIED,
    HOOK_README_UPDATED,
    HOOK_CHANGELOG_UPDATED,
    HOOK_RELEASE_PUBLISHED,
    HOOK_ERROR,
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class HookRegistration:
    """A single handler registered for a hook."""

    hook: str
    handler: Callable[..., Any]
    plugin_name: str = "unknown"
    priority: int = 0  # lower = runs first


@dataclass
class PluginRegistry:
    """Central registry of all hooks and their handlers."""

    _hooks: dict[str, list[HookRegistration]] = field(default_factory=dict)

    def register(self, hook: str, handler: Callable, plugin_name: str = "unknown", priority: int = 0) -> None:
        """Register *handler* under *hook*."""
        if hook not in ALL_HOOKS:
            raise ValueError(f"Unknown hook: {hook!r}.  Valid hooks: {ALL_HOOKS}")
        entry = HookRegistration(hook=hook, handler=handler, plugin_name=plugin_name, priority=priority)
        self._hooks.setdefault(hook, []).append(entry)
        self._hooks[hook].sort(key=lambda r: r.priority)
        logger.debug("Registered handler %s for hook %s (plugin=%s)", handler.__name__, hook, plugin_name)

    def fire(self, hook: str, **kwargs: Any) -> list[Any]:
        """Fire *hook*, passing **kwargs** to each handler. Returns list of results."""
        results = []
        for reg in self._hooks.get(hook, []):
            try:
                result = reg.handler(**kwargs)
                results.append(result)
            except Exception:
                logger.error(
                    "Plugin %s hook %s raised an error:\n%s",
                    reg.plugin_name, hook, traceback.format_exc(),
                )
        return results

    def list_hooks(self) -> dict[str, list[str]]:
        """Return a dict mapping hook name -> list of handler names."""
        return {
            hook: [r.handler.__name__ for r in regs]
            for hook, regs in self._hooks.items()
        }

    def to_dict(self) -> dict:
        """Return a serialisable dict summary of registered hooks."""
        return {
            hook: [
                {"handler": r.handler.__name__, "plugin": r.plugin_name, "priority": r.priority}
                for r in regs
            ]
            for hook, regs in self._hooks.items()
        }


# ---------------------------------------------------------------------------
# Global registry singleton
# ---------------------------------------------------------------------------

_registry: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    """Return (or create) the global ``PluginRegistry`` singleton."""
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry


def register(hook: str, handler: Callable, plugin_name: str = "user", priority: int = 0) -> None:
    """Convenience function: register *handler* for *hook* in the global registry."""
    get_registry().register(hook, handler, plugin_name=plugin_name, priority=priority)


def fire(hook: str, **kwargs: Any) -> list[Any]:
    """Convenience function: fire *hook* in the global registry."""
    return get_registry().fire(hook, **kwargs)


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------


def load_plugin_module(path: str | Path) -> Any:
    """Import a Python module from *path* and return it."""
    path = Path(path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Plugin file not found: {path}")
    spec = importlib.util.spec_from_file_location(path.stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


def discover_and_load(repo_path: str | Path) -> list[str]:
    """Auto-discover plugins in ``.awake/plugins.py`` and load them.

    Returns a list of loaded plugin module names.
    """
    repo = Path(repo_path).expanduser().resolve()
    plugin_file = repo / ".awake" / "plugins.py"
    loaded: list[str] = []
    if plugin_file.exists():
        try:
            mod = load_plugin_module(plugin_file)
            loaded.append(mod.__name__)
            logger.info("Loaded plugin: %s", plugin_file)
        except Exception:
            logger.error("Failed to load plugin %s:\n%s", plugin_file, traceback.format_exc())
    return loaded


def register_from_module(module: Any, plugin_name: str = "") -> int:
    """Scan *module* for functions named ``register_hooks`` and call it.

    Falls back to scanning for top-level functions decorated with
    ``@awake_hook`` if ``register_hooks`` is not found.

    Returns the number of handlers registered.
    """
    name = plugin_name or getattr(module, "__name__", "unknown")
    count = 0

    if hasattr(module, "register_hooks") and callable(module.register_hooks):
        try:
            module.register_hooks(get_registry())
            count += 1
        except Exception:
            logger.error("register_hooks() in %s failed:\n%s", name, traceback.format_exc())
        return count

    # Fallback: look for @awake_hook decorated functions
    for attr_name in dir(module):
        obj = getattr(module, attr_name, None)
        if callable(obj) and hasattr(obj, "_awake_hook"):
            hook = obj._awake_hook
            priority = getattr(obj, "_awake_priority", 0)
            try:
                get_registry().register(hook, obj, plugin_name=name, priority=priority)
                count += 1
            except Exception:
                logger.error("Failed to register %s for hook %s:\n%s", attr_name, hook, traceback.format_exc())

    return count


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def awake_hook(hook: str, priority: int = 0) -> Callable:
    """Decorator to mark a function as a handler for *hook*.

    Usage::

        @awake_hook("on_analysis_complete")
        def my_handler(session_id, report, **kwargs):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        fn._awake_hook = hook  # type: ignore[attr-defined]
        fn._awake_priority = priority  # type: ignore[attr-defined]
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(registry: PluginRegistry) -> str:
    """Render registry state as a Markdown table."""
    data = registry.to_dict()
    if not data:
        return "_No hooks registered._\n"
    lines = [
        "# Awake Plugin Registry",
        "",
        "| Hook | Handler | Plugin | Priority |",
        "|------|---------|--------|----------|",
    ]
    for hook in ALL_HOOKS:
        for reg in data.get(hook, []):
            lines.append(
                f"| `{hook}` | `{reg['handler']}` | {reg['plugin']} | {reg['priority']} |"
            )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    """CLI entry point for plugin management."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-plugins")
    p.add_argument("--repo", default=None, help="Repository root")
    p.add_argument("--run", metavar="HOOK", help="Fire a hook manually")
    p.add_argument("--json", action="store_true", help="Output JSON")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    discover_and_load(repo_path)
    reg = get_registry()

    if args.run:
        results = reg.fire(args.run)
        print(f"Fired hook '{args.run}', {len(results)} handler(s) ran.")
        return 0

    if args.json:
        print(json.dumps(reg.to_dict(), indent=2))
    else:
        print(render_markdown(reg))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
