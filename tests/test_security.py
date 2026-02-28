"""Tests for src/security.py — Security audit module."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.security import (
    SecurityFinding,
    SecurityReport,
    audit_security,
    save_security_report,
    _SecurityVisitor,
)


# ---------------------------------------------------------------------------
# SecurityFinding
# ---------------------------------------------------------------------------

class TestSecurityFinding:
    def _finding(self, severity="HIGH") -> SecurityFinding:
        return SecurityFinding(
            rule="S001",
            title="Use of eval()",
            severity=severity,
            cwe="CWE-94",
            file="src/foo.py",
            line=5,
            snippet="eval(user_input)",
            description="Dangerous",
        )

    def test_to_dict_keys(self):
        d = self._finding().to_dict()
        assert "rule" in d
        assert "severity" in d
        assert "cwe" in d
        assert "file" in d
        assert "line" in d
        assert "snippet" in d
        assert "description" in d
        assert "cwe_description" in d

    def test_cwe_description_populated(self):
        d = self._finding().to_dict()
        assert d["cwe_description"] == "Code Injection"

    def test_unknown_cwe(self):
        f = self._finding()
        f.cwe = "CWE-9999"
        d = f.to_dict()
        assert d["cwe_description"] == ""


# ---------------------------------------------------------------------------
# SecurityReport
# ---------------------------------------------------------------------------

class TestSecurityReport:
    def _make_report(self) -> SecurityReport:
        rpt = SecurityReport(repo_path="/tmp/repo", files_scanned=3)
        rpt.findings = [
            SecurityFinding("S001", "eval", "HIGH", "CWE-94", "src/a.py", 1, "eval(x)", "desc"),
            SecurityFinding("S004", "shell=True", "HIGH", "CWE-78", "src/b.py", 5, "run(cmd, shell=True)", "desc"),
            SecurityFinding("S005", "os.system", "MEDIUM", "CWE-78", "src/c.py", 3, "os.system(cmd)", "desc"),
        ]
        return rpt

    def test_high_count(self):
        rpt = self._make_report()
        assert rpt.high_count == 2

    def test_medium_count(self):
        rpt = self._make_report()
        assert rpt.medium_count == 1

    def test_low_count(self):
        rpt = self._make_report()
        assert rpt.low_count == 0

    def test_grade_many_high(self):
        rpt = self._make_report()
        # 2 HIGH → grade C or worse
        assert rpt.grade in ("C", "D", "F")

    def test_grade_clean(self):
        rpt = SecurityReport(repo_path="/tmp", files_scanned=1)
        assert rpt.grade == "A"

    def test_grade_low_only(self):
        rpt = SecurityReport(repo_path="/tmp", files_scanned=1)
        rpt.findings = [
            SecurityFinding("S001", "t", "LOW", "CWE-94", "f", 1, "", ""),
        ]
        assert rpt.grade == "A"

    def test_to_markdown_contains_findings(self):
        rpt = self._make_report()
        md = rpt.to_markdown()
        assert "Findings" in md
        assert "S001" in md
        assert "S004" in md

    def test_to_markdown_no_findings(self):
        rpt = SecurityReport(repo_path="/tmp", files_scanned=2)
        md = rpt.to_markdown()
        assert "No security issues found" in md

    def test_to_dict(self):
        rpt = self._make_report()
        d = rpt.to_dict()
        assert d["high_count"] == 2
        assert d["medium_count"] == 1
        assert d["total"] == 3

    def test_to_json_valid(self):
        rpt = self._make_report()
        obj = json.loads(rpt.to_json())
        assert "findings" in obj


# ---------------------------------------------------------------------------
# AST checks via _SecurityVisitor
# ---------------------------------------------------------------------------

def _audit_source(source: str, rel: str = "test.py") -> list[SecurityFinding]:
    import ast
    lines = source.splitlines()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    visitor = _SecurityVisitor(rel, lines)
    visitor.visit(tree)
    return visitor.findings


class TestSecurityVisitor:
    def test_detects_eval(self):
        findings = _audit_source("eval(x)")
        rules = [f.rule for f in findings]
        assert "S001" in rules

    def test_detects_exec(self):
        findings = _audit_source("exec('code')")
        rules = [f.rule for f in findings]
        assert "S002" in rules

    def test_detects_pickle_loads(self):
        findings = _audit_source("import pickle; pickle.loads(data)")
        rules = [f.rule for f in findings]
        assert "S003" in rules

    def test_detects_subprocess_shell_true(self):
        findings = _audit_source(
            "import subprocess; subprocess.run('cmd', shell=True)"
        )
        rules = [f.rule for f in findings]
        assert "S004" in rules

    def test_no_flag_shell_false(self):
        findings = _audit_source(
            "import subprocess; subprocess.run(['cmd'], shell=False)"
        )
        rules = [f.rule for f in findings]
        assert "S004" not in rules

    def test_detects_os_system(self):
        findings = _audit_source("import os; os.system('ls')")
        rules = [f.rule for f in findings]
        assert "S005" in rules

    def test_detects_weak_md5(self):
        findings = _audit_source("import hashlib; hashlib.md5(data)")
        rules = [f.rule for f in findings]
        assert "S006" in rules

    def test_detects_weak_sha1(self):
        findings = _audit_source("import hashlib; hashlib.sha1(data)")
        rules = [f.rule for f in findings]
        assert "S006" in rules

    def test_no_flag_sha256(self):
        findings = _audit_source("import hashlib; hashlib.sha256(data)")
        rules = [f.rule for f in findings]
        assert "S006" not in rules

    def test_detects_mktemp(self):
        findings = _audit_source("import tempfile; tempfile.mktemp()")
        rules = [f.rule for f in findings]
        assert "S007" in rules

    def test_detects_yaml_load_no_loader(self):
        findings = _audit_source("import yaml; yaml.load(stream)")
        rules = [f.rule for f in findings]
        assert "S008" in rules

    def test_no_flag_yaml_safe_load(self):
        findings = _audit_source("import yaml; yaml.safe_load(stream)")
        rules = [f.rule for f in findings]
        assert "S008" not in rules

    def test_clean_code_no_findings(self):
        source = """
