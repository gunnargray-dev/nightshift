"""Performance benchmark suite for Awake modules.

Times every analysis module, detects regressions against a stored baseline,
and outputs a ranked table.  The baseline is persisted in
``docs/benchmark_history.json`` so regressions are tracked across sessions.

Usage
-----
    from src.benchmark import run_benchmarks, save_benchmark_report
    report = run_benchmarks(repo_path=Path("."))
    print(report.to_markdown())
    save_benchmark_report(report, Path("docs/benchmark_report.md"))
"""

from __future__ import annotations

import ast
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    """Timing result for a single module analysis."""

    module: str
    elapsed_ms: float
    status: str  # "ok" | "error" | "skipped"
    error: Optional[str] = None
    baseline_ms: Optional[float] = None

    @property
    def regression(self) -> Optional[float]:
        """Return percentage change vs baseline (positive = slower)."""
        if self.baseline_ms is None or self.baseline_ms == 0:
            return None
        return ((self.elapsed_ms - self.baseline_ms) / self.baseline_ms) * 100.0

    @property
    def regression_label(self) -> str:
        """Human-readable regression string, e.g. ``"\u25b2 +35%  \u26a0"`` or ``"—"``."""
        r = self.regression
        if r is None:
            return "—"
        if r > 20:
            return f"\u25b2 +{r:.0f}%  \u26a0"
        if r < -10:
            return f"\u25bc {r:.0f}%"
        return f"{r:+.0f}%"

    def to_dict(self) -> dict:
        """Serialise this result to a plain dictionary including derived fields."""
        d = asdict(self)
        d["regression"] = self.regression
        d["regression_label"] = self.regression_label
        return d


