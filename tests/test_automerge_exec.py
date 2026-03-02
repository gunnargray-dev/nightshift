from __future__ import annotations

import json
import os

import pytest

from src.automerge_exec import merge_pull_request, main


def test_merge_pull_request_dry_run() -> None:
    res = merge_pull_request(owner="o", repo="r", pr_number=1, token="t", dry_run=True)
    assert res.status == "dry_run"
    assert res.merged is False


def test_main_ineligible_json(capsys) -> None:
    # score below threshold => ineligible
    rc = main(["--pr", "1", "--score", "10", "--ci-passed", "true", "--min-score", "80", "--json"])
    assert rc == 1
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["status"] == "ineligible"


def test_main_missing_token_error_json(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    rc = main(["--pr", "1", "--score", "90", "--ci-passed", "true", "--min-score", "80", "--json"])
    assert rc == 2
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "missing_token"


def test_main_dry_run_does_not_require_token(monkeypatch, capsys) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    rc = main(["--pr", "1", "--score", "90", "--ci-passed", "true", "--min-score", "80", "--dry-run", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "dry_run"
