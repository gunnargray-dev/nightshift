"""OpenAPI spec generator for Awake.

Introspects the Flask (or FastAPI) application to produce an OpenAPI 3.0
specification in YAML or JSON.  The generator uses static analysis of route
decorators and type annotations -- no live server needed.

CLI
---
    awake openapi                  # Print YAML to stdout
    awake openapi --json           # Print JSON instead
    awake openapi --write          # Write docs/openapi.yaml
    awake openapi --validate       # Validate against jsonschema
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class RouteInfo:
    """Metadata extracted from a single route decorator."""

    path: str
    methods: list[str]
    func_name: str
    module: str
    summary: str = ""
    description: str = ""
    params: list[dict] = field(default_factory=list)
    request_body: Optional[dict] = None
    responses: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass
class OpenAPISpec:
    """A complete OpenAPI 3.0 specification."""

    title: str
    version: str
    description: str = ""
    routes: list[RouteInfo] = field(default_factory=list)
    components: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise the spec to a plain dictionary."""
        paths: dict[str, Any] = {}
        for route in self.routes:
            if route.path not in paths:
                paths[route.path] = {}
            for method in route.methods:
                m = method.lower()
                op: dict[str, Any] = {
                    "summary": route.summary or route.func_name,
                    "operationId": f"{route.func_name}_{m}",
                    "tags": route.tags or [route.module],
                    "responses": route.responses or {
                        "200": {"description": "Success"},
                        "400": {"description": "Bad request"},
                        "500": {"description": "Internal server error"},
                    },
                }
                if route.description:
                    op["description"] = route.description
                if route.params:
                    op["parameters"] = route.params
                if route.request_body:
                    op["requestBody"] = route.request_body
                paths[route.path][m] = op

        return {
            "openapi": "3.0.3",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
            },
            "paths": paths,
            "components": self.components,
        }

    def to_yaml(self) -> str:
        """Serialise the spec to YAML (no external deps)."""
        return _dict_to_yaml(self.to_dict())


# ---------------------------------------------------------------------------
# YAML serialiser (no PyYAML dependency)
# ---------------------------------------------------------------------------


def _yaml_value(val: Any, indent: int = 0) -> str:
    """Serialise a Python value to YAML scalar/collection form."""
    pad = "  " * indent
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        # Quote strings that look like YAML primitives or contain special chars
        needs_quote = (
            val in ("true", "false", "null", "yes", "no")
            or ":" in val
            or val.startswith("-")
            or "\n" in val
            or val == ""
        )
        if needs_quote:
            escaped = val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        return val
    if isinstance(val, list):
        if not val:
            return "[]"
        items = []
        for item in val:
            v = _yaml_value(item, indent + 1)
            if isinstance(item, dict):
                # Inline first key, indent rest
                sub = _dict_to_yaml(item, indent + 1)
                items.append(f"{pad}  -\n{sub}")
            else:
                items.append(f"{pad}  - {v}")
        return "\n" + "\n".join(items)
    if isinstance(val, dict):
        return "\n" + _dict_to_yaml(val, indent + 1)
    return str(val)


def _dict_to_yaml(d: dict, indent: int = 0) -> str:
    """Convert a nested dict to a YAML string."""
    pad = "  " * indent
    lines: list[str] = []
    for k, v in d.items():
        yaml_v = _yaml_value(v, indent)
        if yaml_v.startswith("\n"):
            lines.append(f"{pad}{k}:{yaml_v}")
        else:
            lines.append(f"{pad}{k}: {yaml_v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Route extractor
# ---------------------------------------------------------------------------


def _extract_routes(path: Path, repo_root: Path) -> list[RouteInfo]:
    """Extract route information from a single Python source file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    rel_module = str(path.relative_to(repo_root)).replace("/", ".")[:-3]
    routes: list[RouteInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            route_path, methods = _parse_route_decorator(decorator)
            if route_path is None:
                continue

            # Extract docstring
            summary = ""
            description = ""
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
                doc = node.body[0].value.value
                parts = doc.strip().split("\n", 1)
                summary = parts[0].strip()
                description = parts[1].strip() if len(parts) > 1 else ""

            # Extract path params from route pattern
            params = _extract_path_params(route_path)

            routes.append(
                RouteInfo(
                    path=route_path,
                    methods=methods,
                    func_name=node.name,
                    module=rel_module,
                    summary=summary,
                    description=description,
                    params=params,
                )
            )

    return routes


def _parse_route_decorator(
    decorator: ast.expr,
) -> tuple[Optional[str], list[str]]:
    """Return (path, methods) from a Flask/FastAPI route decorator, or (None, [])."""
    # Flask: @app.route('/path', methods=['GET', 'POST'])
    # FastAPI: @router.get('/path'), @router.post('/path')
    if not isinstance(decorator, ast.Call):
        return None, []

    func = decorator.func
    # FastAPI-style: router.get / router.post / ...
    if isinstance(func, ast.Attribute):
        method = func.attr.upper()
        if method in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            path_arg = decorator.args[0] if decorator.args else None
            if isinstance(path_arg, ast.Constant):
                return path_arg.value, [method]
        # Flask-style: app.route
        if func.attr == "route":
            path_arg = decorator.args[0] if decorator.args else None
            if not isinstance(path_arg, ast.Constant):
                return None, []
            route_path = path_arg.value
            methods = ["GET"]  # default
            for kw in decorator.keywords:
                if kw.arg == "methods" and isinstance(kw.value, ast.List):
                    methods = [
                        elt.value.upper()
                        for elt in kw.value.elts
                        if isinstance(elt, ast.Constant)
                    ]
            return route_path, methods

    return None, []


def _extract_path_params(route_path: str) -> list[dict]:
    """Extract path parameters from a Flask/FastAPI route pattern."""
    # Flask: <type:name> or <name>
    flask_params = re.findall(r"<(?:[a-z]+:)?([a-z_]+)>", route_path)
    # FastAPI: {name}
    fastapi_params = re.findall(r"\{([a-z_]+)\}", route_path)
    all_params = flask_params + fastapi_params
    return [
        {
            "name": p,
            "in": "path",
            "required": True,
            "schema": {"type": "string"},
        }
        for p in all_params
    ]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


def generate_openapi_spec(
    repo_root: Path,
    title: str = "Awake API",
    version: str = "1.0.0",
    description: str = "",
) -> OpenAPISpec:
    """Scan a repository and produce an OpenAPI spec object."""
    src_dir = repo_root / "src"
    if not src_dir.exists():
        src_dir = repo_root

    all_routes: list[RouteInfo] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        all_routes.extend(_extract_routes(py_file, repo_root))

    return OpenAPISpec(
        title=title,
        version=version,
        description=description or f"Auto-generated API spec for {title}",
        routes=all_routes,
    )


def validate_openapi_spec(spec_dict: dict) -> list[str]:
    """Validate an OpenAPI spec dict; returns a list of error strings."""
    errors: list[str] = []
    info = spec_dict.get("info", {})
    if not info.get("title"):
        errors.append("info.title is required")
    if not info.get("version"):
        errors.append("info.version is required")
    paths = spec_dict.get("paths", {})
    if not isinstance(paths, dict):
        errors.append("paths must be an object")
    else:
        for path, ops in paths.items():
            if not path.startswith("/"):
                errors.append(f"path '{path}' must start with '/'")
            for method, op in ops.items():
                if method.lower() not in ("get", "post", "put", "delete", "patch", "options", "head", "trace"):
                    errors.append(f"Invalid HTTP method '{method}' at '{path}'")
                if "responses" not in op:
                    errors.append(f"Missing 'responses' at {path}.{method}")
    return errors