@dataclass
class BenchmarkReport:
    """Full benchmark report across all timed modules."""

    results: list[BenchmarkResult] = field(default_factory=list)
    total_ms: float = 0.0
    session: int = 15
    timestamp: str = ""

    # ---- derived --------------------------------------------------------

    @property
    def regressions(self) -> list[BenchmarkResult]:
        """Return all results where timing regressed more than 20% vs baseline."""
        return [r for r in self.results if r.regression is not None and r.regression > 20]

    @property
    def fastest(self) -> Optional[BenchmarkResult]:
        """Return the result with the shortest elapsed time (``status == "ok"`` only)."""
        ok = [r for r in self.results if r.status == "ok"]
        return min(ok, key=lambda r: r.elapsed_ms) if ok else None

    @property
    def slowest(self) -> Optional[BenchmarkResult]:
        """Return the result with the longest elapsed time (``status == "ok"`` only)."""
        ok = [r for r in self.results if r.status == "ok"]
        return max(ok, key=lambda r: r.elapsed_ms) if ok else None

    # ---- serialisation --------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise the report to a plain dictionary (JSON-safe)."""
        return {
            "results": [r.to_dict() for r in self.results],
            "total_ms": self.total_ms,
            "session": self.session,
            "timestamp": self.timestamp,
            "regressions": len(self.regressions),
        }

    def to_json(self) -> str:
        """Serialise the report to a pretty-printed JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        """Render the benchmark report as a Markdown table."""
        lines: list[str] = ["# Awake Performance Benchmark\n"]
        if self.timestamp:
            lines.append(f"*Recorded: {self.timestamp}*\n")

        lines += [
            "| Module | Time (ms) | vs Baseline | Status |",
            "|--------|----------:|-------------|--------|",
        ]
        sorted_results = sorted(self.results, key=lambda r: r.elapsed_ms)
        for r in sorted_results:
            status_icon = "✅" if r.status == "ok" else ("❌" if r.status == "error" else "⏭")
            lines.append(
                f"| `{r.module}` | {r.elapsed_ms:.1f} | {r.regression_label} | {status_icon} |"
            )

        lines.append(f"\n**Total wall time:** {self.total_ms:.0f} ms\n")

        if self.regressions:
            lines.append(f"\n⚠️  **{len(self.regressions)} regression(s) detected:**")
            for r in self.regressions:
                lines.append(f"  - `{r.module}`: {r.regression_label}")

        if self.fastest:
            lines.append(f"\n🏆 Fastest: `{self.fastest.module}` ({self.fastest.elapsed_ms:.1f} ms)")
        if self.slowest:
            lines.append(f"🐢 Slowest: `{self.slowest.module}` ({self.slowest.elapsed_ms:.1f} ms)")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Benchmark runners
# ---------------------------------------------------------------------------


def _time_module(name: str, fn) -> BenchmarkResult:
    """Run *fn* and record its wall-clock time in milliseconds."""
    start = time.perf_counter()
    try:
        fn()
        elapsed_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(module=name, elapsed_ms=elapsed_ms, status="ok")
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return BenchmarkResult(
            module=name, elapsed_ms=elapsed_ms, status="error", error=str(exc)[:120]
        )


def _build_runners(repo_path: Path) -> list[tuple[str, object]]:
    """Return a list of (module_name, callable) pairs to benchmark."""
    runners = []

    try:
        from src.health import analyze_health
        runners.append(("health", lambda: analyze_health(repo_path / "src")))
    except ImportError:
        pass

    try:
        from src.stats import compute_stats
        log = repo_path / "AWAKE_LOG.md"
        runners.append(("stats", lambda: compute_stats(repo_path=repo_path, log_path=log)))
    except ImportError:
        pass

    try:
        from src.dep_graph import build_dep_graph
        runners.append(("dep_graph", lambda: build_dep_graph(repo_path / "src")))
    except ImportError:
        pass

    try:
        from src.todo_hunter import hunt_todos
        runners.append(("todo_hunter", lambda: hunt_todos(repo_path / "src", session=15)))
    except ImportError:
        pass

    try:
        from src.doctor import run_doctor
        runners.append(("doctor", lambda: run_doctor(repo_path)))
    except ImportError:
        pass

    try:
        from src.dead_code import find_dead_code
        runners.append(("dead_code", lambda: find_dead_code(repo_path / "src")))
    except ImportError:
        pass

    try:
        from src.security import audit_security
        runners.append(("security", lambda: audit_security(repo_path / "src")))
    except ImportError:
        pass

    try:
        from src.coverage_map import build_coverage_map
        runners.append(("coverage_map", lambda: build_coverage_map(repo_path)))
    except ImportError:
        pass

    try:
        from src.blame import analyze_blame
        runners.append(("blame", lambda: analyze_blame(repo_path)))
    except ImportError:
        pass

    try:
        from src.maturity import assess_maturity
        runners.append(("maturity", lambda: assess_maturity(repo_path=repo_path)))
    except ImportError:
        pass

    try:
        from src.dna import fingerprint_repo
        runners.append(("dna", lambda: fingerprint_repo(repo_path=repo_path)))
    except ImportError:
        pass

    try:
        from src.coupling import analyze_coupling
        runners.append(("coupling", lambda: analyze_coupling(repo_path / "src")))
    except ImportError:
        pass

    try:
        from src.complexity import analyze_complexity
        runners.append(("complexity", lambda: analyze_complexity(repo_path / "src", session=15)))
    except ImportError:
        pass

    return runners


# ---------------------------------------------------------------------------
# Baseline persistence
# ---------------------------------------------------------------------------


def _load_baseline(history_path: Path) -> dict[str, float]:
    """Load the most recent baseline from benchmark_history.json."""
    if not history_path.exists():
        return {}
    try:
        data = json.loads(history_path.read_text())
        if isinstance(data, list) and data:
            last = data[-1]
            return {r["module"]: r["elapsed_ms"] for r in last.get("results", [])}
        return {}
    except Exception:
        return {}


def _save_history(report: BenchmarkReport, history_path: Path) -> None:
    """Append the current report to the rolling history file."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list = []
    if history_path.exists():
        try:
            existing = json.loads(history_path.read_text())
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
    existing.append(report.to_dict())
    existing = existing[-20:]
    history_path.write_text(json.dumps(existing, indent=2))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_benchmarks(
    repo_path: Optional[Path] = None,
    session: int = 15,
    persist: bool = True,
) -> BenchmarkReport:
    """Run all module benchmarks and return a BenchmarkReport."""
    import datetime

    repo = repo_path or Path(__file__).resolve().parent.parent
    history_path = repo / "docs" / "benchmark_history.json"
    baseline = _load_baseline(history_path)

    runners = _build_runners(repo)
    results: list[BenchmarkResult] = []
    wall_start = time.perf_counter()

    for name, fn in runners:
        result = _time_module(name, fn)
        result.baseline_ms = baseline.get(name)
        results.append(result)

    total_ms = (time.perf_counter() - wall_start) * 1000

    report = BenchmarkReport(
        results=results,
        total_ms=total_ms,
        session=session,
        timestamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    if persist:
        _save_history(report, history_path)

    return report


def save_benchmark_report(report: BenchmarkReport, output_path: Path) -> None:
    """Write Markdown report and JSON sidecar to *output_path*."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_markdown())
    output_path.with_suffix(".json").write_text(report.to_json())
