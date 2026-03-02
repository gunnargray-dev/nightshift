"""OpenAPI 3.1 specification generator for the Awake REST API.

Inspects all ``@app.route`` (Flask-style) or ``@router.xxx`` (FastAPI-style)
decorators found in the repository source, then synthesises a minimal but
valid ``openapi.json`` / ``openapi.yaml`` document.

Features
--------
- Detects Flask ``@app.route``, ``@bp.route``, and FastAPI ``@router.*``
  decorators.
- Extracts path parameters from URL patterns (e.g. ``/users/<user_id>``).
- Reads function docstrings to populate ``summary`` and ``description``.
- Infers request/response models from type annotations where possible.
- Outputs JSON or YAML.

Public API
----------
- ``RouteInfo``            -- a single discovered route
- ``build_openapi_spec(repo_path)`` -> ``dict``
- ``save_openapi_spec(spec, out_path)``

CLI
---
    awake openapi [--yaml] [--output PATH]
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RouteInfo:
    """Metadata for a single HTTP route."""

    path: str  # URL path, e.g. "/users/{user_id}"
    methods: list[str]  # ["GET", "POST", ...]
    handler: str  # function name
    file: str  # relative source file
    line: int
    summary: str = ""
    description: str = ""
    params: list[str] = field(default_factory=list)  # path param names
    query_params: list[str] = field(default_factory=list)
    request_body_type: str | None = None
    response_type: str | None = None


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


_FLASK_METHODS_DEFAULT = ["GET"]
_FASTAPI_METHOD_MAP = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "patch": "PATCH",
    "delete": "DELETE",
    "options": "OPTIONS",
    "head": "HEAD",
}


def _flask_path_to_openapi(path: str) -> tuple[str, list[str]]:
    """Convert a Flask-style path to OpenAPI path and return param names.

    e.g. ``/users/<user_id>`` -> ``("/users/{user_id}", ["user_id"])``
    """
    params: list[str] = []

    def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
        inner = m.group(1)
        # Strip type converter prefix: int:user_id -> user_id
        if ":" in inner:
            inner = inner.split(":", 1)[1]
        params.append(inner)
        return f"{{{inner}}}"

    converted = re.sub(r"<([^>]+)>", _replace, path)
    return converted, params


def _extract_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str]:
    """Return (summary, description) from a function's docstring."""
    body = node.body
    if not body:
        return "", ""
    first = body[0]
    if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)):
        return "", ""
    doc: str = first.value.value
    lines = doc.strip().splitlines()
    summary = lines[0].strip() if lines else ""
    description = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""
    return summary, description


