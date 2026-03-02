"""Tests for src/coupling.py — Module coupling analyzer.

All tests are self-contained and use ``tmp_path`` (pytest fixture) or
in-memory data so no real git repository is required.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.coupling import (
    ModuleCoupling,
    CouplingReport,
    analyze_coupling,
    save_coupling_report,
    _ImportCollector,
    _parse_file,
    _rank,
    _instability,
)


# ---------------------------------------------------------------------------
# Helper: build a tiny fake src/ tree under tmp_path
# ---------------------------------------------------------------------------


def _make_src(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write *files* (relative-path → content) under ``tmp_path/src/``.

    Returns the ``src/`` directory path.
    """
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        dest = src / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return src


# ---------------------------------------------------------------------------
# _instability
# ---------------------------------------------------------------------------


class TestInstability:
    def test_both_zero_returns_zero(self):
        """An isolated module (Ca=0, Ce=0) should be treated as stable."""
        assert _instability(0, 0) == 0.0

    def test_fully_unstable(self):
        """Ce=5, Ca=0 → I = 1.0."""
        assert _instability(0, 5) == 1.0

    def test_fully_stable(self):
        """Ce=0, Ca=5 → I = 0.0."""
        assert _instability(5, 0) == 0.0

    def test_midpoint(self):
        """Ca=5, Ce=5 → I = 0.5."""
        assert _instability(5, 5) == pytest.approx(0.5)

    def test_asymmetric(self):
        """Ca=1, Ce=3 → I = 0.75."""
        assert _instability(1, 3) == pytest.approx(0.75)

    def test_large_values(self):
        """Sanity check with larger numbers."""
        assert _instability(90, 10) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# _rank
# ---------------------------------------------------------------------------


class TestRank:
    def test_high_by_instability(self):
        assert _rank(0.8, 0) == "HIGH"

    def test_high_by_instability_above_threshold(self):
        assert _rank(0.95, 2) == "HIGH"

    def test_high_by_ce(self):
        """Ce >= 10 should always be HIGH regardless of instability."""
        assert _rank(0.0, 10) == "HIGH"

    def test_high_by_ce_large(self):
        assert _rank(0.3, 15) == "HIGH"

    def test_medium_by_instability(self):
        assert _rank(0.5, 0) == "MEDIUM"

    def test_medium_by_ce(self):
        """Ce=5 should be MEDIUM if instability is below 0.8."""
        assert _rank(0.3, 5) == "MEDIUM"

    def test_medium_boundary_instability(self):
        assert _rank(0.4, 0) == "MEDIUM"

    def test_low_stable(self):
        assert _rank(0.0, 0) == "LOW"

    def test_low_near_medium_boundary(self):
        assert _rank(0.39, 4) == "LOW"

    def test_low_moderate_instability_low_ce(self):
        assert _rank(0.2, 2) == "LOW"


# ---------------------------------------------------------------------------
# ModuleCoupling
# ---------------------------------------------------------------------------


