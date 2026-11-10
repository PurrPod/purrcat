"""OpenAPI 文档生成器（SPEC-023）。"""

from __future__ import annotations

import re

from fastapi import FastAPI, Query
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from scripts import gen_api_docs


class ItemIn(BaseModel):
    name: str = Field(description="display name")
    count: int = 1


class ItemOut(BaseModel):
    id: str
    label: str


def _demo_spec() -> dict:
    app = FastAPI()

    @app.get("/alpha/{item_id}", tags=["alpha"], operation_id="fetch_item")
    def read_item(
        item_id: str,
        q: str | None = Query(default=None, description="query text"),
    ):
        """Fetch a single item.

        Longer details should not be rendered.
        """
        return {"item_id": item_id}

    @app.get("/items", tags=["beta"], operation_id="list_items")
    def list_items():
        """List items."""
        return []

    @app.get("/items/extra", tags=["beta"], operation_id="list_extra_items")
    def list_extra_items():
        return []

    @app.post("/items", tags=["beta"], response_model=ItemOut)
    def create_item(payload: ItemIn):
        """Create one item."""
        return {"id": "1", "label": payload.name}

    spec = app.openapi()
    # FastAPI 会从函数名生成 summary；删除以验证 operationId 兜底。
    del spec["paths"]["/alpha/{item_id}"]["get"]["summary"]
    return spec


def test_render_groups_tags_and_sorts_paths_and_methods():
    markdown = gen_api_docs.render_markdown(_demo_spec())

    assert markdown.index("## alpha") < markdown.index("## beta")
    assert markdown.index("### `GET /items`") < markdown.index("### `POST /items`")
    assert markdown.index("### `POST /items`") < markdown.index(
        "### `GET /items/extra`"
    )


def test_render_parameter_table_keeps_path_and_query_rows():
    markdown = gen_api_docs.render_markdown(_demo_spec())

    assert "#### 参数" in markdown
    assert "| item_id | path | string | 是 |  |" in markdown
    assert "| q | query | string \\| null | 否 | query text |" in markdown


def test_render_request_body_expands_schema_one_level():
    markdown = gen_api_docs.render_markdown(_demo_spec())

    assert "**Schema**：`ItemIn`" in markdown
    assert "| name | string | 是 | display name |" in markdown
    assert "| count | integer | 否 |  |" in markdown


def test_render_response_uses_schema_name():
    markdown = gen_api_docs.render_markdown(_demo_spec())

    assert "| 200 | Successful Response | ItemOut |" in markdown
    assert "| 422 | Validation Error | HTTPValidationError |" in markdown


def test_render_falls_back_to_operation_id_and_first_paragraph():
    markdown = gen_api_docs.render_markdown(_demo_spec())

    assert "**标题**：Fetch Item" in markdown
    assert "Fetch a single item." in markdown
    assert "Longer details" not in markdown


def test_render_skips_empty_sections():
    markdown = gen_api_docs.render_markdown(_demo_spec())
    section = markdown.split("### `GET /items/extra`", 1)[1].split("\n### ", 1)[0]

    assert "#### 参数" not in section
    assert "#### 请求体" not in section
    assert "#### 响应" in section


def test_check_mode_passes_when_files_match(tmp_path, monkeypatch):
    document = tmp_path / "openapi.md"
    documents = {document: "# generated\n"}
    monkeypatch.setattr(gen_api_docs, "build_documents", lambda: documents)
    gen_api_docs.write_documents(documents)

    assert gen_api_docs.main(["--check"]) == 0


def test_check_mode_fails_after_tampering(tmp_path, monkeypatch):
    document = tmp_path / "openapi.md"
    documents = {document: "# generated\n"}
    monkeypatch.setattr(gen_api_docs, "build_documents", lambda: documents)
    gen_api_docs.write_documents(documents)
    document.write_text("# tampered\n", encoding="utf-8")

    assert gen_api_docs.main(["--check"]) == 1


def test_check_mode_fails_when_file_is_missing(tmp_path, monkeypatch):
    documents = {tmp_path / "openapi.md": "# generated\n"}
    monkeypatch.setattr(gen_api_docs, "build_documents", lambda: documents)

    assert gen_api_docs.main(["--check"]) == 1


def _normalized(path: str) -> str:
    return re.sub(r"\{([^}:]+):[^}]+\}", r"{\1}", path)


def test_create_app_route_table_is_port_independent():
    from src.server.app import create_app

    offline = create_app()
    online = create_app(8000)

    def _routes(app):
        return [(route.path, getattr(route, "methods", None)) for route in app.routes]

    assert _routes(offline) == _routes(online)
    assert offline.router.on_startup == []
    assert len(online.router.on_startup) == 1


def test_real_app_openapi_covers_all_api_routes():
    from src.server.app import create_app

    app = create_app()
    spec = app.openapi()
    assert spec["paths"]

    generated = {
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if method in gen_api_docs.METHOD_ORDER
    }

    expected = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        path = _normalized(route.path)
        if not (path.startswith("/api") or path.startswith("/acp")):
            continue
        for method in route.methods or ():
            if method.lower() in gen_api_docs.METHOD_ORDER:
                expected.add((method.upper(), path))

    assert expected
    assert expected <= generated, expected - generated
