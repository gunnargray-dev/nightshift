"""Module coupling analyzer for Awake.

Implements Robert Martin's Stable Dependencies Principle (SDP) by computing
afferent coupling (Ca), efferent coupling (Ce), and the Instability metric
(I = Ce / (Ca + Ce)) for every Python module inside ``src/``.

Definitions
-----------
- **Ca (Afferent Coupling):** The number of other ``src/`` modules that
  *import* this module.  High Ca → the module is heavily depended-upon
  (stable, hard to change).
- **Ce (Efferent Coupling):** The number of ``src/`` modules that *this*
  module imports.  High Ce → the module depends on many others
  (unstable, easy to change).
- **Instability (I):** ``Ce / (Ca + Ce)``.  Ranges from 0.0 (maximally
  stable — nothing this module depends on, everyone depends on it) to 1.0
  (maximally unstable — depends on many, no-one depends on it).  When both
  Ca and Ce are zero the module is treated as fully stable (I = 0.0).

Ranking thresholds
------------------
- **HIGH:**   I >= 0.8  *or*  Ce >= 10   (tightly coupled, fragile)
- **MEDIUM:** I >= 0.4  *or*  Ce >= 5    (moderate coupling)
- **LOW:**    otherwise                   (stable, well-bounded)

Only intra-project imports (other modules discovered under ``src/``) are
counted.  Standard-library and third-party imports are ignored.

Public API
----------
- ``ModuleCoupling``  — per-module coupling record
- ``CouplingReport``  — full report with aggregate properties
- ``analyze_coupling(repo_path)``  → ``CouplingReport``
- ``save_coupling_report(report, output_path)``

CLI
---
    awake coupling [--write] [--json]
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModuleCoupling:
    """Coupling metrics for a single Python module inside ``src/``.

    Attributes
    ----------
    module:
        Short module name, e.g. ``"health"``.
    file:
        Relative path from the repository root, e.g. ``"src/health.py"``.
    ca:
        Afferent coupling — how many other ``src/`` modules import this one.
    ce:
        Efferent coupling — how many ``src/`` modules this one imports.
    instability:
        Instability metric ``I = Ce / (Ca + Ce)``.  0.0 = maximally stable,
        1.0 = maximally unstable.  Defined as 0.0 when both Ca and Ce are 0.
    rank:
        ``"HIGH"``, ``"MEDIUM"``, or ``"LOW"`` based on instability/coupling.
    dependents:
        Names of the modules that import this one (Ca contributors).
    dependencies:
        Names of the ``src/`` modules that this module imports (Ce contributors).
    """

    module: str
    file: str
    ca: int = 0
    ce: int = 0
    instability: float = 0.0
    rank: str = "LOW"
    dependents: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dictionary."""
        return {
            "module": self.module,
            "file": self.file,
            "ca": self.ca,
            "ce": self.ce,
            "instability": round(self.instability, 4),
            "rank": self.rank,
            "dependents": sorted(self.dependents),
            "dependencies": sorted(self.dependencies),
        }


