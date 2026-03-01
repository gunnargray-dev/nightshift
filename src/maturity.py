"""Module Maturity Scorer for Awake.

Rates each module in src/ on a 0–100 maturity scale across five dimensions:

1. **Test coverage** (0–25)  — does a test file exist, and how many tests are there?
2. **Documentation** (0–25)  — module docstring, function docstring coverage
3. **Complexity health** (0–20) — average cyclomatic complexity (lower is better)
4. **Age / session depth** (0–15) — how many sessions ago was this module first added?
5. **Coupling stability** (0–15) — instability metric (lower I = more stable)

Each dimension gets a 0–5 star rating, and the overall 0–100 score maps to a
maturity tier:

  SEED    (0–19)   — brand new, barely started
  SPROUT  (20–39)  — basic functionality, thin test layer
  GROWING (40–59)  — solid implementation, needs documentation or test depth
  MATURE  (60–79)  — well-tested, documented, stable
  VETERAN (80–100) — exemplary: high tests, docs, low complexity, long history

Output formats:
- Markdown table (default)
- JSON (--json)

CLI:
    awake maturity [--write] [--json]
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Tier / scoring constants
# ---------------------------------------------------------------------------

TIER_SEED = "SEED"
TIER_SPROUT = "SPROUT"
TIER_GROWING = "GROWING"
TIER_MATURE = "MATURE"
TIER_VETERAN = "VETERAN"

_TIER_THRESHOLDS = [
    (80, TIER_VETERAN),
    (60, TIER_MATURE),
    (40, TIER_GROWING),
    (20, TIER_SPROUT),
    (0,  TIER_SEED),
]

_TIER_EMOJI = {
    TIER_SEED:    "🌱",
    TIER_SPROUT:  "🌿",
    TIER_GROWING: "🌳",
    TIER_MATURE:  "🏆",
    TIER_VETERAN: "⭐",
}


def _score_to_tier(score: float) -> str:
    for threshold, tier in _TIER_THRESHOLDS:
        if score >= threshold:
            return tier
    return TIER_SEED


def _stars(score_0_to_max: float, max_score: float, max_stars: int = 5) -> str:
    """Return a Unicode star rating string like ★★★☆☆."""
    filled = round((score_0_to_max / max_score) * max_stars)
    filled = max(0, min(max_stars, filled))
    return "★" * filled + "☆" * (max_stars - filled)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ModuleMaturity:
    """Maturity assessment for a single module."""

    name: str                        # e.g. "health"
    src_path: str                    # relative path
    test_path: Optional[str]         # None if no test file

    # Dimension scores
    test_score: float = 0.0          # 0–25
    docs_score: float = 0.0          # 0–25
    complexity_score: float = 0.0    # 0–20
    age_score: float = 0.0           # 0–15
    coupling_score: float = 0.0      # 0–15

    # Raw metrics (for display)
    test_count: int = 0
    public_functions: int = 0
    docstring_coverage: float = 0.0  # 0.0–1.0
    avg_complexity: float = 0.0
    session_age: int = 0             # sessions since first added
    instability: float = 0.5         # 0–1 (lower = more stable)

    @property
    def total_score(self) -> float:
        """Return the sum of all dimension scores for this module"""
        return round(
            self.test_score
            + self.docs_score
            + self.complexity_score
            + self.age_score
            + self.coupling_score,
            1,
        )

    @property
    def tier(self) -> str:
        """Return the maturity tier name based on total score"""
        return _score_to_tier(self.total_score)

    @property
    def tier_emoji(self) -> str:
        """Return the emoji icon for this module's maturity tier"""
        return _TIER_EMOJI[self.tier]

    def to_dict(self) -> dict:
        """Return a dictionary representation including computed score and tier"""
        d = asdict(self)
        d["total_score"] = self.total_score
        d["tier"] = self.tier
        return d

    def summary_row(self) -> str:
        """Return a Markdown table row for this module."""
        stars_test = _stars(self.test_score, 25)
        stars_docs = _stars(self.docs_score, 25)
        stars_cmp = _stars(self.complexity_score, 20)
        stars_age = _stars(self.age_score, 15)
        stars_cpl = _stars(self.coupling_score, 15)
        return (
            f"| `{self.name}` "
            f"| {self.total_score:.0f}/100 "
            f"| {self.tier_emoji} {self.tier} "
            f"| {stars_test} "
            f"| {stars_docs} "
            f"| {stars_cmp} "
            f"| {stars_age} "
            f"| {stars_cpl} |"
        )