def add(a, b):
    return a + b

result = add(1, 2)
"""
        findings = _audit_source(source)
        assert findings == []


# ---------------------------------------------------------------------------
# Hardcoded secrets (regex)
# ---------------------------------------------------------------------------

class TestHardcodedSecrets:
    def test_detects_hardcoded_password(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "config.py").write_text('password = "hunter2"\n')
        report = audit_security(repo_path=tmp_path)
        rules = [f.rule for f in report.findings]
        assert "S010" in rules

    def test_detects_api_key(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "config.py").write_text('api_key = "sk-abc1234567890"\n')
        report = audit_security(repo_path=tmp_path)
        rules = [f.rule for f in report.findings]
        assert "S010" in rules

    def test_no_flag_short_literal(self, tmp_path):
        # Passwords under 4 chars are noise; pattern requires {4,}
        src = tmp_path / "src"
        src.mkdir()
        (src / "config.py").write_text('password = "abc"\n')
        report = audit_security(repo_path=tmp_path)
        rules = [f.rule for f in report.findings]
        # Short values should not be flagged
        assert "S010" not in rules


# ---------------------------------------------------------------------------
# audit_security integration
# ---------------------------------------------------------------------------

class TestAuditSecurity:
    def test_missing_src_dir(self, tmp_path):
        report = audit_security(repo_path=tmp_path)
        assert report.files_scanned == 0
        assert len(report.findings) == 0

    def test_clean_files_no_findings(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "clean.py").write_text("x = 1 + 1\n")
        report = audit_security(repo_path=tmp_path)
        assert len(report.findings) == 0

    def test_counts_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("x = 1\n")
        (src / "b.py").write_text("y = 2\n")
        report = audit_security(repo_path=tmp_path)
        assert report.files_scanned == 2

    def test_grade_assigned(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "risky.py").write_text("eval(user_input)\n")
        report = audit_security(repo_path=tmp_path)
        assert report.grade in ("A", "B", "C", "D", "F")

    def test_syntax_error_skipped(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "bad.py").write_text("def broken(:\n")
        report = audit_security(repo_path=tmp_path)
        assert isinstance(report, SecurityReport)


# ---------------------------------------------------------------------------
# save_security_report
# ---------------------------------------------------------------------------

class TestSaveSecurityReport:
    def test_writes_files(self, tmp_path):
        out = tmp_path / "sec.md"
        rpt = SecurityReport(repo_path=str(tmp_path))
        save_security_report(rpt, out)
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_json_is_valid(self, tmp_path):
        out = tmp_path / "sec.md"
        rpt = SecurityReport(repo_path=str(tmp_path))
        save_security_report(rpt, out)
        data = json.loads(out.with_suffix(".json").read_text())
        assert "findings" in data

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "a" / "b" / "sec.md"
        rpt = SecurityReport(repo_path=str(tmp_path))
        save_security_report(rpt, out)
        assert out.exists()
