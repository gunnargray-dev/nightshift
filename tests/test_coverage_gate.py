from pathlib import Path

import pytest

from src.coverage_gate import read_total_coverage_percent, enforce_coverage_gate


def test_read_total_coverage_percent_reads_percent_covered(tmp_path: Path):
    p = tmp_path / "coverage.json"
    p.write_text('{"totals": {"percent_covered": 88.5}}', encoding="utf-8")
    assert read_total_coverage_percent(p) == 88.5


def test_read_total_coverage_percent_raises_if_missing(tmp_path: Path):
    p = tmp_path / "coverage.json"
    p.write_text('{"totals": {}}', encoding="utf-8")
    with pytest.raises(ValueError):
        read_total_coverage_percent(p)


def test_enforce_coverage_gate_fails_below_threshold(tmp_path: Path, capsys):
    p = tmp_path / "coverage.json"
    p.write_text('{"totals": {"percent_covered": 79.9}}', encoding="utf-8")

    rc = enforce_coverage_gate(min_percent=80.0, coverage_json_path=p)
    assert rc == 1
    assert "Coverage gate failed" in capsys.readouterr().err


def test_enforce_coverage_gate_passes_at_or_above_threshold(tmp_path: Path, capsys):
    p = tmp_path / "coverage.json"
    p.write_text('{"totals": {"percent_covered": 80.0}}', encoding="utf-8")

    rc = enforce_coverage_gate(min_percent=80.0, coverage_json_path=p)
    assert rc == 0
    assert "Coverage gate passed" in capsys.readouterr().out
