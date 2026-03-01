"""Tests for src/init_cmd.py — Session 16."""

from __future__ import annotations

import json
import pytest
from pathlib import Path


def _import():
    from src import init_cmd
    return init_cmd


# ---------------------------------------------------------------------------
# bootstrap — creates files
# ---------------------------------------------------------------------------

class TestBootstrap:
    def test_creates_awake_toml(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        assert (tmp_path / "awake.toml").exists()

    def test_creates_awake_log(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        assert (tmp_path / "AWAKE_LOG.md").exists()

    def test_creates_changelog(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        assert (tmp_path / "CHANGELOG.md").exists()

    def test_creates_docs_readme(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        assert (tmp_path / "docs" / "README.md").exists()

    def test_creates_github_workflow(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        assert (tmp_path / ".github" / "workflows" / "awake.yml").exists()

    def test_workflow_content_is_valid_yaml_shape(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        content = (tmp_path / ".github" / "workflows" / "awake.yml").read_text()
        assert "awake health" in content
        assert "python-version" in content

    def test_awake_toml_has_thresholds(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        content = (tmp_path / "awake.toml").read_text()
        assert "[thresholds]" in content
        assert "health_score_min" in content

    def test_session_log_has_session_0(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        content = (tmp_path / "AWAKE_LOG.md").read_text()
        assert "Session 0" in content

    def test_result_created_count(self, tmp_path):
        ic = _import()
        result = ic.bootstrap(tmp_path)
        assert result.total_created == 5  # 5 files created

    def test_result_repo_path(self, tmp_path):
        ic = _import()
        result = ic.bootstrap(tmp_path)
        assert result.repo_path == str(tmp_path)

    def test_idempotent_no_force(self, tmp_path):
        ic = _import()
        # First run
        ic.bootstrap(tmp_path)
        # Modify awake.toml
        (tmp_path / "awake.toml").write_text("# custom", encoding="utf-8")
        # Second run without force
        result2 = ic.bootstrap(tmp_path)
        # Should skip awake.toml
        assert any("awake.toml" in p for p in result2.skipped)
        # Content should be unchanged (custom)
        assert (tmp_path / "awake.toml").read_text() == "# custom"

    def test_force_overwrites(self, tmp_path):
        ic = _import()
        ic.bootstrap(tmp_path)
        (tmp_path / "awake.toml").write_text("# custom", encoding="utf-8")
        result2 = ic.bootstrap(tmp_path, force=True)
        assert any("awake.toml" in p for p in result2.created)
        content = (tmp_path / "awake.toml").read_text()
        assert "[thresholds]" in content  # original template restored

    def test_create_src_flag(self, tmp_path):
        ic = _import()
        result = ic.bootstrap(tmp_path, create_src=True)
        assert (tmp_path / "src" / "__init__.py").exists()
        assert any("src/__init__.py" in p or p.endswith("__init__.py") for p in result.created)

    def test_create_src_skipped_if_exists(self, tmp_path):
        ic = _import()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "__init__.py").write_text("# existing", encoding="utf-8")
        result = ic.bootstrap(tmp_path, create_src=True)
        assert any("src/__init__.py" in p or p.endswith("__init__.py") for p in result.skipped)


# ---------------------------------------------------------------------------
# InitResult
# ---------------------------------------------------------------------------

class TestInitResult:
    def _make_result(self):
        ic = _import()
        r = ic.InitResult(repo_path="/tmp/test")
        r.created = ["awake.toml", "CHANGELOG.md"]
        r.skipped = ["AWAKE_LOG.md"]
        return r

    def test_total_created(self):
        r = self._make_result()
        assert r.total_created == 2

    def test_to_dict_keys(self):
        r = self._make_result()
        d = r.to_dict()
        assert "created" in d
        assert "skipped" in d
        assert "total_created" in d
        assert "repo_path" in d

    def test_to_json_valid(self):
        r = self._make_result()
        parsed = json.loads(r.to_json())
        assert parsed["total_created"] == 2

    def test_to_markdown_shows_created(self):
        r = self._make_result()
        md = r.to_markdown()
        assert "awake.toml" in md
        assert "Created" in md

    def test_to_markdown_shows_skipped(self):
        r = self._make_result()
        md = r.to_markdown()
        assert "Skipped" in md
        assert "AWAKE_LOG.md" in md

    def test_to_markdown_empty(self):
        ic = _import()
        r = ic.InitResult(repo_path="/tmp/empty")
        md = r.to_markdown()
        assert "awake health" in md  # still shows the tip
