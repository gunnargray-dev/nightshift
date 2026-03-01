"""Repo DNA Fingerprint — a unique visual signature based on code patterns.

Every codebase has a "DNA" — the cumulative fingerprint of its style, structure,
and evolution.  This module analyses src/ and generates a visual ASCII/Unicode
fingerprint that encodes:

  Channel 1 (Complexity  ████████░░)  — average cyclomatic complexity profile
  Channel 2 (Coupling    ▓▓▓▓░░░░░░)  — import density / coupling ratio
  Channel 3 (Docstrings  ▓▓▓▓▓▓░░░░)  — average docstring coverage
  Channel 4 (Test depth  ████████████) — test-to-source ratio
  Channel 5 (File sizes  ░░░▓▓▓███░)  — line count distribution
  Channel 6 (Age spread  ████░░░░░░░)  — session age entropy

These six channels are encoded into a 12×6 Unicode block matrix that forms
the repo's "DNA band".  Like a real genetic fingerprint, each band is unique
to its codebase and changes as the code evolves.

A hex digest (8 chars) is also computed from a deterministic hash of all
channel values, giving a short unique identifier like ``A3F7C901``.

Additionally, a richer sparkline chart shows per-file complexity, letting
engineers quickly spot hot-spots.

The fingerprint is entirely reproducible — run it twice on the same codebase
and you'll get the same result.  This makes it useful for tracking identity
across sessions (e.g., "the fingerprint changed — something structural shifted").

Output:
  - Terminal ANSI coloured block art
  - Markdown embedded block art (no ANSI)
  - JSON (channel values + hex digest)

CLI:
    awake dna [--write] [--json]
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Block characters for visual rendering
# ---------------------------------------------------------------------------

_FILL_CHARS  = " ░▒▓█"          # 5 levels: empty → full
_SPARK_CHARS = "▁▂▃▄▅▆▇█"       # 8 levels for sparklines

_CHANNEL_LABELS = [
    "Complexity ",
    "Coupling   ",
    "Doc Cover  ",
    "Test Depth ",
    "File Sizes ",
    "Age Spread ",
]

_CHANNEL_DESCRIPTIONS = [
    "Average cyclomatic complexity across all functions (lower = better)",
    "Import density and inter-module coupling ratio",
    "Average docstring coverage across all public functions",
    "Test function count relative to source symbols",
    "Line count distribution across source files",
    "Session age entropy — how evenly distributed are module ages?",
]

_BAND_WIDTH = 16    # characters per band strip


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DnaChannel:
    """A single channel in the DNA fingerprint."""

    label: str
    value: float          # 0.0–1.0 normalised
    raw_value: float      # original metric value
    description: str

    def to_dict(self) -> dict:
        """Return a dictionary representation of this channel"""
        return asdict(self)

    def render_bar(self, width: int = _BAND_WIDTH) -> str:
        """Render a filled progress bar of given width."""
        filled = round(self.value * width)
        filled = max(0, min(width, filled))
        # Use gradient fill characters
        if filled == 0:
            bar = _FILL_CHARS[0] * width
        elif filled == width:
            bar = _FILL_CHARS[4] * width
        else:
            bar = _FILL_CHARS[4] * (filled - 1) + _FILL_CHARS[2] + _FILL_CHARS[0] * (width - filled)
        return bar


@dataclass
class RepoDna:
    """The full DNA fingerprint of the repository."""

    repo_name: str
    generated_at: str = ""
    hex_digest: str = ""          # 8-char hex identifier
    channels: list[DnaChannel] = field(default_factory=list)
    per_file_complexity: list[tuple[str, float]] = field(default_factory=list)
    total_modules: int = 0
    total_lines: int = 0

    def to_dict(self) -> dict:
        """Return a dictionary representation of the full DNA fingerprint"""
        d = {
            "repo_name": self.repo_name,
            "generated_at": self.generated_at,
            "hex_digest": self.hex_digest,
            "total_modules": self.total_modules,
            "total_lines": self.total_lines,
            "channels": [c.to_dict() for c in self.channels],
            "per_file_complexity": self.per_file_complexity,
        }
        return d

    def to_json(self) -> str:
        """Serialize the DNA fingerprint to a JSON string"""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def _render_band(self) -> list[str]:
        """Render the 6-channel DNA band as a list of text rows."""
        rows = []
        for ch in self.channels:
            bar = ch.render_bar(_BAND_WIDTH)
            pct = round(ch.value * 100)
            rows.append(f"  {ch.label}  │{bar}│  {pct:3d}%")
        return rows

    def _render_sparkline_chart(self) -> list[str]:
        """Render per-file complexity as a horizontal sparkline chart."""
        if not self.per_file_complexity:
            return []

        values = [v for _, v in self.per_file_complexity]
        lo, hi = min(values), max(values)
        rows = ["  Per-file complexity:", ""]

        for name, v in self.per_file_complexity:
            if lo == hi:
                bar_char = _SPARK_CHARS[4]
            else:
                idx = round((v - lo) / (hi - lo) * (len(_SPARK_CHARS) - 1))
                bar_char = _SPARK_CHARS[idx]
            bar_width = max(1, round((v / max(hi, 1)) * 20))
            bar = bar_char * bar_width
            rows.append(f"  {name:<20s}  {bar}  {v:.1f}")

        return rows

    def _compute_matrix(self) -> list[str]:
        """Render a compact 6×16 visual DNA matrix."""
        rows = []
        for i, ch in enumerate(self.channels):
            # Each row is a gradient bar showing the channel value
            bar = ch.render_bar(_BAND_WIDTH)
            rows.append(bar)
        return rows

    def to_markdown(self) -> str:
        """Render the DNA fingerprint as a Markdown document."""
        from datetime import datetime

        lines = [
            "# Repo DNA Fingerprint",
            "",
            f"**Repository:** {self.repo_name}  ",
            f"**Generated:** {self.generated_at}  ",
            f"**Fingerprint ID:** `{self.hex_digest}`  ",
            f"**Modules:** {self.total_modules}  **Lines:** {self.total_lines:,}",
            "",
            "## DNA Band",
            "",
            "```",
            f"  ╔═════════════════════════════════════╗",
            f"  ║  🧬  {self.repo_name:<28s} ║",
            f"  ║  ID: {self.hex_digest:<28s} ║",
            f"  ╠═════════════════════════════════════╣",
        ]

        for row in self._render_band():
            lines.append(row)

        lines += [
            "  ╚═════════════════════════════════════╝",
            "```",
            "",
            "## Channel Breakdown",
            "",
            "| Channel | Value | Raw Metric | Description |",
            "|---------|-------|------------|-------------|",
        ]

        for ch in self.channels:
            pct = f"{ch.value*100:.0f}%"
            raw = f"{ch.raw_value:.2f}"
            lines.append(f"| **{ch.label.strip()}** | {pct} | {raw} | {ch.description} |")

        lines += [""]

        # Sparkline chart
        spark_rows = self._render_sparkline_chart()
        if spark_rows:
            lines += [
                "## Per-File Complexity Profile",
                "",
                "```",
            ]
            lines.extend(spark_rows)
            lines += ["```", ""]

        lines += [
            "## What This Fingerprint Means",
            "",
            _generate_fingerprint_narrative(self),
            "",
            "---",
            "",
            f"*The fingerprint ID `{self.hex_digest}` changes whenever the codebase's "
            f"structural profile shifts — use it to detect architectural drift across sessions.*",
            "",
        ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Metric collection
# ---------------------------------------------------------------------------


def _compute_avg_complexity(src_dir: Path) -> tuple[float, list[tuple[str, float]]]:
    """Compute average cyclomatic complexity per file.

    Returns:
        (global_avg, [(filename, avg_cc), ...])
    """
    results: list[tuple[str, float]] = []

    for f in sorted(src_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            results.append((f.stem, 5.0))
            continue

        ccs: list[float] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = 1 + sum(
                    1
                    for child in ast.walk(node)
                    if isinstance(
                        child,
                        (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler,
                         ast.With, ast.Assert),
                    )
                )
                ccs.append(float(cc))

        avg = sum(ccs) / len(ccs) if ccs else 1.0
        results.append((f.stem, avg))

    if not results:
        return 1.0, []

    global_avg = sum(v for _, v in results) / len(results)
    return global_avg, results


def _compute_coupling_ratio(src_dir: Path) -> float:
    """Compute the average ratio of src imports to total imports per file."""
    ratios: list[float] = []

    for f in sorted(src_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue

        total_imports = 0
        src_imports = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                total_imports += 1
                if node.module and node.module.startswith("src."):
                    src_imports += 1
            elif isinstance(node, ast.Import):
                total_imports += 1

        if total_imports > 0:
            ratios.append(src_imports / total_imports)
        else:
            ratios.append(0.0)

    return sum(ratios) / len(ratios) if ratios else 0.0


def _compute_docstring_coverage(src_dir: Path) -> float:
    """Compute average docstring coverage across all public functions."""
    covered = 0
    total = 0

    for f in sorted(src_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    total += 1
                    if ast.get_docstring(node):
                        covered += 1

    return covered / total if total > 0 else 0.0


def _compute_test_depth(src_dir: Path, tests_dir: Path) -> float:
    """Compute the ratio of test functions to public source functions."""
    src_symbols = 0
    test_fns = 0

    for f in sorted(src_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    src_symbols += 1

    for f in sorted(tests_dir.glob("test_*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                test_fns += 1

    if src_symbols == 0:
        return 0.0
    ratio = test_fns / src_symbols
    # Normalise: ratio >= 5.0 = full score
    return min(ratio / 5.0, 1.0)


def _compute_file_size_entropy(src_dir: Path) -> float:
    """Compute entropy of file size distribution (higher = more uniform).

    0.0 = all weight in one file (monolith)
    1.0 = perfectly uniform distribution
    """
    sizes = []
    for f in sorted(src_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        sizes.append(len(f.read_bytes()))

    if not sizes or len(sizes) == 1:
        return 0.5

    total = sum(sizes)
    if total == 0:
        return 0.5

    probs = [s / total for s in sizes]
    max_entropy = math.log(len(sizes))
    if max_entropy == 0:
        return 1.0

    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    return min(entropy / max_entropy, 1.0)


def _compute_age_entropy(log_path: Path, src_dir: Path) -> float:
    """Compute entropy of module age distribution.

    1.0 = modules were added evenly across all sessions (well-paced growth)
    0.0 = all modules added in one session (burst)
    """
    if not log_path.exists():
        return 0.5

    content = log_path.read_text(encoding="utf-8")
    session_headers = list(re.finditer(r"^## Session (\d+)", content, re.MULTILINE))
    if not session_headers:
        return 0.5

    last_session = int(session_headers[-1].group(1))
    session_counts: dict[int, int] = {i: 0 for i in range(1, last_session + 1)}

    for f in sorted(src_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        name = f.stem
        pattern = re.compile(rf"src/{re.escape(name)}\.py", re.IGNORECASE)
        for m_hdr in session_headers:
            session_num = int(m_hdr.group(1))
            idx = session_headers.index(m_hdr)
            end = (
                session_headers[idx + 1].start()
                if idx + 1 < len(session_headers)
                else len(content)
            )
            section = content[m_hdr.start():end]
            if pattern.search(section):
                session_counts[session_num] += 1
                break

    counts = [v for v in session_counts.values() if v > 0]
    if len(counts) <= 1:
        return 0.2  # all in one session

    total = sum(counts)
    probs = [c / total for c in counts]
    max_entropy = math.log(len(counts))
    if max_entropy == 0:
        return 0.5
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    return min(entropy / max_entropy, 1.0)


def _compute_hex_digest(channels: list[DnaChannel]) -> str:
    """Compute a deterministic 8-char hex digest from channel values."""
    # Use the channel values as a key
    channel_str = "|".join(f"{ch.label.strip()}:{ch.raw_value:.4f}" for ch in channels)
    digest = hashlib.sha256(channel_str.encode()).hexdigest()[:8].upper()
    return digest


def _generate_fingerprint_narrative(dna: "RepoDna") -> str:
    """Generate a prose interpretation of the DNA fingerprint."""
    # Interpret each channel
    parts = []

    ch_map = {ch.label.strip(): ch for ch in dna.channels}

    cmp = ch_map.get("Complexity")
    if cmp:
        if cmp.value < 0.3:
            parts.append("complexity is low and well-controlled")
        elif cmp.value < 0.6:
            parts.append("complexity is moderate — some hot-spots worth watching")
        else:
            parts.append("complexity is high — consider targeted refactoring")

    doc = ch_map.get("Doc Cover")
    if doc:
        if doc.value > 0.7:
            parts.append("documentation coverage is strong")
        elif doc.value > 0.4:
            parts.append("documentation is present but has gaps")
        else:
            parts.append("documentation coverage is thin — a good area to invest in")

    test = ch_map.get("Test Depth")
    if test:
        if test.value > 0.7:
            parts.append(f"the test suite is deep ({dna.total_modules} modules well-covered)")
        elif test.value > 0.4:
            parts.append("test depth is moderate")
        else:
            parts.append("test depth is shallow — more tests would reduce risk")

    age = ch_map.get("Age Spread")
    if age:
        if age.value > 0.6:
            parts.append("module growth has been well-paced across sessions")
        else:
            parts.append("most modules were added in concentrated bursts")

    if not parts:
        return "No narrative could be generated from the current channel data."

    narrative = (
        f"The `{dna.hex_digest}` fingerprint tells the following story: "
        + ", ".join(parts[:-1])
        + (f", and {parts[-1]}" if len(parts) > 1 else parts[0])
        + "."
    )
    return narrative


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_complexity(avg_cc: float) -> float:
    """Normalise complexity to 0–1 (1 = best = low complexity)."""
    # CC 1 = score 1.0; CC 10+ = score 0.0
    return max(0.0, min(1.0, 1.0 - (avg_cc - 1.0) / 9.0))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fingerprint_repo(repo_path: Path, repo_name: str = "awake") -> RepoDna:
    """Generate the DNA fingerprint for a repository.

    Args:
        repo_path: Path to the repository root.
        repo_name: Display name for the repository.

    Returns:
        A RepoDna instance with all channels populated.
    """
    from datetime import datetime, timezone

    src_dir = repo_path / "src"
    tests_dir = repo_path / "tests"
    log_path = repo_path / "AWAKE_LOG.md"

    if not src_dir.exists():
        return RepoDna(
            repo_name=repo_name,
            generated_at=datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC"),
            hex_digest="00000000",
        )

    # Collect raw metrics
    avg_cc, per_file_cc = _compute_avg_complexity(src_dir)
    coupling_ratio = _compute_coupling_ratio(src_dir)
    doc_coverage = _compute_docstring_coverage(src_dir)
    test_depth = _compute_test_depth(src_dir, tests_dir)
    size_entropy = _compute_file_size_entropy(src_dir)
    age_entropy = _compute_age_entropy(log_path, src_dir)

    # Compute aggregate stats
    total_modules = len([f for f in src_dir.glob("*.py") if not f.name.startswith("_")])
    total_lines = sum(
        len(f.read_text(encoding="utf-8", errors="replace").splitlines())
        for f in src_dir.glob("*.py")
        if not f.name.startswith("_")
    )

    # Normalise all channels to 0–1 (higher = better where applicable)
    channels = [
        DnaChannel(
            label=_CHANNEL_LABELS[0],
            value=_normalise_complexity(avg_cc),
            raw_value=round(avg_cc, 3),
            description=_CHANNEL_DESCRIPTIONS[0],
        ),
        DnaChannel(
            label=_CHANNEL_LABELS[1],
            value=coupling_ratio,       # higher coupling_ratio = more inter-module connections
            raw_value=round(coupling_ratio, 3),
            description=_CHANNEL_DESCRIPTIONS[1],
        ),
        DnaChannel(
            label=_CHANNEL_LABELS[2],
            value=doc_coverage,
            raw_value=round(doc_coverage, 3),
            description=_CHANNEL_DESCRIPTIONS[2],
        ),
        DnaChannel(
            label=_CHANNEL_LABELS[3],
            value=test_depth,
            raw_value=round(test_depth, 3),
            description=_CHANNEL_DESCRIPTIONS[3],
        ),
        DnaChannel(
            label=_CHANNEL_LABELS[4],
            value=size_entropy,
            raw_value=round(size_entropy, 3),
            description=_CHANNEL_DESCRIPTIONS[4],
        ),
        DnaChannel(
            label=_CHANNEL_LABELS[5],
            value=age_entropy,
            raw_value=round(age_entropy, 3),
            description=_CHANNEL_DESCRIPTIONS[5],
        ),
    ]

    hex_digest = _compute_hex_digest(channels)

    return RepoDna(
        repo_name=repo_name,
        generated_at=datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC"),
        hex_digest=hex_digest,
        channels=channels,
        per_file_complexity=per_file_cc,
        total_modules=total_modules,
        total_lines=total_lines,
    )


def save_dna_report(dna: RepoDna, output_path: Path) -> None:
    """Save the DNA fingerprint as Markdown + JSON sidecar.

    Args:
        dna: The RepoDna to save.
        output_path: Path for the .md file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dna.to_markdown(), encoding="utf-8")
    output_path.with_suffix(".json").write_text(dna.to_json(), encoding="utf-8")
