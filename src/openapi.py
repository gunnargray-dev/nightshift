"""OpenAPI spec generation helpers."""

import inspect
import json
import re
from typing import Any, Callable, Optional, get_type_hints


def _python_type_to_json_schema(annotation) -> dict:
    """Convert a Python type annotation to a JSON Schema dict."""
    origin = getattr(annotation, "__origin__", None)

    # Handle Optional[X] -> {"oneOf": [{...}, {"type": "null"}]}
    if origin is type(None):
        return {"type": "null"}

    import types

    if origin is types.UnionType or str(origin) == "typing.Union":
        args = annotation.__args__
        non_none = [a for a in args if a is not type(None)]
        has_none = any(a is type(None) for a in args)
        schemas = [_python_type_to_json_schema(a) for a in non_none]
        if has_none:
            schemas.append({"type": "null"})
        if len(schemas) == 1:
            return schemas[0]
        return {"oneOf": schemas}

    if origin is list:
        item_args = getattr(annotation, "__args__", None)
        items = _python_type_to_json_schema(item_args[0]) if item_args else {}
        return {"type": "array", "items": items}

    if origin is dict:
        return {"type": "object"}

    # Primitive mappings
    primitive_map = {
        str: {"type": "string"},
        int: {"type": "integer"},
        float: {"type": "number"},
        bool: {"type": "boolean"},
        type(None): {"type": "null"},
    }
    if annotation in primitive_map:
        return primitive_map[annotation]

    # Fallback
    return {"type": "string"}


def _parse_docstring(
    docstring: Optional[str],
) -> tuple[str, dict[str, str]]:
    """Return (summary, {param_name: description}) from a numpy/google docstring."""
    if not docstring:
        return "", {}

    lines = inspect.cleandoc(docstring).splitlines()
    summary_lines = []
    param_descs: dict[str, str] = {}

    in_params = False
    current_param: Optional[str] = None

    for line in lines:
        stripped = line.strip()

        # Detect "Args:" / "Parameters:" section header
        if re.match(r"^(Args|Arguments|Parameters):\s*$", stripped, re.IGNORECASE):
            in_params = True
            current_param = None
            continue

        # Detect another section header -> stop collecting params
        if re.match(r"^[A-Za-z][\w ]+:\s*$", stripped) and in_params:
            in_params = False
            current_param = None
            continue

        if in_params:
            # Indented continuation of previous param
            indent = len(line) - len(line.lstrip())
            if indent >= 4 and current_param:
                param_descs[current_param] += " " + stripped
            else:
                # New param line: "name (type): description" or "name: description"
                m = re.match(r"^([\w]+)(?:\s*\([^)]*\))?:\s*(.*)", stripped)
                if m:
                    current_param = m.group(1)
                    param_descs[current_param] = m.group(2).strip()
        else:
            if not in_params and not summary_lines and not stripped:
                continue
            if not in_params:
                summary_lines.append(stripped)

    summary = " ".join(l for l in summary_lines if l).strip()
    return summary, param_descs


def function_to_openapi_tool(func: Callable) -> dict:
    """
    Convert a Python function to an OpenAI-style tool definition.

    Args:
        func: The function to convert.

    Returns:
        A dict matching the OpenAI tool JSON schema.
    """
    hints = get_type_hints(func)
    sig = inspect.signature(func)
    docstring = inspect.getdoc(func) or ""
    summary, param_descs = _parse_docstring(docstring)

    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        annotation = hints.get(name, str)
        schema = _python_type_to_json_schema(annotation)

        if name in param_descs:
            schema["description"] = param_descs[name]

        properties[name] = schema

        # Required if no default
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": summary,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def functions_to_openapi_spec(
    functions: list[Callable],
    title: str = "Generated API",
    version: str = "1.0.0",
    base_path: str = "/",
) -> dict:
    """
    Build a minimal OpenAPI 3.1 spec from a list of Python functions.

    Args:
        functions: List of callables to expose.
        title: API title.
        version: API version string.
        base_path: Base path prefix for all routes.

    Returns:
        An OpenAPI 3.1 specification dict.
    """
    paths: dict[str, Any] = {}

    for func in functions:
        hints = get_type_hints(func)
        sig = inspect.signature(func)
        docstring = inspect.getdoc(func) or ""
        summary, param_descs = _parse_docstring(docstring)

        route = f"{base_path.rstrip('/')}/{func.__name__.replace('_', '-')}"

        parameters = []
        request_body_props: dict[str, Any] = {}
        request_body_required: list[str] = []

        for name, param in sig.parameters.items():
            if name == "self":
                continue
            annotation = hints.get(name, str)
            schema = _python_type_to_json_schema(annotation)

            if name in param_descs:
                schema["description"] = param_descs[name]

            # Scalars as query params, complex types in body
            if schema.get("type") in ("string", "integer", "number", "boolean"):
                parameters.append(
                    {
                        "name": name,
                        "in": "query",
                        "required": param.default is inspect.Parameter.empty,
                        "schema": schema,
                    }
                )
            else:
                request_body_props[name] = schema
                if param.default is inspect.Parameter.empty:
                    request_body_required.append(name)

        operation: dict[str, Any] = {
            "operationId": func.__name__,
            "summary": summary,
            "parameters": parameters,
            "responses": {
                "200": {"description": "Success"},
                "422": {"description": "Validation error"},
            },
        }

        if request_body_props:
            operation["requestBody"] = {
                "required": bool(request_body_required),
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": request_body_props,
                            "required": request_body_required,
                        }
                    }
                },
            }

        paths[route] = {"post": operation}

    return {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "paths": paths,
    }


def export_openapi_json(
    functions: list[Callable],
    output_path: str,
    title: str = "Generated API",
    version: str = "1.0.0",
) -> None:
    """
    Write an OpenAPI 3.1 spec to a JSON file.

    Args:
        functions: Callables to expose.
        output_path: Destination file path.
        title: API title.
        version: API version string.
    """
    spec = functions_to_openapi_spec(functions, title=title, version=version)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2)