@dataclass
class MaturityReport:
    """Maturity assessment for all modules in the repository."""

    generated_at: str = ""
    modules: list[ModuleMaturity] = field(default_factory=list)

    @property
    def avg_score(self) -> float:
        """Return the average maturity score across all modules"""
        if not self.modules:
            return 0.0
        return round(sum(m.total_score for m in self.modules) / len(self.modules), 1)

    @property
    def veterans(self) -> list[ModuleMaturity]:
        """Return modules that have reached the VETERAN maturity tier"""
        return [m for m in self.modules if m.tier == TIER_VETERAN]

    @property
    def seeds(self) -> list[ModuleMaturity]:
        """Return modules that are still in the SEED maturity tier"""
        return [m for m in self.modules if m.tier == TIER_SEED]

    def to_dict(self) -> dict:
        """Return a dictionary representation of the maturity report"""
        return {
            "generated_at": self.generated_at,
            "avg_score": self.avg_score,
            "modules": [m.to_dict() for m in self.modules],
        }

    def to_json(self) -> str:
        """Serialize the maturity report to a JSON string"""
        return json.dumps(self.to_dict(), indent=2, default=str)

    def to_markdown(self) -> str:
        """Render the maturity report as a Markdown document."""
        # Sort: highest score first
        sorted_modules = sorted(self.modules, key=lambda m: m.total_score, reverse=True)

        lines = [
            "# Module Maturity Report",
            "",
            f"*Generated {self.generated_at}*",
            "",
            f"**Modules analysed:** {len(self.modules)}  "
            f"**Average score:** {self.avg_score}/100  "
            f"**Veterans:** {len(self.veterans)}  "
            f"**Seeds:** {len(self.seeds)}",
            "",
            "## Scoring Dimensions",
            "",
            "| Dimension | Weight | Measures |",
            "|-----------|--------|----------|",
            "| Tests | 25 pts | Test file exists + test function count |",
            "| Docs | 25 pts | Module docstring + function docstring coverage |",
            "| Complexity | 20 pts | Average cyclomatic complexity (lower = better) |",
            "| Age | 15 pts | Session depth (older modules score higher) |",
            "| Coupling | 15 pts | Dependency instability (lower = more stable) |",
            "",
            "## Module Rankings",
            "",
            "| Module | Score | Tier | Tests ★ | Docs ★ | Complexity ★ | Age ★ | Coupling ★ |",
            "|--------|-------|------|---------|--------|--------------|-------|------------|",
        ]

        for m in sorted_modules:
            lines.append(m.summary_row())

        lines += [
            "",
            "## Detail: Top 5 Modules",
            "",
        ]

        for m in sorted_modules[:5]:
            lines += [
                f"### `{m.name}` — {m.total_score:.0f}/100 {m.tier_emoji}",
                "",
                f"- **Tests:** {m.test_count} test functions "
                + ("(\u2705)" if m.test_path else "(\u274c no test file)"),
                f"- **Docs:** {m.docstring_coverage*100:.0f}% function docstring coverage",
                f"- **Complexity:** avg {m.avg_complexity:.1f} cyclomatic complexity",
                f"- **Age:** {m.session_age} session(s) old",
                f"- **Instability:** {m.instability:.2f} (0=stable, 1=unstable)",
                "",
            ]

        lines += [
            "## Tiers",
            "",
            "| Tier | Score | Meaning |",
            "|------|-------|--------|",
            "| ⭐ VETERAN | 80–100 | Exemplary: tested, documented, stable, mature |",
            "| 🏆 MATURE | 60–79 | Well-rounded, minor gaps remain |",
            "| 🌳 GROWING | 40–59 | Solid but needs attention in 1–2 areas |",
            "| 🌿 SPROUT | 20–39 | Basic functionality, thin coverage |",
            "| 🌱 SEED | 0–19 | Newly added, much room to grow |",
            "",
        ]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Metric collection helpers
# ---------------------------------------------------------------------------


