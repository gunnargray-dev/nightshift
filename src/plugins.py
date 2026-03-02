"""Plugin loader for awake agent capabilities."""

import importlib
import importlib.util
import inspect
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, "Plugin"] = {}


@dataclass
class Plugin:
    """Represents a loaded plugin."""

    name: str
    module_path: str
    description: str = ""
    hooks: dict[str, Callable] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _extract_plugin_meta(module) -> tuple[str, dict[str, Callable]]:
    """Pull description and hook functions from a module."""
    description = getattr(module, "PLUGIN_DESCRIPTION", "") or ""
    hooks: dict[str, Callable] = {}

    for name, obj in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("hook_"):
            hooks[name[len("hook_"):]] = obj

    return description, hooks


def load_plugin(path: str, name: Optional[str] = None) -> Plugin:
    """
    Load a plugin from a .py file path.

    Args:
        path: Absolute or relative path to the plugin .py file.
        name: Optional override for the plugin name. Defaults to the stem of the file.

    Returns:
        A Plugin instance.
    """
    resolved = Path(path).resolve()
    plugin_name = name or resolved.stem

    spec = importlib.util.spec_from_file_location(plugin_name, resolved)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin from {resolved}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]

    description, hooks = _extract_plugin_meta(module)

    plugin = Plugin(
        name=plugin_name,
        module_path=str(resolved),
        description=description,
        hooks=hooks,
    )
    _REGISTRY[plugin_name] = plugin
    logger.info("Loaded plugin '%s' with hooks: %s", plugin_name, list(hooks))
    return plugin


def load_plugins_from_dir(directory: str) -> list[Plugin]:
    """
    Load all .py files in a directory as plugins.

    Args:
        directory: Path to the directory containing plugin files.

    Returns:
        List of loaded Plugin instances.
    """
    plugins = []
    for filepath in sorted(Path(directory).glob("*.py")):
        if filepath.name.startswith("_"):
            continue
        try:
            plugins.append(load_plugin(str(filepath)))
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to load plugin %s: %s", filepath.name, exc)
    return plugins


def get_plugin(name: str) -> Optional[Plugin]:
    """Return a registered plugin by name, or None."""
    return _REGISTRY.get(name)


def list_plugins() -> list[Plugin]:
    """Return all registered plugins."""
    return list(_REGISTRY.values())


def call_hook(
    hook_name: str,
    *args: Any,
    plugin_name: Optional[str] = None,
    **kwargs: Any,
) -> list[Any]:
    """
    Call a named hook on all registered plugins (or a specific one).

    Args:
        hook_name: The hook to invoke (without 'hook_' prefix).
        plugin_name: If given, only call the hook on this plugin.

    Returns:
        List of return values from each hook invocation.
    """
    plugins = [_REGISTRY[plugin_name]] if plugin_name else list(_REGISTRY.values())
    results = []
    for plugin in plugins:
        hook = plugin.hooks.get(hook_name)
        if hook:
            try:
                results.append(hook(*args, **kwargs))
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Hook '%s' in plugin '%s' raised: %s", hook_name, plugin.name, exc
                )
    return results


def unload_plugin(name: str) -> bool:
    """
    Remove a plugin from the registry.

    Args:
        name: Plugin name to remove.

    Returns:
        True if removed, False if not found.
    """
    if name in _REGISTRY:
        del _REGISTRY[name]
        logger.info("Unloaded plugin '%s'", name)
        return True
    return False


def reload_plugin(path: str, name: Optional[str] = None) -> Plugin:
    """
    Reload a plugin from disk, replacing any existing registration.

    Args:
        path: Path to the plugin file.
        name: Optional name override.

    Returns:
        The reloaded Plugin instance.
    """
    resolved = Path(path).resolve()
    plugin_name = name or resolved.stem
    unload_plugin(plugin_name)
    return load_plugin(path, name=plugin_name)
