"""Tests for src/openapi.py — OpenAPI spec generator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.openapi import (
    OpenAPISpec,
    OpenAPIOperation,
    OpenAPIPath,
    OpenAPIParameter,
    generate_openapi_spec,
    _dict_to_yaml,
)


def test_generate_openapi_spec_returns_spec():
    spec = generate_openapi_spec()
    assert isinstance(spec, OpenAPISpec)


def test_spec_has_paths():
    spec = generate_openapi_spec()
    assert len(spec.paths) > 10


def test_spec_to_dict_structure():
    spec = generate_openapi_spec()
    d = spec.to_dict()
    assert d["openapi"] == "3.1.0"
    assert "info" in d
    assert "paths" in d
    assert d["info"]["title"] == "Awake API"


def test_spec_contains_health_endpoint():
    spec = generate_openapi_spec()
    d = spec.to_dict()
    assert "/api/health" in d["paths"]


def test_spec_contains_session17_endpoints():
    spec = generate_openapi_spec()
    d = spec.to_dict()
    assert "/api/openapi" in d["paths"]
    assert "/api/report" in d["paths"]
    assert "/api/modules" in d["paths"]
    assert "/api/trends" in d["paths"]


def test_spec_parameterized_routes_use_braces():
    spec = generate_openapi_spec()
    d = spec.to_dict()
    # /api/replay/<n> should become /api/replay/{n}
    assert "/api/replay/{n}" in d["paths"]
    assert "/api/diff/{n}" in d["paths"]


def test_openapi_parameter_to_dict():
    param = OpenAPIParameter(
        name="n", location="path", description="Session number",
        required=True, schema_type="integer", schema_format="int32",
    )
    d = param.to_dict()
    assert d["in"] == "path"
    assert d["required"] is True
    assert d["schema"]["type"] == "integer"
    assert d["schema"]["format"] == "int32"


def test_openapi_operation_to_dict():
    op = OpenAPIOperation(
        operation_id="getHealth",
        summary="Code health report",
        tags=["analysis"],
        session_added="1",
    )
    d = op.to_dict()
    assert d["operationId"] == "getHealth"
    assert "200" in d["responses"]
    assert "500" in d["responses"]
    assert d["x-session-added"] == "1"


def test_spec_to_yaml_is_string():
    spec = generate_openapi_spec()
    yaml_str = spec.to_yaml()
    assert isinstance(yaml_str, str)
    assert "openapi" in yaml_str
    assert "3.1.0" in yaml_str


def test_spec_to_markdown():
    spec = generate_openapi_spec()
    md = spec.to_markdown()
    assert "# Awake API" in md
    assert "| Endpoint |" in md
    assert "/api/health" in md


def test_spec_with_repo_root(tmp_path):
    """Spec reads version from pyproject.toml when available."""
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.3.4"\n')
    spec = generate_openapi_spec(tmp_path)
    assert spec.version == "2.3.4"


def test_spec_all_operations_have_tags():
    spec = generate_openapi_spec()
    for p in spec.paths:
        if p.get:
            assert len(p.get.tags) > 0, f"No tags for {p.path}"


def test_spec_json_serializable():
    spec = generate_openapi_spec()
    d = spec.to_dict()
    # Should not raise
    json_str = json.dumps(d)
    assert len(json_str) > 100


def test_dict_to_yaml_simple():
    d = {"key": "value", "num": 42, "flag": True}
    yaml = _dict_to_yaml(d)
    assert "key:" in yaml
    assert "42" in yaml
    assert "true" in yaml


def test_dict_to_yaml_nested():
    d = {"outer": {"inner": "value"}}
    yaml = _dict_to_yaml(d)
    assert "outer:" in yaml
    assert "inner:" in yaml


def test_spec_servers_present():
    spec = generate_openapi_spec()
    d = spec.to_dict()
    assert len(d["servers"]) >= 1
    assert "127.0.0.1" in d["servers"][0]["url"]


def test_spec_session17_endpoints_have_correct_tags():
    spec = generate_openapi_spec()
    paths_dict = spec.to_dict()["paths"]
    # /api/openapi should be tagged meta
    report_entry = paths_dict.get("/api/report", {})
    get_op = report_entry.get("get", {})
    assert "analysis" in get_op.get("tags", [])