def _count_tests_in_file(path: Path) -> int:
    """Count test functions in a test file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )


def _analyze_src_file(path: Path) -> tuple[int, float, float]:
    """Return (public_function_count, docstring_coverage, avg_complexity)."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return 0, 0.0, 5.0

    public_funcs = []
    complexities: list[float] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                public_funcs.append(node)
            # Compute simple cyclomatic complexity proxy
            cc = 1 + sum(
                1
                for child in ast.walk(node)
                if isinstance(
                    child,
                    (ast.If, ast.For, ast.While, ast.Try, ast.ExceptHandler,
                     ast.With, ast.Assert, ast.comprehension),
                )
            )
            complexities.append(float(cc))

    if not public_funcs:
        return 0, 1.0, 1.0

    with_docs = sum(
        1 for f in public_funcs
        if (ast.get_docstring(f) or "").strip()
    )
    doc_cov = with_docs / len(public_funcs)
    avg_cc = sum(complexities) / len(complexities) if complexities else 1.0

    return len(public_funcs), doc_cov, avg_cc


def _estimate_session_age(name: str, log_path: Path) -> int:
    """Estimate how many sessions ago a module was introduced.

    Scans AWAKE_LOG.md for the earliest session that mentions src/<name>.py.
    Returns 0 if the log doesn't exist or no mention is found.
    """
    if not log_path.exists():
        return 0

    content = log_path.read_text(encoding="utf-8")

    # Find all session headers
    session_headers = list(
        re.finditer(r"^## Session (\d+)", content, re.MULTILINE)
    )
    if not session_headers:
        return 0

    last_session = int(session_headers[-1].group(1))

    # Find earliest session that mentions this module
    pattern = re.compile(
        rf"src/{re.escape(name)}\.py",
        re.IGNORECASE,
    )

    for m_hdr in session_headers:
        session_num = int(m_hdr.group(1))
        # Get text of this section
        next_i = session_headers.index(m_hdr) + 1
        end = (
            session_headers[next_i].start()
            if next_i < len(session_headers)
            else len(content)
        )
        section = content[m_hdr.start():end]
        if pattern.search(section):
            return last_session - session_num + 1

    return 1  # default: one session old


def _estimate_instability(name: str, src_dir: Path) -> float:
    """Estimate the instability of a module (0=stable, 1=unstable).

    Uses a simplified version of Robert Martin's instability metric:
    I = Ce / (Ca + Ce)
    where Ca = number of modules that import this module (afferent)
          Ce = number of modules this module imports from src (efferent)
    """
    all_files = list(src_dir.glob("*.py"))
    afferent = 0
    efferent = 0

    for f in all_files:
        if f.stem == name:
            # Count this module's own imports from src
            try:
                source = f.read_text(encoding="utf-8")
                tree = ast.parse(source)
                efferent = sum(
                    1
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and node.module
                    and node.module.startswith("src.")
                )
            except Exception:
                efferent = 0
        else:
            # Check if this other file imports our module
            try:
                source = f.read_text(encoding="utf-8")
                if f"src.{name}" in source or f"from src import {name}" in source:
                    afferent += 1
            except Exception:
                pass

    total = afferent + efferent
    if total == 0:
        return 0.5  # neutral / unknown
    return round(efferent / total, 3)


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

_MAX_TEST_SCORE = 25.0
_MAX_DOCS_SCORE = 25.0
_MAX_COMPLEXITY_SCORE = 20.0
_MAX_AGE_SCORE = 15.0
_MAX_COUPLING_SCORE = 15.0

_TARGET_TESTS_PER_MODULE = 35  # 35+ tests = full test score


def _score_tests(test_count: int, has_test_file: bool) -> float:
    if not has_test_file:
        return 0.0
    # 1–10 tests: 1–14 pts; 11–35: 14–25 pts; 35+: 25 pts
    if test_count <= 0:
        return 2.0  # file exists but empty
    ratio = min(test_count / _TARGET_TESTS_PER_MODULE, 1.0)
    return round(ratio * _MAX_TEST_SCORE, 1)


def _score_docs(public_funcs: int, docstring_coverage: float, has_module_docstring: bool) -> float:
    base = docstring_coverage * 20.0  # 0–20 pts
    if has_module_docstring:
        base += 5.0  # 5 bonus pts for module-level docstring
    return round(min(base, _MAX_DOCS_SCORE), 1)


def _score_complexity(avg_cc: float) -> float:
    # CC 1–2: full score; CC 3–5: good; CC 6–10: ok; CC 10+: poor
    if avg_cc <= 2.0:
        return _MAX_COMPLEXITY_SCORE
    if avg_cc <= 5.0:
        score = _MAX_COMPLEXITY_SCORE - ((avg_cc - 2.0) / 3.0) * 8.0
    elif avg_cc <= 10.0:
        score = 12.0 - ((avg_cc - 5.0) / 5.0) * 8.0
    else:
        score = max(0.0, 4.0 - (avg_cc - 10.0) * 0.5)
    return round(max(0.0, score), 1)


