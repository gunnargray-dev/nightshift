"""Nightshift Config System — nightshift.toml reader and writer.

Allows users to customize thresholds, output formats, and behavior via a
``nightshift.toml`` file in the repository root.  Falls back to hardcoded
defaults when no config file is present.

Public API
----------
load_config(repo_path) -> NightshiftConfig
save_default_config(repo_path) -> Path
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Default values (canonical source of truth)
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    "output": {
        "format": "markdown",   # markdown | json | html
        "color": True,
        "emoji": True,
    },
    "complexity": {
        "hot_spot_threshold": 10,
        "critical_threshold": 20,
        "warn_on_critical": True,
    },
    "coupling": {
        "instability_warn": 0.8,
        "min_module_connections": 1,
    },
    "health": {
        "min_score": 60,
        "fail_score": 40,
    },
    "coverage": {
        "warn_threshold": 70,
        "fail_threshold": 50,
    },
    "todos": {
        "stale_sessions": 2,
        "max_age_warn": 5,
    },
    "export": {
        "default_formats": ["json", "markdown", "html"],
        "output_dir": "docs/exports",
    },
    "session": {
        "current": 12,
    },
}


@dataclass
class OutputConfig:
    format: str = "markdown"
    color: bool = True
    emoji: bool = True


@dataclass
class ComplexityConfig:
    hot_spot_threshold: int = 10
    critical_threshold: int = 20
    warn_on_critical: bool = True


@dataclass
class CouplingConfig:
    instability_warn: float = 0.8
    min_module_connections: int = 1


@dataclass
class HealthConfig:
    min_score: int = 60
    fail_score: int = 40


@dataclass
class CoverageConfig:
    warn_threshold: int = 70
    fail_threshold: int = 50


@dataclass
class TodosConfig:
    stale_sessions: int = 2
    max_age_warn: int = 5


@dataclass
class ExportConfig:
    default_formats: list[str] = field(default_factory=lambda: ["json", "markdown", "html"])
    output_dir: str = "docs/exports"


@dataclass
class SessionConfig:
    current: int = 12


@dataclass
class NightshiftConfig:
    output: OutputConfig = field(default_factory=OutputConfig)
    complexity: ComplexityConfig = field(default_factory=ComplexityConfig)
    coupling: CouplingConfig = field(default_factory=CouplingConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    coverage: CoverageConfig = field(default_factory=CoverageConfig)
    todos: TodosConfig = field(default_factory=TodosConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    session: SessionConfig = field(default_factory=SessionConfig)

    _source: Optional[Path] = field(default=None, compare=False, repr=False)

    @classmethod
    def defaults(cls) -> "NightshiftConfig":
        """Return a config populated entirely from built-in defaults."""
        return cls()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("_source", None)
        return d

    def to_toml(self) -> str:
        """Render config as TOML (hand-crafted, no tomllib dependency)."""
        lines = [
            "# nightshift.toml — Configuration for the Nightshift dev system",
            "# Generated automatically. Edit to customize thresholds and behavior.",
            "",
        ]
        d = self.to_dict()
        for section, values in d.items():
            if not isinstance(values, dict):
                continue
            lines.append(f"[{section}]")
            for key, val in values.items():
                if isinstance(val, bool):
                    lines.append(f"{key} = {'true' if val else 'false'}")
                elif isinstance(val, list):
                    items = ", ".join(f'"{v}"' for v in val)
                    lines.append(f'{key} = [{items}]')
                elif isinstance(val, str):
                    lines.append(f'{key} = "{val}"')
                else:
                    lines.append(f"{key} = {val}")
            lines.append("")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render current config as a Markdown table for display."""
        lines = [
            "# Nightshift Configuration",
            "",
            f"*Source: {self._source or 'built-in defaults'}*",
            "",
        ]
        d = self.to_dict()
        for section, values in d.items():
            if not isinstance(values, dict):
                continue
            lines.append(f"## [{section}]")
            lines.append("")
            lines.append("| Key | Value |")
            lines.append("| --- | ----- |")
            for key, val in values.items():
                if isinstance(val, list):
                    val_str = ", ".join(str(v) for v in val)
                else:
                    val_str = str(val)
                lines.append(f"| `{key}` | `{val_str}` |")
            lines.append("")
        return "\n".join(lines)


def _parse_toml_value(raw: str) -> Any:
    """Parse a single TOML value string into a Python object."""
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        items = re.split(r',\s*', inner)
        return [_parse_toml_value(i.strip()) for i in items if i.strip()]
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _parse_toml(text: str) -> dict[str, Any]:
    """Minimal TOML parser — handles [sections] and key = value pairs."""
    result: dict[str, Any] = {}
    current_section: Optional[str] = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            result.setdefault(current_section, {})
            continue
        if "=" in line:
            key, _, raw_val = line.partition("=")
            key = key.strip()
            raw_val = raw_val.strip()
            if " #" in raw_val and not raw_val.startswith('"'):
                raw_val = raw_val[:raw_val.index(" #")].strip()
            val = _parse_toml_value(raw_val)
            if current_section:
                result.setdefault(current_section, {})[key] = val
            else:
                result[key] = val
    return result


def _merge_dict(base: dict, override: dict) -> dict:
    """Deep-merge override into base, returning a new dict."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _merge_dict(result[key], val)
        else:
            result[key] = val
    return result


def load_config(repo_path: Optional[Path] = None) -> NightshiftConfig:
    """Load config from nightshift.toml in repo_path, falling back to defaults."""
    if repo_path is None:
        repo_path = Path.cwd()
    config_path = repo_path / "nightshift.toml"
    raw = dict(DEFAULTS)
    source: Optional[Path] = None
    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
            file_data = _parse_toml(text)
            raw = _merge_dict(raw, file_data)
            source = config_path
        except Exception:
            pass
    cfg = NightshiftConfig(
        output=OutputConfig(
            format=raw["output"].get("format", "markdown"),
            color=raw["output"].get("color", True),
            emoji=raw["output"].get("emoji", True),
        ),
        complexity=ComplexityConfig(
            hot_spot_threshold=raw["complexity"].get("hot_spot_threshold", 10),
            critical_threshold=raw["complexity"].get("critical_threshold", 20),
            warn_on_critical=raw["complexity"].get("warn_on_critical", True),
        ),
        coupling=CouplingConfig(
            instability_warn=raw["coupling"].get("instability_warn", 0.8),
            min_module_connections=raw["coupling"].get("min_module_connections", 1),
        ),
        health=HealthConfig(
            min_score=raw["health"].get("min_score", 60),
            fail_score=raw["health"].get("fail_score", 40),
        ),
        coverage=CoverageConfig(
            warn_threshold=raw["coverage"].get("warn_threshold", 70),
            fail_threshold=raw["coverage"].get("fail_threshold", 50),
        ),
        todos=TodosConfig(
            stale_sessions=raw["todos"].get("stale_sessions", 2),
            max_age_warn=raw["todos"].get("max_age_warn", 5),
        ),
        export=ExportConfig(
            default_formats=raw["export"].get("default_formats", ["json", "markdown", "html"]),
            output_dir=raw["export"].get("output_dir", "docs/exports"),
        ),
        session=SessionConfig(
            current=raw["session"].get("current", 12),
        ),
    )
    cfg._source = source
    return cfg


def save_default_config(repo_path: Path) -> Path:
    """Write nightshift.toml with default values to repo_path."""
    config_path = repo_path / "nightshift.toml"
    cfg = NightshiftConfig.defaults()
    config_path.write_text(cfg.to_toml(), encoding="utf-8")
    return config_path