@dataclass
class CouplingReport:
    """Full module-coupling analysis report.

    Attributes
    ----------
    modules:
        List of per-module coupling records, one per ``src/`` Python file.
    repo_path:
        Absolute path to the repository root that was analysed.
    files_scanned:
        Total number of ``src/`` Python files parsed.
    """

    modules: list[ModuleCoupling] = field(default_factory=list)
    repo_path: str = ""
    files_scanned: int = 0

    # ---------------------------------------------------------------------------
    # Aggregate properties
    # ---------------------------------------------------------------------------

    @property
    def avg_instability(self) -> float:
        """Average instability across all modules (0.0 when no modules)."""
        if not self.modules:
            return 0.0
        return round(sum(m.instability for m in self.modules) / len(self.modules), 4)

    @property
    def high_count(self) -> int:
        """Number of modules ranked HIGH (instability >= 0.8 or Ce >= 10)."""
        return sum(1 for m in self.modules if m.rank == "HIGH")

    @property
    def medium_count(self) -> int:
        """Number of modules ranked MEDIUM (instability 0.4–0.79 or Ce 5–9)."""
        return sum(1 for m in self.modules if m.rank == "MEDIUM")

    @property
    def low_count(self) -> int:
        """Number of modules ranked LOW (instability < 0.4 and Ce < 5)."""
        return sum(1 for m in self.modules if m.rank == "LOW")

    # ---------------------------------------------------------------------------
    # Rendering
    # ---------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise the full report to a JSON-compatible dictionary."""
        return {
            "repo_path": self.repo_path,
            "files_scanned": self.files_scanned,
            "module_count": len(self.modules),
            "avg_instability": self.avg_instability,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "modules": [m.to_dict() for m in self.modules],
        }

    def to_json(self) -> str:
        """Serialise the full report to a pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render the report as a Markdown string.

        Sections
        --------
        1. Summary table with aggregate metrics.
        2. Per-module table sorted by instability descending (most unstable
           modules first), then alphabetically by module name.
        3. Detailed dependency listings for HIGH-ranked modules.
        """
        lines: list[str] = []

        lines.append("# Module Coupling Report\n")
        lines.append(f"**Repo:** `{self.repo_path}`  ")
        lines.append(f"**Files scanned:** {self.files_scanned}  ")
        lines.append(f"**Modules analysed:** {len(self.modules)}\n")

        if not self.modules:
            lines.append("_No modules found.\n_")
            return "\n".join(lines)

        lines.append("## Summary\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Average instability | {self.avg_instability:.3f} |")
        lines.append(f"| HIGH coupling | {self.high_count} |")
        lines.append(f"| MEDIUM coupling | {self.medium_count} |")
        lines.append(f"| LOW coupling | {self.low_count} |")
        lines.append("")

        # Sort: rank priority (HIGH first), then instability desc, then name
        _RANK_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        sorted_modules = sorted(
            self.modules,
            key=lambda m: (_RANK_ORDER.get(m.rank, 9), -m.instability, m.module),
        )

        lines.append("## Modules\n")
        lines.append("| Module | File | Ca | Ce | Instability | Rank |")
        lines.append("|--------|------|----|----|-------------|------|")
        for m in sorted_modules:
            lines.append(
                f"| `{m.module}` | `{m.file}` | {m.ca} | {m.ce} "
                f"| {m.instability:.3f} | {m.rank} |"
            )
        lines.append("")

        # Detail section for HIGH modules
        high_modules = [m for m in sorted_modules if m.rank == "HIGH"]
        if high_modules:
            lines.append("## HIGH Coupling Detail\n")
            for m in high_modules:
                lines.append(f"### `{m.module}`\n")
                lines.append(f"- **File:** `{m.file}`")
                lines.append(f"- **Ca (afferent):** {m.ca}")
                lines.append(f"- **Ce (efferent):** {m.ce}")
                lines.append(f"- **Instability:** {m.instability:.3f}")
                if m.dependents:
                    lines.append(
                        f"- **Depended on by:** {', '.join(f'`{d}`' for d in sorted(m.dependents))}"
                    )
                if m.dependencies:
                    lines.append(
                        f"- **Depends on:** {', '.join(f'`{d}`' for d in sorted(m.dependencies))}"
                    )
                lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# AST import collector
# ---------------------------------------------------------------------------


class _ImportCollector(ast.NodeVisitor):
    """Collect all module names referenced in ``import`` / ``from … import`` statements.

    Only top-level module names are stored (e.g. ``from src.health import X``
    yields ``"src.health"`` and ``import os.path`` yields ``"os"``).
    """

    def __init__(self) -> None:
        self.imports: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        """Record each name from a bare ``import`` statement."""
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        """Record the module name from a ``from … import`` statement."""
        if node.module:
            self.imports.append(node.module)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_file(py_file: Path) -> Optional[ast.Module]:
    """Parse *py_file* and return its AST, or ``None`` on syntax error."""
    from src._ast_utils import parse_file
    return parse_file(py_file)


def _rank(instability: float, ce: int) -> str:
    """Compute the coupling rank string from instability and efferent count.

    Parameters
    ----------
    instability:
        Pre-computed instability value in [0.0, 1.0].
    ce:
        Efferent coupling count.

    Returns
    -------
    ``"HIGH"``, ``"MEDIUM"``, or ``"LOW"``.
    """
    if instability >= 0.8 or ce >= 10:
        return "HIGH"
    if instability >= 0.4 or ce >= 5:
        return "MEDIUM"
    return "LOW"