def _score_age(session_age: int, max_sessions: int) -> float:
    if max_sessions == 0:
        return _MAX_AGE_SCORE / 2
    ratio = min(session_age / max(max_sessions, 1), 1.0)
    return round(ratio * _MAX_AGE_SCORE, 1)


def _score_coupling(instability: float) -> float:
    # Lower instability = more stable = higher score
    return round((1.0 - instability) * _MAX_COUPLING_SCORE, 1)


def _has_module_docstring(path: Path) -> bool:
    """Return True if the module has a top-level docstring."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        return bool(ast.get_docstring(tree))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_module_maturity(
    name: str,
    src_dir: Path,
    tests_dir: Path,
    log_path: Path,
    max_sessions: int = 13,
) -> ModuleMaturity:
    """Score the maturity of a single module.

    Args:
        name: Module name (without .py).
        src_dir: Path to src/ directory.
        tests_dir: Path to tests/ directory.
        log_path: Path to AWAKE_LOG.md.
        max_sessions: Total number of sessions (for age normalisation).

    Returns:
        A ModuleMaturity instance with all scores populated.
    """
    src_path = src_dir / f"{name}.py"
    test_path_candidate = tests_dir / f"test_{name}.py"
    has_test_file = test_path_candidate.exists()
    test_path = str(test_path_candidate.relative_to(src_dir.parent)) if has_test_file else None

    # Collect metrics
    test_count = _count_tests_in_file(test_path_candidate) if has_test_file else 0
    public_funcs, doc_cov, avg_cc = _analyze_src_file(src_path)
    has_module_doc = _has_module_docstring(src_path)
    session_age = _estimate_session_age(name, log_path)
    instability = _estimate_instability(name, src_dir)

    # Score each dimension
    test_score = _score_tests(test_count, has_test_file)
    docs_score = _score_docs(public_funcs, doc_cov, has_module_doc)
    complexity_score = _score_complexity(avg_cc)
    age_score = _score_age(session_age, max_sessions)
    coupling_score = _score_coupling(instability)

    return ModuleMaturity(
        name=name,
        src_path=str(src_path.relative_to(src_dir.parent)),
        test_path=test_path,
        test_score=test_score,
        docs_score=docs_score,
        complexity_score=complexity_score,
        age_score=age_score,
        coupling_score=coupling_score,
        test_count=test_count,
        public_functions=public_funcs,
        docstring_coverage=doc_cov,
        avg_complexity=avg_cc,
        session_age=session_age,
        instability=instability,
    )


def assess_maturity(
    repo_path: Path,
) -> MaturityReport:
    """Assess maturity for all modules in src/.

    Args:
        repo_path: Path to the repository root.

    Returns:
        A MaturityReport containing assessments for every src/*.py module.
    """
    from datetime import datetime, timezone

    src_dir = repo_path / "src"
    tests_dir = repo_path / "tests"
    log_path = repo_path / "AWAKE_LOG.md"

    if not src_dir.exists():
        return MaturityReport(
            generated_at=datetime.now(timezone.utc).strftime("%B %d, %Y"),
            modules=[],
        )

    # Count total sessions for age normalisation
    max_sessions = 1
    if log_path.exists():
        content = log_path.read_text(encoding="utf-8")
        session_matches = re.findall(r"^## Session (\d+)", content, re.MULTILINE)
        if session_matches:
            max_sessions = max(int(s) for s in session_matches)

    modules = []
    for src_file in sorted(src_dir.glob("*.py")):
        if src_file.name.startswith("_"):
            continue
        name = src_file.stem
        m = score_module_maturity(
            name=name,
            src_dir=src_dir,
            tests_dir=tests_dir,
            log_path=log_path,
            max_sessions=max_sessions,
        )
        modules.append(m)

    return MaturityReport(
        generated_at=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        modules=modules,
    )


def save_maturity_report(report: MaturityReport, output_path: Path) -> None:
    """Save the maturity report as Markdown + JSON sidecar.

    Args:
        report: The MaturityReport to save.
        output_path: Path for the .md output file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.to_markdown(), encoding="utf-8")
    output_path.with_suffix(".json").write_text(report.to_json(), encoding="utf-8")
