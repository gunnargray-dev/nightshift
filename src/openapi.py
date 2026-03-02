"""OpenAPI 3.1 specification generator for the Awake API server.

Generates a complete OpenAPI 3.1 JSON/YAML document from the route catalogue.
No external dependencies -- uses only the standard library.

CLI
---
    awake openapi              # Print spec to stdout
    awake openapi --write      # Write docs/openapi.json + docs/openapi.yaml
    awake openapi --format yaml
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class OpenAPIParameter:
    """Represent a single parameter in an OpenAPI operation"""
    name: str
    location: str
    description: str = ""
    required: bool = False
    schema_type: str = "string"
    schema_format: str = ""

    def to_dict(self) -> dict:
        """Return an OpenAPI-compliant dictionary for this parameter"""
        d: dict[str, Any] = {
            "name": self.name,
            "in": self.location,
            "description": self.description,
            "required": self.required,
            "schema": {"type": self.schema_type},
        }
        if self.schema_format:
            d["schema"]["format"] = self.schema_format
        return d


@dataclass
class OpenAPIOperation:
    """Represent a single API operation with its metadata and response schema"""
    operation_id: str
    summary: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[OpenAPIParameter] = field(default_factory=list)
    response_description: str = "Successful response"
    response_example: Optional[dict] = None
    session_added: str = ""

    def to_dict(self) -> dict:
        """Return an OpenAPI-compliant dictionary for this operation"""
        responses: dict[str, Any] = {
            "200": {
                "description": self.response_description,
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "500": {
                "description": "Internal server error",
                "content": {"application/json": {"schema": {"type": "object", "properties": {"error": {"type": "string"}}}}},
            },
        }
        if self.response_example:
            responses["200"]["content"]["application/json"]["example"] = self.response_example
        d: dict[str, Any] = {
            "operationId": self.operation_id,
            "summary": self.summary,
            "tags": self.tags,
            "responses": responses,
        }
        if self.description:
            d["description"] = self.description
        if self.parameters:
            d["parameters"] = [p.to_dict() for p in self.parameters]
        if self.session_added:
            d["x-session-added"] = self.session_added
        return d


@dataclass
class OpenAPIPath:
    """Represent an API endpoint path and its associated operations"""
    path: str
    get: Optional[OpenAPIOperation] = None

    def to_dict(self) -> dict:
        """Return an OpenAPI-compliant dictionary for this path"""
        d: dict[str, Any] = {}
        if self.get:
            d["get"] = self.get.to_dict()
        return d


@dataclass
class OpenAPISpec:
    """Represent a complete OpenAPI 3.1 specification document"""
    title: str = "Awake API"
    version: str = "1.0.0"
    description: str = ""
    paths: list[OpenAPIPath] = field(default_factory=list)
    server_url: str = "http://127.0.0.1:8710"

    def to_dict(self) -> dict:
        """Return the full OpenAPI 3.1 specification as a dictionary"""
        paths_dict: dict[str, Any] = {}
        for p in self.paths:
            openapi_path = re.sub(r"<([^>]+)>", r"{\1}", p.path)
            paths_dict[openapi_path] = p.to_dict()
        return {
            "openapi": "3.1.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
                "contact": {"name": "Awake", "url": "https://github.com/gunnargray-dev/awake"},
                "license": {"name": "MIT"},
            },
            "servers": [{"url": self.server_url, "description": "Local Awake API server"}],
            "tags": [
                {"name": "analysis", "description": "Code analysis endpoints"},
                {"name": "sessions", "description": "Session management"},
                {"name": "meta", "description": "Server metadata"},
            ],
            "paths": paths_dict,
        }

    def to_yaml(self) -> str:
        """Serialize the specification to a YAML string"""
        return _dict_to_yaml(self.to_dict())

    def to_markdown(self) -> str:
        """Render the specification as a Markdown endpoint summary table"""
        lines = [
            f"# {self.title}",
            "",
            f"> Version `{self.version}` -- {len(self.paths)} endpoints",
            "",
            "| Endpoint | Operation | Tags | Description |",
            "|----------|-----------|------|-------------|",
        ]
        for p in self.paths:
            op = p.get
            if op:
                tags_str = ", ".join(f"`{t}`" for t in op.tags)
                desc = op.summary
                added = f" *(v{op.session_added})*" if op.session_added else ""
                openapi_path = re.sub(r"<([^>]+)>", r"{\1}", p.path)
                lines.append(f"| `{openapi_path}` | `{op.operation_id}` | {tags_str} | {desc}{added} |")
        return "\n".join(lines)


_ROUTE_CATALOGUE: dict[str, tuple] = {
    "/api/health": ("getHealth", "Code health report", "AST-based static analysis scoring all Python source files 0-100.", ["analysis"], "1"),
    "/api/stats": ("getStats", "Repository statistics", "Commit count, PR totals, lines changed, and session metrics from git history.", ["analysis"], "1"),
    "/api/coverage": ("getCoverage", "Test coverage trend", "Historical test coverage data with session-over-session sparklines.", ["analysis"], "1"),
    "/api/changelog": ("getChangelog", "Changelog entries", "Auto-generated changelog from [awake] commit messages, grouped by session.", ["analysis"], "1"),
    "/api/scores": ("getPRScores", "PR quality scores", "PR quality leaderboard: 0-100 scores across 5 dimensions with letter grades.", ["analysis"], "1"),
    "/api/depgraph": ("getDependencyGraph", "Module dependency graph", "Directed import dependency graph with circular import detection.", ["analysis"], "1"),
    "/api/doctor": ("getDoctor", "Repo health diagnostic", "13-check diagnostic suite producing an A-F composite grade.", ["analysis"], "1"),
    "/api/todos": ("getTodos", "Stale TODO annotations", "Scans for TODO/FIXME/HACK/XXX comments and flags stale items.", ["analysis"], "1"),
    "/api/triage": ("getIssueTriage", "Issue triage", "Classifies and prioritises GitHub issues by type and urgency.", ["analysis"], "1"),
    "/api/plan": ("getPlan", "Brain task ranking", "AI-style task ranking engine recommending the highest-value work for the next session.", ["analysis"], "1"),
    "/api/sessions": ("getSessions", "List available sessions", "Returns metadata for all recorded Awake development sessions.", ["sessions"], "1"),
    "/api/replay/<n>": ("replaySession", "Replay a specific session", "Reconstruct full narrative and diff for session N from AWAKE_LOG.md.", ["sessions"], "1"),
    "/api/diff/<n>": ("getDiff", "Diff for a specific session", "Markdown summary of git changes introduced in session N.", ["sessions"], "1"),
    "/api/blame": ("getBlame", "Human vs AI attribution", "Git blame analysis: % of lines attributed to human vs autonomous AI commits.", ["analysis"], "13"),
    "/api/security": ("getSecurity", "Security audit", "10-check security audit for common Python anti-patterns; A-F grade.", ["analysis"], "13"),
    "/api/deadcode": ("getDeadCode", "Dead code detector", "AST-based unused function, class, and import detection.", ["analysis"], "13"),
    "/api/coveragemap": ("getCoverageMap", "Test coverage heat map", "Cross-reference src/X.py vs tests/test_X.py to rank weakest coverage areas.", ["analysis"], "13"),
    "/api/maturity": ("getMaturity", "Module maturity scores", "Composite 0-100 maturity score per module: tests, docs, complexity, age, coupling.", ["analysis"], "14"),
    "/api/dna": ("getDNA", "Repo DNA fingerprint", "6-channel visual repo signature and deterministic hex digest.", ["analysis"], "14"),
    "/api/story": ("getStory", "Repo narrative", "Prose summary of the repo's evolution, extracted from session log.", ["analysis"], "14"),
    "/api/benchmark": ("getBenchmark", "Performance benchmarks", "Timed execution of all analysis modules with regression detection.", ["analysis"], "15"),
    "/api/gitstats": ("getGitStats", "Git statistics deep-dive", "Churn, velocity, commit frequency, and PR size histograms.", ["analysis"], "15"),
    "/api/badges": ("getBadges", "Shields.io badge metadata", "Live metrics formatted for Shields.io README badges.", ["meta"], "15"),
    "/api/teach/<module>": ("teachModule", "Module tutorial", "AST-based tutorial explaining a module's structure, public API, and usage.", ["analysis"], "1"),
    "/api/audit": ("getAudit", "Comprehensive repo audit", "Weighted composite A-F grade combining health, security, dead code, coverage, complexity.", ["analysis"], "16"),
    "/api/semver": ("getSemver", "Semantic version analysis", "Conventional Commits -> semver bump recommendation (major/minor/patch).", ["analysis"], "16"),
    "/api/predict": ("getPredict", "Predictive session planner", "Five-signal module ranking predicting which areas need the most attention next.", ["analysis"], "16"),
    "/api/openapi": ("getOpenAPISpec", "OpenAPI specification", "The live OpenAPI 3.1 spec for the Awake API.", ["meta"], "17"),
    "/api/report": ("getReport", "Executive HTML report", "Combined HTML executive summary aggregating all analyses into a single document.", ["analysis"], "17"),
    "/api/modules": ("getModuleGraph", "Module interconnection graph", "Mermaid diagram source showing how all src/ modules interconnect.", ["analysis"], "17"),
    "/api/trends": ("getHistoricalTrends", "Historical trend data", "Session-over-session metrics for the React dashboard trend charts.", ["analysis"], "17"),
    "/api/commits": ("getCommitAnalysis", "Commit message analysis", "Quality scores and pattern extraction for all commit messages.", ["analysis"], "17"),
    "/api/diff-sessions/<a>/<b>": ("diffSessions", "Compare two sessions", "Rich delta analysis comparing any two sessions by number.", ["sessions"], "17"),
    "/api/test-quality": ("getTestQuality", "Test quality analysis", "Grade tests by assertion density, edge case coverage, and mock usage.", ["analysis"], "17"),
    "/api/plugins": ("getPlugins", "Plugin registry", "List all registered plugins from awake.toml.", ["meta"], "17"),
    "/api": ("getIndex", "API index", "List all available endpoints with metadata.", ["meta"], "1"),
}

_PARAMETERIZED: dict[str, list[OpenAPIParameter]] = {
    "/api/replay/<n>": [OpenAPIParameter(name="n", location="path", description="Session number (1-based)", required=True, schema_type="integer", schema_format="int32")],
    "/api/diff/<n>": [OpenAPIParameter(name="n", location="path", description="Session number (1-based)", required=True, schema_type="integer", schema_format="int32")],
    "/api/teach/<module>": [OpenAPIParameter(name="module", location="path", description="Module name (e.g. health, security, maturity)", required=True)],
    "/api/diff-sessions/<a>/<b>": [
        OpenAPIParameter(name="a", location="path", description="Session A number", required=True, schema_type="integer"),
        OpenAPIParameter(name="b", location="path", description="Session B number", required=True, schema_type="integer"),
    ],
}

_COMMON_FORMAT_PARAM = OpenAPIParameter(name="format", location="query", description="Response format override: json | markdown", required=False)


def generate_openapi_spec(repo_root: Optional[Path] = None) -> OpenAPISpec:
    """Generate the full OpenAPI 3.1 spec from the server route catalogue."""
    version = "1.0.0"
    if repo_root:
        pp = repo_root / "pyproject.toml"
        if pp.exists():
            import re as _re
            text = pp.read_text()
            m = _re.search(r'version\s*=\s*"([^"]+)"', text)
            if m:
                version = m.group(1)
    spec = OpenAPISpec(
        title="Awake API",
        version=version,
        description="REST API for the Awake autonomous development analysis system. All endpoints return JSON. Run `awake serve` to start the server.",
    )
    for route, (op_id, summary, desc, tags, session) in _ROUTE_CATALOGUE.items():
        params = list(_PARAMETERIZED.get(route, []))
        if route not in _PARAMETERIZED and route not in ("/api", "/api/"):
            params.append(_COMMON_FORMAT_PARAM)
        op = OpenAPIOperation(
            operation_id=op_id,
            summary=summary,
            description=desc,
            tags=tags,
            parameters=params,
            session_added=session,
        )
        spec.paths.append(OpenAPIPath(path=route, get=op))
    return spec


def _dict_to_yaml(obj: Any, indent: int = 0) -> str:
    """Minimal YAML emitter sufficient for OpenAPI documents."""
    pad = "  " * indent
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_str = str(k)
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{key_str}:")
                lines.append(_dict_to_yaml(v, indent + 1))
            else:
                lines.append(f"{pad}{key_str}: {_yaml_scalar(v)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                first_line = _dict_to_yaml(item, indent + 1).lstrip()
                lines.append(f"{pad}- {first_line}")
            else:
                lines.append(f"{pad}- {_yaml_scalar(item)}")
    else:
        return f"{pad}{_yaml_scalar(obj)}"
    return "\n".join(lines)


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if any(c in s for c in (":", "#", "{", "}", "[", "]", ",", "&", "*", "?", "|", "-", "<", ">", "=", "!", "%", "@", "`", "'", "\"")):
        escaped = s.replace("\\", "\\\\").replace("\"", "\\\"")
        return f'"{escaped}"'
    return s
