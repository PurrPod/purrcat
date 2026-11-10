#!/usr/bin/env python3
"""Generate ``docs/api/openapi.json`` / ``openapi.md`` from the FastAPI contract.

The application factory is the single source of truth: routes, parameters,
schemas and responses all come from ``create_app().openapi()``. Generation is
deterministic (sorted keys, fixed method order) so CI can diff the artifacts.

用法：
    uv run python scripts/gen_api_docs.py          # 写文件
    uv run python scripts/gen_api_docs.py --check  # 只校验，过期返回 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs" / "api"
OPENAPI_JSON = DOCS_DIR / "openapi.json"
OPENAPI_MD = DOCS_DIR / "openapi.md"

METHOD_ORDER = ("get", "post", "put", "patch", "delete")
DEFAULT_TAG = "Default"
_JSON_REF_PREFIX = "#/components/schemas/"
_HEADER = (
    "# PurrCat API 参考（生成物）\n"
    "\n"
    "> 本文件由 `scripts/gen_api_docs.py` 从 FastAPI 契约自动生成，禁止手动修改。\n"
    "> 更新：`uv run python scripts/gen_api_docs.py`\n"
    "> 校验：`uv run python scripts/check_api_docs.py`\n"
    "\n"
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_spec() -> dict[str, Any]:
    """Build the OpenAPI document from the production app (no server start)."""

    from src.server.app import create_app

    return create_app().openapi()


def render_json(spec: dict[str, Any]) -> str:
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _title_case(operation_id: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", operation_id or "")
    words = spaced.replace("_", " ").split()
    return " ".join(word[:1].upper() + word[1:] for word in words) or "Endpoint"


def _title(operation: dict[str, Any]) -> str:
    summary = operation.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary.strip()
    return _title_case(str(operation.get("operationId") or ""))


def _description(operation: dict[str, Any]) -> str:
    text = str(operation.get("description") or "").strip()
    if not text:
        return ""
    return re.split(r"\n\s*\n", text, maxsplit=1)[0].strip()


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _ref_name(schema: dict[str, Any]) -> str | None:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith(_JSON_REF_PREFIX):
        return ref[len(_JSON_REF_PREFIX) :]
    return None


def _resolve_schema(
    spec: dict[str, Any], schema: dict[str, Any]
) -> tuple[str | None, dict[str, Any]]:
    """Resolve a ``$ref`` one level; return (schema name, resolved schema)."""

    name = _ref_name(schema)
    if name is None:
        return None, schema
    component = spec.get("components", {}).get("schemas", {}).get(name, {})
    return name, component


def _type_label(spec: dict[str, Any], schema: Any) -> str:
    if not isinstance(schema, dict) or not schema:
        return "object"

    name = _ref_name(schema)
    if name:
        return name
    for combinator in ("anyOf", "oneOf"):
        options = schema.get(combinator)
        if isinstance(options, list):
            labels: list[str] = []
            for option in options:
                label = _type_label(spec, option)
                if label not in labels:
                    labels.append(label)
            return " | ".join(labels) if labels else "object"
    if isinstance(schema.get("allOf"), list) and schema["allOf"]:
        return " & ".join(_type_label(spec, item) for item in schema["allOf"])

    schema_type = schema.get("type")
    if schema_type == "array":
        return f"array[{_type_label(spec, schema.get('items', {}))}]"
    if isinstance(schema_type, str) and schema_type:
        return schema_type
    if "properties" in schema or "additionalProperties" in schema:
        return "object"
    return "object"


def _schema_label(spec: dict[str, Any], schema: Any) -> str:
    if not isinstance(schema, dict):
        return "-"
    name = _ref_name(schema)
    if name:
        return name
    return _type_label(spec, schema)


def _object_fields(
    spec: dict[str, Any], schema: dict[str, Any]
) -> tuple[str, dict[str, Any], list[str]]:
    """Return (display name, properties, required) expanding one level only."""

    name, resolved = _resolve_schema(spec, schema)
    label = name or str(resolved.get("title") or "Inline")

    if resolved.get("type") == "array" or "items" in resolved:
        item_name, item_schema = _resolve_schema(spec, resolved.get("items", {}))
        label = f"array[{item_name}]" if item_name else "array[object]"
        resolved = item_schema

    properties = resolved.get("properties")
    if not isinstance(properties, dict):
        properties = {}
    required = resolved.get("required")
    if not isinstance(required, list):
        required = []
    return label, properties, [str(item) for item in required]


def _pick_media(content: Any) -> tuple[str | None, dict[str, Any]]:
    if not isinstance(content, dict) or not content:
        return None, {}
    for media_type in (
        "application/json",
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    ):
        if media_type in content:
            return media_type, content[media_type].get("schema", {})
    media_type = sorted(content)[0]
    return media_type, content[media_type].get("schema", {})


def _parameter_rows(
    spec: dict[str, Any], parameters: list[dict[str, Any]]
) -> list[str]:
    rows: list[str] = []
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        schema = parameter.get("schema")
        if not isinstance(schema, dict):
            schema = {}
        description = parameter.get("description") or schema.get("description") or ""
        rows.append(
            "| {name} | {location} | {type} | {required} | {description} |".format(
                name=_cell(parameter.get("name", "-")),
                location=_cell(parameter.get("in", "-")),
                type=_cell(_type_label(spec, schema)),
                required="是" if parameter.get("required") else "否",
                description=_cell(description),
            )
        )
    return rows


def _request_body_lines(
    spec: dict[str, Any], request_body: dict[str, Any]
) -> list[str]:
    _, schema = _pick_media(request_body.get("content"))
    label, properties, required = _object_fields(spec, schema)

    lines = ["#### 请求体", "", f"**Schema**：`{_cell(label)}`", ""]
    if properties:
        lines.extend(
            [
                "| 字段 | 类型 | 必填 | 说明 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for field_name, field_schema in properties.items():
            if not isinstance(field_schema, dict):
                field_schema = {}
            lines.append(
                "| {name} | {type} | {required} | {description} |".format(
                    name=_cell(field_name),
                    type=_cell(_type_label(spec, field_schema)),
                    required="是" if field_name in required else "否",
                    description=_cell(field_schema.get("description", "")),
                )
            )
        lines.append("")
    return lines


def _status_sort_key(code: str) -> tuple[int, Any]:
    try:
        return (0, int(code))
    except (TypeError, ValueError):
        return (1, str(code))


def _response_rows(spec: dict[str, Any], responses: Any) -> list[str]:
    if not isinstance(responses, dict) or not responses:
        return []

    rows = ["| 状态码 | 描述 | Schema |", "| --- | --- | --- |"]
    for code in sorted(responses, key=_status_sort_key):
        response = responses[code]
        if not isinstance(response, dict):
            response = {}
        _, schema = _pick_media(response.get("content"))
        rows.append(
            "| {code} | {description} | {schema} |".format(
                code=_cell(code),
                description=_cell(response.get("description", "")),
                schema=_cell(_schema_label(spec, schema) if schema else "-"),
            )
        )
    return rows


def _endpoint_lines(
    spec: dict[str, Any], path: str, method: str, operation: dict[str, Any]
) -> list[str]:
    lines = [f"### `{method.upper()} {path}`", "", f"**标题**：{_title(operation)}", ""]

    description = _description(operation)
    if description:
        lines.extend([description, ""])

    parameters = [
        item for item in operation.get("parameters", []) if isinstance(item, dict)
    ]
    if parameters:
        lines.extend(
            [
                "#### 参数",
                "",
                "| 名称 | 位置 | 类型 | 必填 | 说明 |",
                "| --- | --- | --- | --- | --- |",
                *_parameter_rows(spec, parameters),
                "",
            ]
        )

    request_body = operation.get("requestBody")
    if isinstance(request_body, dict):
        lines.extend(_request_body_lines(spec, request_body))

    response_rows = _response_rows(spec, operation.get("responses"))
    if response_rows:
        lines.extend(["#### 响应", "", *response_rows, ""])

    return lines


def render_markdown(spec: dict[str, Any]) -> str:
    groups: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        paths = {}

    for path in sorted(paths):
        path_item = paths[path]
        if not isinstance(path_item, dict):
            continue
        for method in METHOD_ORDER:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            tags = operation.get("tags")
            tag = str(tags[0]) if isinstance(tags, list) and tags else DEFAULT_TAG
            groups.setdefault(tag, []).append((path, method, operation))

    lines = [_HEADER.rstrip("\n"), ""]
    for tag in sorted(groups):
        lines.extend([f"## {tag}", ""])
        for path, method, operation in groups[tag]:
            lines.extend(_endpoint_lines(spec, path, method, operation))

    return "\n".join(lines).rstrip("\n") + "\n"


def build_documents() -> dict[Path, str]:
    spec = build_spec()
    return {
        OPENAPI_JSON: render_json(spec),
        OPENAPI_MD: render_markdown(spec),
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def write_documents(documents: dict[Path, str] | None = None) -> list[Path]:
    documents = documents or build_documents()
    for path, content in documents.items():
        _write(path, content)
    return list(documents)


def check_documents(documents: dict[Path, str] | None = None) -> list[Path]:
    """Return generated files that are missing or differ from the contract."""

    documents = documents or build_documents()
    stale: list[Path] = []
    for path, content in documents.items():
        try:
            current = path.read_bytes()
        except OSError:
            stale.append(path)
            continue
        if current != content.encode("utf-8"):
            stale.append(path)
    return stale


def relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify docs/api/openapi.{json,md}."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只比较生成物，不落盘；有过期文件时退出码为 1。",
    )
    args = parser.parse_args(argv)

    if args.check:
        stale = check_documents()
        if stale:
            print("[ERROR] 生成物过期，请运行 uv run python scripts/gen_api_docs.py")
            for path in stale:
                print(f"  {relative_path(path)}")
            return 1
        print("[OK] docs/api/openapi.json 与 openapi.md 已与 FastAPI 契约一致")
        return 0

    for path in write_documents():
        print(f"[OK] 已生成 {relative_path(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
