"""Awake configuration system.

Reads ``awake.toml`` from the repo root to allow users to customize
thresholds, output formats, and other Awake behaviour without modifying
source code.

If no ``awake.toml`` exists the module returns built-in defaults so that
all subcommands work out of the box.

Usage
-----
    from src.config import load_config, save_default_config

    cfg = load_config(repo_root)          # returns AwakeConfig
    save_default_config(repo_root)        # writes awake.toml with defaults
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Config sections
# ---------------------------------------------------------------------------


@dataclass
class ThresholdsConfig:
    """Thresholds that drive pass/fail decisions in various analysers."""

    health_score_min: float = 60.0          # Below this: warn in doctor
    docstring_coverage_min: float = 0.5     # Below this: flag in health report
    max_line_length: int = 88               # PEP 8 relaxed limit
    todo_warn_threshold: int = 10           # Warn if repo has more TODOs than this
    coupling_instability_max: float = 0.8   # Max acceptable instability metric
    complexity_cc_warn: int = 10            # Cyclomatic complexity soft limit
    complexity_cc_critical: int = 20        # Cyclomatic complexity hard limit
    dep_outdated_warn: int = 3              # Warn if N or more deps are outdated

    def to_dict(self) -> dict:
        """Return a dictionary representation of the thresholds config"""
        return asdict(self)


@dataclass
class OutputConfig:
    """Controls default output format for CLI subcommands."""

    default_format: str = "markdown"    # markdown | json | plain
    color: bool = True                  # ANSI colour in terminal output
    unicode_symbols: bool = True        # Use ▲ ▼ = symbols

    def to_dict(self) -> dict:
        """Return a dictionary representation of the output config"""
        return asdict(self)


@dataclass
class SessionConfig:
    """Session-specific settings."""

    session_log_path: str = "AWAKE_LOG.md"
    docs_dir: str = "docs"
    src_dir: str = "src"

    def to_dict(self) -> dict:
        """Return a dictionary representation of the session config"""
        return asdict(self)


@dataclass
class AwakeConfig:
    """Top-level Awake configuration object.

    Populated from awake.toml or built-in defaults.
    """

    thresholds: ThresholdsConfig = field(default_factory=ThresholdsConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    _source: Optional[str] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a dictionary representation of the full config"""
        return {
            "thresholds": self.thresholds.to_dict(),
            "output": self.output.to_dict(),
            "session": self.session.to_dict(),
        }

    def to_markdown(self) -> str:
        """Render the config as a human-readable Markdown table."""
        lines = [
            "# Awake Configuration",
            "",
            "## Thresholds",
            "",
            "| Setting | Value |",
            "|---------|-------|",
        ]
        for k, v in self.thresholds.to_dict().items():
            label = k.replace("_", " ").title()
            lines.append(f"| {label} | {v} |")

        lines += [
            "",
            "## Output",
            "",
            "| Setting | Value |",
            "|---------|-------|",
        ]
        for k, v in self.output.to_dict().items():
            label = k.replace("_", " ").title()
            lines.append(f"| {label} | {v} |")

        lines += [
            "",
            "## Session",
            "",
            "| Setting | Value |",
            "|---------|-------|",
        ]
        for k, v in self.session.to_dict().items():
            label = k.replace("_", " ").title()
            lines.append(f"| {label} | {v} |")

        lines += ["", "---", ""]
        return "\n".join(lines)

    def to_toml(self) -> str:
        """Render the config as a TOML string."""
        d = self.to_dict()
        sections = []
        for section_name, section_data in d.items():
            sections.append(f"[{section_name}]")
            for k, v in section_data.items():
                if isinstance(v, bool):
                    val = "true" if v else "false"
                elif isinstance(v, str):
                    val = f'"{v}"'
                else:
                    val = str(v)
                sections.append(f"{k} = {val}")
            sections.append("")
        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Class method constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict) -> "AwakeConfig":
        """Build a config from a nested dict (as loaded from TOML)."""
        thresholds = ThresholdsConfig(
            **{
                k: v
                for k, v in data.get("thresholds", {}).items()
                if k in ThresholdsConfig.__dataclass_fields__  # type: ignore[attr-defined]
            }
        )
        output = OutputConfig(
            **{
                k: v
                for k, v in data.get("output", {}).items()
                if k in OutputConfig.__dataclass_fields__  # type: ignore[attr-defined]
            }
        )
        session = SessionConfig(
            **{
                k: v
                for k, v in data.get("session", {}).items()
                if k in SessionConfig.__dataclass_fields__  # type: ignore[attr-defined]
            }
        )
        return cls(thresholds=thresholds, output=output, session=session)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(repo_root: Optional[Path] = None) -> AwakeConfig:
    """Load configuration from ``awake.toml`` in the repo root.

    Falls back to built-in defaults if the file does not exist or cannot be
    parsed.

    Args:
        repo_root: Path to the repository root. Defaults to CWD.

    Returns:
        AwakeConfig populated from the TOML file or defaults.
    """
    root = repo_root or Path.cwd()
    config_path = root / "awake.toml"

    if not config_path.exists():
        cfg = AwakeConfig()
        cfg._source = None
        return cfg

    # Try native tomllib / tomli first
    if tomllib is not None:
        try:
            with config_path.open("rb") as f:
                data = tomllib.load(f)
            cfg = AwakeConfig.from_dict(data)
            cfg._source = str(config_path)
            return cfg
        except Exception:
            pass

    # Fallback: minimal hand-rolled TOML parser for simple key=value files
    try:
        data = _parse_simple_toml(config_path.read_text(encoding="utf-8"))
        cfg = AwakeConfig.from_dict(data)
        cfg._source = str(config_path)
        return cfg
    except Exception:
        pass

    cfg = AwakeConfig()
    cfg._source = None
    return cfg


def save_default_config(repo_root: Optional[Path] = None) -> Path:
    """Write the default configuration to ``awake.toml``.

    Does NOT overwrite an existing file.

    Args:
        repo_root: Path to the repository root. Defaults to CWD.

    Returns:
        Path to the written (or existing) config file.
    """
    root = repo_root or Path.cwd()
    config_path = root / "awake.toml"
    if not config_path.exists():
        default = AwakeConfig()
        config_path.write_text(default.to_toml(), encoding="utf-8")
    return config_path


# Convenience constant: the TOML text for a default configuration.
DEFAULT_CONFIG_TOML = AwakeConfig().to_toml()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_simple_toml(text: str) -> dict:
    """A minimal section-aware TOML parser for key = value files.

    Handles:
    - [section] headers
    - key = value  (string, int, float, bool)
    - Inline comments starting with #
    """
    result: dict = {}
    current_section: Optional[str] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Section header
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            result.setdefault(current_section, {})
            continue

        # Key = value
        if "=" in line:
            key, _, rest = line.partition("=")
            key = key.strip()
            rest = rest.strip()
            # Strip inline comments
            rest = rest.split(" #")[0].strip()
            value: object
            if rest.startswith('"') and rest.endswith('"'):
                value = rest[1:-1]
            elif rest.lower() == "true":
                value = True
            elif rest.lower() == "false":
                value = False
            else:
                try:
                    value = int(rest)
                except ValueError:
                    try:
                        value = float(rest)
                    except ValueError:
                        value = rest

            if current_section is not None:
                result[current_section][key] = value
            else:
                result[key] = value

    return result
