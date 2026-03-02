"""Plugin management for Awake."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class PluginMetadata:
    """Metadata for an installed plugin."""

    name: str
    version: str = "0.0.0"
    description: str = ""
    author: str = ""
    entry_point: str = ""


@dataclass
class Plugin:
    """A loaded Awake plugin."""

    metadata: PluginMetadata
    module: Any = None
    hooks: dict[str, Callable] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version

    @property
    def description(self) -> str:
        return self.metadata.description


class PluginManager:
    """Manages loading, unloading, and querying plugins."""

    DEFAULT_DIR = Path.home() / ".awake" / "plugins"

    def __init__(self, plugin_dir: Optional[Path] = None) -> None:
        self.plugin_dir = plugin_dir or self.DEFAULT_DIR
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, Plugin] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        """Load all plugins found in the plugin directory."""
        for path in sorted(self.plugin_dir.glob("*.py")):
            try:
                self._load_from_path(path)
            except Exception:  # pragma: no cover
                pass

    def _load_from_path(self, path: Path) -> Plugin:
        """Load a single plugin from a .py file."""
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:  # pragma: no cover
            raise ImportError(f"Cannot load plugin from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        metadata = PluginMetadata(
            name=getattr(module, "__plugin_name__", path.stem),
            version=getattr(module, "__version__", "0.0.0"),
            description=getattr(module, "__description__", ""),
            author=getattr(module, "__author__", ""),
        )
        hooks: dict[str, Callable] = {}
        for attr in dir(module):
            fn = getattr(module, attr)
            if callable(fn) and getattr(fn, "_awake_hook", False):
                hooks[attr] = fn

        plugin = Plugin(metadata=metadata, module=module, hooks=hooks)
        self._plugins[metadata.name] = plugin
        return plugin

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[Plugin]:
        """Return all loaded plugins."""
        return list(self._plugins.values())

    def get(self, name: str) -> Optional[Plugin]:
        """Return a plugin by name, or None."""
        return self._plugins.get(name)

    def install(self, name: str) -> None:
        """Stub: install a plugin by name (would fetch from registry in production)."""
        # In production this would download from a plugin registry
        raise NotImplementedError(f"Plugin registry install not yet implemented for {name!r}")

    def uninstall(self, name: str) -> None:
        """Remove a plugin by name."""
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            raise KeyError(f"Plugin {name!r} not found")
        # Remove the .py file
        candidate = self.plugin_dir / f"{name}.py"
        if candidate.exists():
            candidate.unlink()
        # Remove from sys.modules
        sys.modules.pop(name, None)

    def call_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """Call a named hook on all plugins that implement it."""
        results = []
        for plugin in self._plugins.values():
            fn = plugin.hooks.get(hook_name)
            if fn is not None:
                results.append(fn(*args, **kwargs))
        return results
