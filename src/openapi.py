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
            if p.get:
                op = p.get
                tags = ", ".join(op.tags)
                lines.append(
                    f"| `{p.path}` | `{op.operation_id}` | {tags} | {op.summary} |"
                )
        return "\n".join(lines)


def _dict_to_yaml(obj: Any, indent: int = 0) -> str:
    """Recursively convert a dict/list/scalar to a YAML string."""
    pad = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            return "{}\n"
        lines = []
        for k, v in obj.items():
            v_yaml = _dict_to_yaml(v, indent + 1)
            if v_yaml.startswith("\n") or isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:\n{v_yaml}")
            else:
                lines.append(f"{pad}{k}: {v_yaml}")
        return "\n".join(lines) + "\n"
    elif isinstance(obj, list):
        if not obj:
            return "[]\n"
        lines = []
        for item in obj:
            item_yaml = _dict_to_yaml(item, indent + 1)
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-\n{item_yaml}")
            else:
                lines.append(f"{pad}- {item_yaml.rstrip()}")
        return "\n".join(lines) + "\n"
    elif isinstance(obj, bool):
        return "true\n" if obj else "false\n"
    elif isinstance(obj, (int, float)):
        return f"{obj}\n"
    elif obj is None:
        return "null\n"
    else:
        s = str(obj)
        needs_quote = (
            ":" in s or "#" in s or "\n" in s or s in ("true", "false", "null", "yes", "no")
            or s.startswith(("{", "[", "'", '"', "|", ">", "!", "&", "*", "?"))
        )
        if needs_quote:
            escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"\n'
        return f"{s}\n"


def build_spec() -> OpenAPISpec:
    """Build the complete OpenAPI specification for the Awake API.

    Returns
    -------
    OpenAPISpec
        The fully populated specification object.
    """
    spec = OpenAPISpec(
        title="Awake API",
        version="1.0.0",
        description=(
            "Awake is an autonomous AI coding assistant that monitors your repo, "
            "scores code health, opens PRs, and keeps everything documented. "
            "This API exposes all analysis and session management endpoints."
        ),
    )

    spec.paths.append(
        OpenAPIPath(
            path="/ping",
            get=OpenAPIOperation(
                operation_id="ping",
                summary="Health check",
                description="Returns a simple pong response to confirm the server is alive.",
                tags=["meta"],
                response_description="Server is alive",
                response_example={"pong": True},
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/status",
            get=OpenAPIOperation(
                operation_id="status",
                summary="Server status",
                description="Returns server version, uptime, and a list of registered routes.",
                tags=["meta"],
                response_description="Server status object",
                response_example={"version": "1.0.0", "uptime_s": 42.3, "routes": ["/ping"]},
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/sessions",
            get=OpenAPIOperation(
                operation_id="list_sessions",
                summary="List all sessions",
                description="Returns a list of all recorded Awake sessions.",
                tags=["sessions"],
                response_description="Array of session summaries",
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/sessions/<session_id>",
            get=OpenAPIOperation(
                operation_id="get_session",
                summary="Get a session by ID",
                tags=["sessions"],
                parameters=[
                    OpenAPIParameter(
                        name="session_id",
                        location="path",
                        description="The session UUID",
                        required=True,
                    )
                ],
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/sessions/<session_id>/replay",
            get=OpenAPIOperation(
                operation_id="replay_session",
                summary="Replay a session",
                description="Reconstruct what happened during a session.",
                tags=["sessions"],
                parameters=[
                    OpenAPIParameter(
                        name="session_id",
                        location="path",
                        description="The session UUID",
                        required=True,
                    )
                ],
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/analyze/health",
            get=OpenAPIOperation(
                operation_id="analyze_health",
                summary="Run health analysis",
                description="Scores code health across all files in the repo.",
                tags=["analysis"],
                response_description="Health report",
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/analyze/trends",
            get=OpenAPIOperation(
                operation_id="analyze_trends",
                summary="Analyse trends",
                description="Returns historical health-score trends.",
                tags=["analysis"],
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/analyze/modules",
            get=OpenAPIOperation(
                operation_id="analyze_modules",
                summary="Analyse module graph",
                description="Returns the inter-module dependency graph.",
                tags=["analysis"],
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/analyze/pr",
            get=OpenAPIOperation(
                operation_id="analyze_pr",
                summary="Score a pull request",
                tags=["analysis"],
                parameters=[
                    OpenAPIParameter(
                        name="pr",
                        location="query",
                        description="PR number",
                        required=True,
                        schema_type="integer",
                    )
                ],
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/analyze/docstrings",
            get=OpenAPIOperation(
                operation_id="analyze_docstrings",
                summary="Scan for missing docstrings",
                tags=["analysis"],
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/analyze/tests",
            get=OpenAPIOperation(
                operation_id="analyze_tests",
                summary="Grade test quality",
                tags=["analysis"],
            ),
        )
    )
    spec.paths.append(
        OpenAPIPath(
            path="/analyze/openapi",
            get=OpenAPIOperation(
                operation_id="get_openapi_spec",
                summary="Return this OpenAPI specification",
                tags=["meta"],
                parameters=[
                    OpenAPIParameter(
                        name="format",
                        location="query",
                        description="Response format: json or yaml",
                        required=False,
                        schema_type="string",
                    )
                ],
            ),
        )
    )

    return spec


def save_spec(spec: OpenAPISpec, repo_path: str | Path) -> tuple[Path, Path]:
    """Persist the OpenAPI spec as JSON and YAML under ``docs/``.

    Parameters
    ----------
    spec:
        The spec to save.
    repo_path:
        Repository root.

    Returns
    -------
    tuple[Path, Path]
        Paths to the JSON and YAML files.
    """
    docs = Path(repo_path) / "docs"
    docs.mkdir(exist_ok=True)
    json_path = docs / "openapi.json"
    yaml_path = docs / "openapi.yaml"
    json_path.write_text(json.dumps(spec.to_dict(), indent=2) + "\n", encoding="utf-8")
    yaml_path.write_text(spec.to_yaml(), encoding="utf-8")
    return json_path, yaml_path


def main(argv=None) -> int:
    """CLI entry point for OpenAPI spec generation."""
    import argparse

    p = argparse.ArgumentParser(prog="awake-openapi")
    p.add_argument(
        "--format",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="Output format (default: json)",
    )
    p.add_argument("--write", action="store_true", help="Write docs/openapi.{json,yaml}")
    p.add_argument("--repo", default=None, help="Repository root (default: auto-detect)")
    args = p.parse_args(argv)

    if args.repo:
        repo_path = Path(args.repo).expanduser().resolve()
    else:
        repo_path = Path(__file__).resolve().parents[1]

    spec = build_spec()

    if args.write:
        json_path, yaml_path = save_spec(spec, repo_path)
        print(f"  Wrote {json_path}")
        print(f"  Wrote {yaml_path}")
        return 0

    if args.format == "yaml":
        print(spec.to_yaml())
    elif args.format == "markdown":
        print(spec.to_markdown())
    else:
        print(json.dumps(spec.to_dict(), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