def _get_return_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Return the string representation of the return annotation, if any."""
    if node.returns is None:
        return None
    return ast.unparse(node.returns)


def _get_first_param_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """Return the annotation of the first non-self parameter (body type hint)."""
    args = node.args.args
    candidates = [a for a in args if a.arg not in ("self", "cls")]
    if not candidates:
        return None
    ann = candidates[0].annotation
    if ann is None:
        return None
    return ast.unparse(ann)


# ---------------------------------------------------------------------------
# Route collector
# ---------------------------------------------------------------------------


class _RouteCollector(ast.NodeVisitor):
    """Walk an AST file and collect route-decorated functions."""

    def __init__(self, rel_path: str) -> None:
        self._path = rel_path
        self.routes: list[RouteInfo] = []

    # ------------------------------------------------------------------
    def _try_flask_route(self, dec: ast.expr, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Attempt to parse *dec* as a Flask-style route decorator."""
        # Matches: app.route("/path", methods=[...])
        # or:      bp.route("/path")
        if not isinstance(dec, ast.Call):
            return False
        func = dec.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "route"
        ):
            return False

        # First positional arg is the URL path
        if not dec.args:
            return False
        path_node = dec.args[0]
        if not (isinstance(path_node, ast.Constant) and isinstance(path_node.value, str)):
            return False
        raw_path: str = path_node.value

        # Extract methods keyword
        methods: list[str] = list(_FLASK_METHODS_DEFAULT)
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, ast.List):
                methods = [
                    elt.value.upper()
                    for elt in kw.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]

        oa_path, params = _flask_path_to_openapi(raw_path)
        summary, description = _extract_docstring(func_node)

        self.routes.append(
            RouteInfo(
                path=oa_path,
                methods=methods,
                handler=func_node.name,
                file=self._path,
                line=func_node.lineno,
                summary=summary,
                description=description,
                params=params,
                response_type=_get_return_annotation(func_node),
                request_body_type=_get_first_param_annotation(func_node)
                if any(m in ("POST", "PUT", "PATCH") for m in methods)
                else None,
            )
        )
        return True

    def _try_fastapi_route(self, dec: ast.expr, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        """Attempt to parse *dec* as a FastAPI-style route decorator."""
        # Matches: router.get("/path"), router.post("/path"), ...
        if not isinstance(dec, ast.Call):
            return False
        func = dec.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in _FASTAPI_METHOD_MAP
        ):
            return False

        if not dec.args:
            return False
        path_node = dec.args[0]
        if not (isinstance(path_node, ast.Constant) and isinstance(path_node.value, str)):
            return False

        raw_path: str = path_node.value
        # FastAPI already uses {param} syntax
        params = re.findall(r"\{([^}]+)\}", raw_path)
        method = _FASTAPI_METHOD_MAP[func.attr]
        summary, description = _extract_docstring(func_node)

        self.routes.append(
            RouteInfo(
                path=raw_path,
                methods=[method],
                handler=func_node.name,
                file=self._path,
                line=func_node.lineno,
                summary=summary,
                description=description,
                params=params,
                response_type=_get_return_annotation(func_node),
                request_body_type=_get_first_param_annotation(func_node)
                if method in ("POST", "PUT", "PATCH")
                else None,
            )
        )
        return True

    # ------------------------------------------------------------------
    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Check function decorators for route declarations."""
        for dec in node.decorator_list:
            if self._try_flask_route(dec, node):
                break
            if self._try_fastapi_route(dec, node):
                break
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        """Visit a sync function definition."""
        self._visit_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        """Visit an async function definition."""
        self._visit_func(node)


# ---------------------------------------------------------------------------
# Spec builder
# ---------------------------------------------------------------------------


def _schema_for_type(type_str: str | None) -> dict[str, Any]:
    """Return a minimal JSON Schema object for the given Python type string."""
    if type_str is None:
        return {}
    mapping: dict[str, dict[str, Any]] = {
        "str": {"type": "string"},
        "int": {"type": "integer"},
        "float": {"type": "number"},
        "bool": {"type": "boolean"},
        "list": {"type": "array", "items": {}},
        "dict": {"type": "object"},
        "None": {"type": "null"},
    }
    return mapping.get(type_str, {"$ref": f"#/components/schemas/{type_str}"})


def build_openapi_spec(repo_path: str | Path) -> dict[str, Any]:
    """Scan *repo_path* and return an OpenAPI 3.1 spec as a dict.

    Parameters
    ----------
    repo_path:
        Root directory of the repository.

    Returns
    -------
    dict
        OpenAPI 3.1 specification dictionary.
    """
    root = Path(repo_path)
    routes: list[RouteInfo] = []

    for py_file in sorted(root.rglob("*.py")):
        rel = str(py_file.relative_to(root))
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (SyntaxError, OSError):
            continue
        collector = _RouteCollector(rel)
        collector.visit(tree)
        routes.extend(collector.routes)

    # Build paths object
    paths: dict[str, Any] = {}
    for route in routes:
        path_item = paths.setdefault(route.path, {})
        for method in route.methods:
            method_lower = method.lower()
            operation: dict[str, Any] = {}
            if route.summary:
                operation["summary"] = route.summary
            if route.description:
                operation["description"] = route.description
            operation["operationId"] = f"{route.handler}_{method_lower}"

            # Path parameters
            if route.params:
                operation["parameters"] = [
                    {
                        "name": p,
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                    for p in route.params
                ]

            # Request body
            if route.request_body_type:
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": _schema_for_type(route.request_body_type)
                        }
                    },
                }

            # Responses
            operation["responses"] = {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": _schema_for_type(route.response_type)
                        }
                    },
                }
            }

            path_item[method_lower] = operation

    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Awake API",
            "version": "0.1.0",
            "description": "Auto-generated OpenAPI specification for Awake.",
        },
        "paths": paths,
    }
    return spec


def save_openapi_spec(spec: dict[str, Any], out_path: str | Path) -> None:
    """Write *spec* to *out_path* as JSON (or YAML if the extension is .yaml/.yml).

    Parameters
    ----------
    spec:
        The OpenAPI spec dict to save.
    out_path:
        Destination file path.
    """
    out = Path(out_path)
    if out.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import]

            text = yaml.dump(spec, sort_keys=False, allow_unicode=True)
        except ImportError:
            # Fallback to JSON with .yaml extension (still valid for most tools)
            text = json.dumps(spec, indent=2)
    else:
        text = json.dumps(spec, indent=2)
    out.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the OpenAPI spec generator.

    Parameters
    ----------
    argv:
        Command-line arguments.

    Returns
    -------
    int
        Exit code.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        prog="awake openapi",
        description="Generate an OpenAPI 3.1 spec from route decorators.",
    )
    parser.add_argument("repo", nargs="?", default=".", help="Repo root")
    parser.add_argument("--yaml", action="store_true", help="Output YAML instead of JSON")
    parser.add_argument("--output", "-o", default="", help="Write output to file")
    args = parser.parse_args(argv)

    root = Path(args.repo).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    spec = build_openapi_spec(root)

    if args.output:
        save_openapi_spec(spec, args.output)
        print(f"OpenAPI spec written to {args.output}")
    elif args.yaml:
        try:
            import yaml  # type: ignore[import]

            print(yaml.dump(spec, sort_keys=False, allow_unicode=True))
        except ImportError:
            print(json.dumps(spec, indent=2))
    else:
        print(json.dumps(spec, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
