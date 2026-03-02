"""OpenAPI specification generator."""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class OpenAPIConfig:
    """Configuration for OpenAPI generation."""

    model: str = "gpt-4o-mini"
    title: str = "My API"
    version: str = "0.1.0"
    description: str = ""
    servers: list[str] = field(default_factory=lambda: ["http://localhost:8000"])
    include_examples: bool = True
    output_format: str = "json"  # json | yaml


@dataclass
class RouteInfo:
    """Parsed information about an API route."""

    method: str
    path: str
    function_name: str
    docstring: Optional[str]
    params: list[str]
    body_model: Optional[str]
    response_model: Optional[str]
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Route extraction
# ---------------------------------------------------------------------------


def _extract_fastapi_routes(tree: ast.Module, source: str) -> list[RouteInfo]:
    """Extract route information from a FastAPI application AST."""
    routes: list[RouteInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            method = None
            path_str = None

            # Handle router.get("/path") and app.get("/path") patterns
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                attr = decorator.func.attr
                if attr in ("get", "post", "put", "patch", "delete", "head", "options"):
                    method = attr.upper()
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        path_str = decorator.args[0].value

            if method is None or path_str is None:
                continue

            # Extract parameters
            params = [a.arg for a in node.args.args if a.arg not in ("self", "request")]

            # Extract docstring
            docstring = None
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            ):
                docstring = node.body[0].value.value

            # Extract response model from decorator kwargs
            response_model = None
            for kw in decorator.keywords:
                if kw.arg == "response_model" and isinstance(kw.value, ast.Name):
                    response_model = kw.value.id

            # Extract body model (Pydantic model in params)
            body_model = None
            for arg in node.args.args:
                if arg.annotation and isinstance(arg.annotation, ast.Name):
                    # Heuristic: capitalized name likely a Pydantic model
                    if arg.annotation.id[0].isupper():
                        body_model = arg.annotation.id
                        break

            routes.append(
                RouteInfo(
                    method=method,
                    path=path_str,
                    function_name=node.name,
                    docstring=docstring,
                    params=params,
                    body_model=body_model,
                    response_model=response_model,
                )
            )

    return routes


def _extract_flask_routes(tree: ast.Module, source: str) -> list[RouteInfo]:
    """Extract route information from a Flask application AST."""
    routes: list[RouteInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            if not (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "route"
            ):
                continue

            path_str = None
            methods = ["GET"]

            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                path_str = decorator.args[0].value

            for kw in decorator.keywords:
                if kw.arg == "methods" and isinstance(kw.value, ast.List):
                    methods = [
                        elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)
                    ]

            if path_str is None:
                continue

            docstring = None
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            ):
                docstring = node.body[0].value.value

            for method in methods:
                routes.append(
                    RouteInfo(
                        method=method,
                        path=path_str,
                        function_name=node.name,
                        docstring=docstring,
                        params=[],
                        body_model=None,
                        response_model=None,
                    )
                )

    return routes


def extract_routes(source: str) -> list[RouteInfo]:
    """Auto-detect framework and extract routes."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    # Prefer FastAPI if detected
    if "fastapi" in source.lower():
        return _extract_fastapi_routes(tree, source)
    if "flask" in source.lower():
        return _extract_flask_routes(tree, source)
    # Fallback: try both
    routes = _extract_fastapi_routes(tree, source)
    if not routes:
        routes = _extract_flask_routes(tree, source)
    return routes


# ---------------------------------------------------------------------------
# Spec builder
# ---------------------------------------------------------------------------


def _route_to_operation(route: RouteInfo, include_examples: bool) -> dict[str, Any]:
    """Convert a :class:`RouteInfo` to an OpenAPI operation object."""
    op: dict[str, Any] = {
        "operationId": route.function_name,
        "summary": route.docstring or route.function_name.replace("_", " ").title(),
        "responses": {
            "200": {"description": "Successful response"},
        },
    }
    if route.tags:
        op["tags"] = route.tags
    if route.params:
        op["parameters"] = [
            {
                "name": p,
                "in": "path" if f"{{{p}}}" in route.path else "query",
                "required": f"{{{p}}}" in route.path,
                "schema": {"type": "string"},
            }
            for p in route.params
        ]
    if route.body_model:
        op["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{route.body_model}"}
                }
            },
        }
    if route.response_model:
        op["responses"]["200"]["content"] = {
            "application/json": {
                "schema": {"$ref": f"#/components/schemas/{route.response_model}"}
            }
        }
    return op


def build_openapi_spec(routes: list[RouteInfo], config: OpenAPIConfig) -> dict[str, Any]:
    """Build an OpenAPI 3.1 spec dict from extracted routes."""
    paths: dict[str, Any] = {}
    for route in routes:
        if route.path not in paths:
            paths[route.path] = {}
        paths[route.path][route.method.lower()] = _route_to_operation(
            route, config.include_examples
        )

    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": config.title,
            "version": config.version,
            "description": config.description,
        },
        "servers": [{"url": s} for s in config.servers],
        "paths": paths,
    }
    return spec


def generate_openapi_spec(
    root: Path,
    config: Optional[OpenAPIConfig] = None,
    glob_pattern: str = "**/*.py",
) -> dict[str, Any]:
    """Scan *root* for API routes and return an OpenAPI spec dict."""
    cfg = config or OpenAPIConfig()
    all_routes: list[RouteInfo] = []
    for py_file in sorted(root.glob(glob_pattern)):
        source = py_file.read_text(encoding="utf-8", errors="replace")
        all_routes.extend(extract_routes(source))
    return build_openapi_spec(all_routes, cfg)