class TestModuleCoupling:
    def _make(self) -> ModuleCoupling:
        return ModuleCoupling(
            module="health",
            file="src/health.py",
            ca=3,
            ce=1,
            instability=0.25,
            rank="LOW",
            dependents=["cli", "report"],
            dependencies=["config"],
        )

    def test_to_dict_keys(self):
        d = self._make().to_dict()
        for key in ("module", "file", "ca", "ce", "instability", "rank",
                    "dependents", "dependencies"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_values(self):
        d = self._make().to_dict()
        assert d["module"] == "health"
        assert d["ca"] == 3
        assert d["ce"] == 1
        assert d["rank"] == "LOW"

    def test_to_dict_dependents_sorted(self):
        mc = ModuleCoupling(
            module="x", file="src/x.py", dependents=["z", "a", "m"],
        )
        assert mc.to_dict()["dependents"] == ["a", "m", "z"]

    def test_to_dict_dependencies_sorted(self):
        mc = ModuleCoupling(
            module="x", file="src/x.py", dependencies=["z", "a"],
        )
        assert mc.to_dict()["dependencies"] == ["a", "z"]

    def test_instability_rounded_in_dict(self):
        mc = ModuleCoupling(
            module="x", file="src/x.py", instability=1 / 3,
        )
        # Should be rounded to 4 decimal places
        assert mc.to_dict()["instability"] == round(1 / 3, 4)


# ---------------------------------------------------------------------------
# CouplingReport properties
# ---------------------------------------------------------------------------


class TestCouplingReportProperties:
    def _make_report(self) -> CouplingReport:
        return CouplingReport(
            repo_path="/repo",
            files_scanned=4,
            modules=[
                ModuleCoupling("a", "src/a.py", ca=0, ce=12, instability=1.0, rank="HIGH"),
                ModuleCoupling("b", "src/b.py", ca=2, ce=5,  instability=0.71, rank="MEDIUM"),
                ModuleCoupling("c", "src/c.py", ca=5, ce=0,  instability=0.0,  rank="LOW"),
                ModuleCoupling("d", "src/d.py", ca=0, ce=0,  instability=0.0,  rank="LOW"),
            ],
        )

    def test_high_count(self):
        assert self._make_report().high_count == 1

    def test_medium_count(self):
        assert self._make_report().medium_count == 1

    def test_low_count(self):
        assert self._make_report().low_count == 2

    def test_avg_instability(self):
        rpt = self._make_report()
        expected = round((1.0 + 0.71 + 0.0 + 0.0) / 4, 4)
        assert rpt.avg_instability == expected

    def test_avg_instability_empty(self):
        rpt = CouplingReport()
        assert rpt.avg_instability == 0.0

    def test_counts_sum_to_total(self):
        rpt = self._make_report()
        assert rpt.high_count + rpt.medium_count + rpt.low_count == len(rpt.modules)


# ---------------------------------------------------------------------------
# CouplingReport.to_dict / to_json
# ---------------------------------------------------------------------------


class TestCouplingReportSerialization:
    def _rpt(self) -> CouplingReport:
        return CouplingReport(
            repo_path="/repo",
            files_scanned=2,
            modules=[
                ModuleCoupling("a", "src/a.py", ca=1, ce=1, instability=0.5, rank="MEDIUM"),
                ModuleCoupling("b", "src/b.py", ca=0, ce=0, instability=0.0, rank="LOW"),
            ],
        )

    def test_to_dict_top_level_keys(self):
        d = self._rpt().to_dict()
        for k in ("repo_path", "files_scanned", "module_count",
                   "avg_instability", "high_count", "medium_count",
                   "low_count", "modules"):
            assert k in d

    def test_to_dict_module_count(self):
        assert self._rpt().to_dict()["module_count"] == 2

    def test_to_dict_modules_list(self):
        d = self._rpt().to_dict()
        assert isinstance(d["modules"], list)
        assert len(d["modules"]) == 2

    def test_to_json_valid(self):
        obj = json.loads(self._rpt().to_json())
        assert "modules" in obj

    def test_to_json_roundtrip(self):
        rpt = self._rpt()
        obj = json.loads(rpt.to_json())
        assert obj["files_scanned"] == 2
        assert obj["modules"][0]["module"] in ("a", "b")


# ---------------------------------------------------------------------------
# CouplingReport.to_markdown
# ---------------------------------------------------------------------------


class TestCouplingReportMarkdown:
    def _rpt_with_high(self) -> CouplingReport:
        return CouplingReport(
            repo_path="/repo",
            files_scanned=3,
            modules=[
                ModuleCoupling("unstable", "src/unstable.py", ca=0, ce=11,
                               instability=1.0, rank="HIGH",
                               dependencies=["a", "b"]),
                ModuleCoupling("mid", "src/mid.py", ca=2, ce=5,
                               instability=0.71, rank="MEDIUM"),
                ModuleCoupling("stable", "src/stable.py", ca=8, ce=0,
                               instability=0.0, rank="LOW",
                               dependents=["unstable", "mid"]),
            ],
        )

    def test_markdown_has_title(self):
        md = self._rpt_with_high().to_markdown()
        assert "Module Coupling Report" in md

    def test_markdown_has_summary_section(self):
        md = self._rpt_with_high().to_markdown()
        assert "Summary" in md

    def test_markdown_has_modules_section(self):
        md = self._rpt_with_high().to_markdown()
        assert "Modules" in md

    def test_markdown_has_high_detail_section(self):
        md = self._rpt_with_high().to_markdown()
        assert "HIGH Coupling Detail" in md

    def test_markdown_lists_module_names(self):
        md = self._rpt_with_high().to_markdown()
        assert "unstable" in md
        assert "stable" in md

    def test_markdown_empty_report(self):
        rpt = CouplingReport(repo_path="/r", files_scanned=0)
        md = rpt.to_markdown()
        assert "No modules found" in md

    def test_markdown_no_high_detail_when_none(self):
        rpt = CouplingReport(
            repo_path="/r",
            modules=[ModuleCoupling("a", "src/a.py", rank="LOW")],
        )
        md = rpt.to_markdown()
        assert "HIGH Coupling Detail" not in md

    def test_markdown_shows_instability_values(self):
        md = self._rpt_with_high().to_markdown()
        assert "1.000" in md   # instability=1.0 formatted to 3dp

    def test_markdown_shows_repo_path(self):
        md = self._rpt_with_high().to_markdown()
        assert "/repo" in md


# ---------------------------------------------------------------------------
# _ImportCollector
# ---------------------------------------------------------------------------


class TestImportCollector:
    def _collect(self, source: str) -> list[str]:
        import ast as _ast
        tree = _ast.parse(source)
        collector = _ImportCollector()
        collector.visit(tree)
        return collector.imports

    def test_bare_import(self):
        imports = self._collect("import os")
        assert "os" in imports

    def test_from_import(self):
        imports = self._collect("from pathlib import Path")
        assert "pathlib" in imports

    def test_from_import_dotted(self):
        imports = self._collect("from src.health import generate_health_report")
        assert "src.health" in imports

    def test_multiple_imports(self):
        source = "import os\nimport sys\nfrom pathlib import Path\n"
        imports = self._collect(source)
        assert "os" in imports
        assert "sys" in imports
        assert "pathlib" in imports

    def test_no_imports(self):
        assert self._collect("x = 1") == []


# ---------------------------------------------------------------------------
# _parse_file
# ---------------------------------------------------------------------------


class TestParseFile:
    def test_valid_file(self, tmp_path):
        f = tmp_path / "ok.py"
        f.write_text("x = 1\n")
        assert _parse_file(f) is not None

    def test_syntax_error_returns_none(self, tmp_path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n")
        assert _parse_file(f) is None


# ---------------------------------------------------------------------------
# analyze_coupling — integration tests using tmp_path fake repos
# ---------------------------------------------------------------------------


class TestAnalyzeCouplingIntegration:
    def test_missing_src_returns_empty_report(self, tmp_path):
        report = analyze_coupling(repo_path=tmp_path)
        assert report.files_scanned == 0
        assert report.modules == []

    def test_empty_src_dir(self, tmp_path):
        (tmp_path / "src").mkdir()
        report = analyze_coupling(repo_path=tmp_path)
        assert report.modules == []

    def test_single_isolated_module_is_stable(self, tmp_path):
        """A module with no imports and no dependents → I=0.0, LOW."""
        _make_src(tmp_path, {"health.py": "def run(): pass\n"})
        report = analyze_coupling(repo_path=tmp_path)
        assert len(report.modules) == 1
        mc = report.modules[0]
        assert mc.ca == 0
        assert mc.ce == 0
        assert mc.instability == 0.0
        assert mc.rank == "LOW"

    def test_module_no_intra_imports_only_stdlib(self, tmp_path):
        """Only stdlib imports → Ce=0, fully stable."""
        _make_src(tmp_path, {
            "utils.py": "import os\nimport sys\nfrom pathlib import Path\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        mc = next(m for m in report.modules if m.module == "utils")
        assert mc.ce == 0
        assert mc.instability == 0.0

    def test_high_ca_module(self, tmp_path):
        """A module imported by many others should have high Ca."""
        content_base = "# base module\ndef shared(): pass\n"
        importers = {
            f"mod{i}.py": f"from src.base import shared\n" for i in range(5)
        }
        _make_src(tmp_path, {"base.py": content_base, **importers})
        report = analyze_coupling(repo_path=tmp_path)
        base_mc = next(m for m in report.modules if m.module == "base")
        assert base_mc.ca == 5
        assert base_mc.instability == 0.0

    def test_high_ce_module(self, tmp_path):
        """A module importing 10+ others should be HIGH."""
        leaves = {f"leaf{i}.py": "x = 1\n" for i in range(11)}
        hub_lines = "\n".join(f"from src.leaf{i} import x" for i in range(11))
        _make_src(tmp_path, {"hub.py": hub_lines + "\n", **leaves})
        report = analyze_coupling(repo_path=tmp_path)
        hub_mc = next(m for m in report.modules if m.module == "hub")
        assert hub_mc.ce >= 10
        assert hub_mc.rank == "HIGH"

    def test_ce_counts_only_src_modules(self, tmp_path):
        """Third-party / stdlib imports must not inflate Ce."""
        _make_src(tmp_path, {
            "mod.py": (
                "import os\n"
                "import sys\n"
                "import json\n"
                "from pathlib import Path\n"
                "from typing import Optional\n"
            ),
        })
        report = analyze_coupling(repo_path=tmp_path)
        mc = report.modules[0]
        assert mc.ce == 0

    def test_two_module_dependency(self, tmp_path):
        """A imports B → A.Ce=1, B.Ca=1, A.instability=1.0."""
        _make_src(tmp_path, {
            "a.py": "from src.b import something\n",
            "b.py": "def something(): pass\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        a = next(m for m in report.modules if m.module == "a")
        b = next(m for m in report.modules if m.module == "b")
        assert a.ce == 1
        assert a.ca == 0
        assert a.instability == pytest.approx(1.0)
        assert b.ca == 1
        assert b.ce == 0
        assert b.instability == 0.0

    def test_circular_dependencies(self, tmp_path):
        """A imports B and B imports A — both should have Ca=1, Ce=1, I=0.5."""
        _make_src(tmp_path, {
            "a.py": "from src.b import f\ndef g(): pass\n",
            "b.py": "from src.a import g\ndef f(): pass\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        a = next(m for m in report.modules if m.module == "a")
        b = next(m for m in report.modules if m.module == "b")
        assert a.ca == 1
        assert a.ce == 1
        assert a.instability == pytest.approx(0.5)
        assert b.ca == 1
        assert b.ce == 1
        assert b.instability == pytest.approx(0.5)

    def test_dependents_list_populated(self, tmp_path):
        """Modules that import X should appear in X.dependents."""
        _make_src(tmp_path, {
            "core.py": "def f(): pass\n",
            "cli.py": "from src.core import f\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        core = next(m for m in report.modules if m.module == "core")
        assert "cli" in core.dependents

    def test_dependencies_list_populated(self, tmp_path):
        """Modules that X imports should appear in X.dependencies."""
        _make_src(tmp_path, {
            "core.py": "def f(): pass\n",
            "cli.py": "from src.core import f\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        cli = next(m for m in report.modules if m.module == "cli")
        assert "core" in cli.dependencies

    def test_files_scanned_count(self, tmp_path):
        """files_scanned should equal the number of non-dunder .py files."""
        _make_src(tmp_path, {
            "a.py": "x=1\n",
            "b.py": "x=1\n",
            "__init__.py": "",
        })
        report = analyze_coupling(repo_path=tmp_path)
        assert report.files_scanned == 2

    def test_repo_path_recorded(self, tmp_path):
        _make_src(tmp_path, {"a.py": "x=1\n"})
        report = analyze_coupling(repo_path=tmp_path)
        assert str(tmp_path) in report.repo_path

    def test_syntax_error_file_skipped_gracefully(self, tmp_path):
        """A file with a syntax error should not crash analysis."""
        _make_src(tmp_path, {
            "broken.py": "def bad(:\n",
            "ok.py": "x = 1\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        assert isinstance(report, CouplingReport)

    def test_medium_coupling_module(self, tmp_path):
        """A module with I=0.5 and Ce=5 should be MEDIUM."""
        deps = {f"dep{i}.py": "x=1\n" for i in range(5)}
        hub_lines = "\n".join(f"from src.dep{i} import x" for i in range(5))
        # One module imports the hub so Ca=1 → I=5/6 ≈ 0.83 → actually HIGH
        # To get MEDIUM we want I in [0.4, 0.8): Ce=5, Ca=3 → I=5/8=0.625
        importers = {f"user{i}.py": "from src.hub import y\n" for i in range(3)}
        _make_src(tmp_path, {"hub.py": hub_lines + "\ndef y(): pass\n",
                              **deps, **importers})
        report = analyze_coupling(repo_path=tmp_path)
        hub = next(m for m in report.modules if m.module == "hub")
        # Ce=5, Ca=3 → I=5/8=0.625 → MEDIUM
        assert hub.rank == "MEDIUM"

    def test_ranking_high_instability(self, tmp_path):
        """Instability=1.0 with low Ce should still rank correctly."""
        _make_src(tmp_path, {
            "leaf.py": "x=1\n",
            "importer.py": "from src.leaf import x\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        importer = next(m for m in report.modules if m.module == "importer")
        # Ce=1, Ca=0 → I=1.0 → but Ce<5 and I<0.8? No: I=1.0 >= 0.8 → HIGH
        assert importer.rank == "HIGH"

    def test_no_self_loop(self, tmp_path):
        """A module should not list itself as a dependency or dependent."""
        _make_src(tmp_path, {
            "mod.py": "from src.mod import something\ndef something(): pass\n",
        })
        report = analyze_coupling(repo_path=tmp_path)
        mc = report.modules[0]
        assert mc.module not in mc.dependencies
        assert mc.module not in mc.dependents


# ---------------------------------------------------------------------------
# save_coupling_report
# ---------------------------------------------------------------------------


class TestSaveCouplingReport:
    def _simple_report(self) -> CouplingReport:
        return CouplingReport(
            repo_path="/repo",
            files_scanned=1,
            modules=[
                ModuleCoupling("a", "src/a.py", ca=0, ce=0,
                               instability=0.0, rank="LOW"),
            ],
        )

    def test_writes_markdown_file(self, tmp_path):
        out = tmp_path / "coupling.md"
        save_coupling_report(self._simple_report(), out)
        assert out.exists()

    def test_markdown_content_valid(self, tmp_path):
        out = tmp_path / "coupling.md"
        save_coupling_report(self._simple_report(), out)
        content = out.read_text()
        assert "Module Coupling Report" in content

    def test_writes_json_sidecar(self, tmp_path):
        out = tmp_path / "coupling.md"
        save_coupling_report(self._simple_report(), out)
        json_path = out.with_suffix(".json")
        assert json_path.exists()

    def test_json_sidecar_is_valid(self, tmp_path):
        out = tmp_path / "coupling.md"
        save_coupling_report(self._simple_report(), out)
        obj = json.loads(out.with_suffix(".json").read_text())
        assert "modules" in obj

    def test_creates_parent_directories(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "coupling.md"
        save_coupling_report(self._simple_report(), out)
        assert out.exists()
