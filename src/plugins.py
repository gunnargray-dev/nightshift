"""Plugin and hook architecture for Awake.

Allows third-party code to extend Awake behaviour without modifying the core
source.  Plugins are plain Python packages (or single modules) that expose a
``register(registry)`` callable.  The registry provides ``hook`` decorators
for well-known extension points.

Extension points
----------------
``on_scan_complete``
    Called after every ``awake health`` scan.  Receives the
    :class:`~health.HealthReport`.

``on_file_change``
    Called when a source file changes (used by the watch loop).  Receives
    the relative file path as a string.

``on_command``
    Called before any CLI sub-command executes.  Receives the command name
    and parsed ``argparse.Namespace``.

Public API
----------
- ``HookRegistry``  -- manages hooks for one extension point
- ``PluginRegistry`` -- top-level registry passed to ``register()``
- ``load_plugins(plugin_dirs)`` -> loaded plugin names
- ``get_registry()`` -> the global :class:`PluginRegistry`

CLI
---
    awake plugins [--list]
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Hook registry
# ---------------------------------------------------------------------------


class HookRegistry:
    """Manages a list of callables registered for a single hook name."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._hooks: list[Callable[..., Any]] = []

    # ------------------------------------------------------------------
    def register(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Register *fn* as a hook handler and return it unchanged."""
        self._hooks.append(fn)
        return fn

    def __call__(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        """Allow the registry to be used as a decorator."""
        return self.register(fn)

    # ------------------------------------------------------------------
    def fire(self, *args: Any, **kwargs: Any) -> list[Any]:
        """Call every registered handler with *args* / *kwargs*.

        Returns
        -------
        list
            Return values from each handler.
        """
        results: list[Any] = []
        for hook in self._hooks:
            try:
                results.append(hook(*args, **kwargs))
            except Exception as exc:  # noqa: BLE001
                # Plugins must not crash Awake
                print(f"[plugins] hook {self._name!r} raised: {exc}")
        return results

    @property
    def handlers(self) -> list[Callable[..., Any]]:
        """Return a copy of the registered handlers list."""
        return list(self._hooks)


# ---------------------------------------------------------------------------
# Plugin registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Top-level registry passed to each plugin's ``register()`` function."""

    def __init__(self) -> None:
        self.on_scan_complete: HookRegistry = HookRegistry("on_scan_complete")
        self.on_file_change: HookRegistry = HookRegistry("on_file_change")
        self.on_command: HookRegistry = HookRegistry("on_command")
        self._loaded: list[str] = []  # names of loaded plugins

    def hook(self, name: str) -> HookRegistry:
        """Return the :class:`HookRegistry` for *name*, creating it if needed.

        Parameters
        ----------
        name:
            Hook name.

        Returns
        -------
        HookRegistry
            The hook registry for the given name.
        """
        if not hasattr(self, name):
            setattr(self, name, HookRegistry(name))
        return getattr(self, name)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Global registry singleton
# ---------------------------------------------------------------------------

_REGISTRY: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Return the process-level :class:`PluginRegistry` singleton."""
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is None:
        _REGISTRY = PluginRegistry()
    return _REGISTRY


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------


def load_plugins(plugin_dirs: list[str | Path] | None = None) -> list[str]:
    """Discover and load plugins from *plugin_dirs*.

    Each directory is searched for Python packages / modules that expose a
    top-level ``register(registry: PluginRegistry) -> None`` callable.

    Parameters
    ----------
    plugin_dirs:
        Directories to search for plugins.  Defaults to ``["plugins"]``
        relative to the current working directory.

    Returns
    -------
    list[str]
        Names of successfully loaded plugins.
    """
    if plugin_dirs is None:
        plugin_dirs = [Path.cwd() / "plugins"]

    registry = get_registry()
    loaded: list[str] = []

    for plugin_dir in plugin_dirs:
        plugin_dir = Path(plugin_dir)
        if not plugin_dir.is_dir():
            continue

        for entry in sorted(plugin_dir.iterdir()):
            # Accept single-file plugins (foo.py) and packages (foo/__init__.py)
            if entry.is_file() and entry.suffix == ".py" and entry.stem != "__init__":
                module_name = f"awake_plugin_{entry.stem}"
                spec = importlib.util.spec_from_file_location(module_name, entry)
            elif entry.is_dir() and (entry / "__init__.py").exists():
                module_name = f"awake_plugin_{entry.name}"
                spec = importlib.util.spec_from_file_location(
                    module_name, entry / "__init__.py"
                )
            else:
                continue

            if spec is None or spec.loader is None:
                continue

            try:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                print(f"[plugins] failed to load {entry}: {exc}")
                continue

            register_fn = getattr(module, "register", None)
            if callable(register_fn):
                try:
                    register_fn(registry)
                    loaded.append(module_name)
                    registry._loaded.append(module_name)
                except Exception as exc:  # noqa: BLE001
                    print(f"[plugins] register() in {entry} raised: {exc}")

    return loaded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for plugin management.

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

    parser = argparse.ArgumentParser(
        prog="awake plugins",
        description="Manage Awake plugins.",
    )
    parser.add_argument("--list", action="store_true", help="List loaded plugins")
    args = parser.parse_args(argv)

    registry = get_registry()

    if args.list:
        if registry._loaded:
            for name in registry._loaded:
                print(name)
        else:
            print("No plugins loaded.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