def _instability(ca: int, ce: int) -> float:
    """Return the instability metric ``I = Ce / (Ca + Ce)``.

    Returns 0.0 when both *ca* and *ce* are zero (isolated module,
    treated as maximally stable by convention).
    """
    total = ca + ce
    if total == 0:
        return 0.0
    return ce / total


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def analyze_coupling(repo_path: Optional[Path] = None) -> CouplingReport:
    """Analyze module coupling across all ``src/`` Python files.

    Algorithm
    ---------
    1. Enumerate every ``*.py`` file under ``<repo_path>/src/`` (non-recursive
       for the top-level ``src/`` directory, matching the pattern used by
       ``dead_code.py``; sub-packages such as ``src/commands/`` are also
       included via recursive glob so their coupling is tracked).
    2. Build a mapping from *module name* (file stem, or ``commands.analysis``
       style dotted name for sub-packages) to its ``Path``.
    3. Parse each file with ``ast`` and collect all import statements.
    4. For each import, check whether the imported module path matches a known
       ``src/`` module; if so, record the dependency edge.
    5. Compute Ca, Ce, instability, and rank for every module.

    Parameters
    ----------
    repo_path:
        Root of the repository.  Defaults to the parent of this file's
        directory (i.e. the project root when installed normally).

    Returns
    -------
    CouplingReport
        Populated report ready for rendering or saving.
    """
    if repo_path is None:
        repo_path = Path(__file__).resolve().parent.parent
    repo_path = Path(repo_path)
    src_dir = repo_path / "src"

    report = CouplingReport(repo_path=str(repo_path))

    if not src_dir.exists():
        return report

    # ---- Enumerate all src/ Python files ----
    py_files: list[Path] = sorted(src_dir.rglob("*.py"))
    # Filter out __init__ and __pycache__ artifacts
    py_files = [
        f for f in py_files
        if not f.name.startswith("__")
    ]
    report.files_scanned = len(py_files)

    if not py_files:
        return report

    # ---- Build module name → Path index ----
    # For a file like src/health.py  → module key "health"
    # For src/commands/analysis.py   → module key "commands.analysis"
    # We also store the full dotted import path variants that code might use,
    # e.g. "src.health", so we can recognise both styles.
    module_index: dict[str, Path] = {}  # canonical key → Path
    # Maps every recognised import string → canonical key
    import_to_key: dict[str, str] = {}

    for py_file in py_files:
        rel = py_file.relative_to(src_dir)          # e.g. health.py or commands/analysis.py
        parts = list(rel.with_suffix("").parts)      # e.g. ["health"] or ["commands", "analysis"]
        canonical = ".".join(parts)                  # "health" or "commands.analysis"
        module_index[canonical] = py_file

        # Recognise several import spellings:
        #   "health", "src.health", "commands.analysis", "src.commands.analysis"
        import_to_key[canonical] = canonical
        import_to_key[f"src.{canonical}"] = canonical
        # Also bare stem for disambiguation (last segment)
        stem = parts[-1]
        # Only add bare stem if it doesn't conflict with an existing entry
        if stem not in import_to_key:
            import_to_key[stem] = canonical

    # ---- Collect raw import edges: importer → set of imported canonical keys ----
    # edges[canonical_key] = set of canonical keys this module imports
    edges: dict[str, set[str]] = {key: set() for key in module_index}

    for py_file in py_files:
        rel = py_file.relative_to(src_dir)
        parts = list(rel.with_suffix("").parts)
        canonical = ".".join(parts)

        tree = _parse_file(py_file)
        if tree is None:
            continue

        collector = _ImportCollector()
        collector.visit(tree)

        for imp in collector.imports:
            # Try the full dotted name first, then progressively shorter prefixes
            # e.g. "src.commands.analysis" → try full, then "src.commands", then "src"
            matched_key: Optional[str] = None

            # Direct lookup
            if imp in import_to_key:
                matched_key = import_to_key[imp]
            else:
                # Try progressively stripping the rightmost segment
                # (handles ``from src.health import generate_health_report``)
                parts_imp = imp.split(".")
                for length in range(len(parts_imp), 0, -1):
                    prefix = ".".join(parts_imp[:length])
                    if prefix in import_to_key:
                        matched_key = import_to_key[prefix]
                        break

            if matched_key is not None and matched_key != canonical:
                edges[canonical].add(matched_key)

    # ---- Compute Ca and Ce for every module ----
    # Ce[key] = len(edges[key])
    # Ca[key] = number of other modules whose edge-set contains key
    ce_map: dict[str, int] = {key: len(deps) for key, deps in edges.items()}
    ca_map: dict[str, int] = {key: 0 for key in module_index}
    dependents_map: dict[str, list[str]] = {key: [] for key in module_index}

    for importer, deps in edges.items():
        for dep_key in deps:
            if dep_key in ca_map:
                ca_map[dep_key] += 1
                dependents_map[dep_key].append(importer)

    # ---- Build ModuleCoupling records ----
    for canonical, py_file in sorted(module_index.items()):
        ca = ca_map[canonical]
        ce = ce_map[canonical]
        inst = _instability(ca, ce)
        rnk = _rank(inst, ce)
        rel_file = str(py_file.relative_to(repo_path))

        mc = ModuleCoupling(
            module=canonical,
            file=rel_file,
            ca=ca,
            ce=ce,
            instability=inst,
            rank=rnk,
            dependents=sorted(dependents_map[canonical]),
            dependencies=sorted(edges[canonical]),
        )
        report.modules.append(mc)

    return report


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_coupling_report(report: CouplingReport, output_path: Path) -> None:
    """Write the coupling report as Markdown + JSON sidecar to *output_path*.

    Parameters
    ----------
    report:
        Populated ``CouplingReport`` instance.
    output_path:
        Destination path for the ``.md`` file.  The parent directory is
        created if it does not exist.  A ``.json`` sidecar is written
        alongside the Markdown file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_markdown(), encoding="utf-8")
    json_path = output_path.with_suffix(".json")
    json_path.write_text(report.to_json(), encoding="utf-8")
