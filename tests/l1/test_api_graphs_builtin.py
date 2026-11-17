"""内置 default 图的写保护：工厂、保存、删除都不能动它（SPEC-037）。"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.server.api import graph, tools


def _client():
    app = FastAPI()
    app.include_router(graph.router)
    return TestClient(app)


def test_save_default_graph_rejected() -> None:
    """SPEC-037：画布保存 default 直接 400，避免被启动修复覆盖。"""
    resp = _client().post("/api/graphs/default", json={"name": "default"})

    assert resp.status_code == 400
    assert "内置图" in resp.json()["detail"]


def test_uninstall_default_graph_rejected() -> None:
    """SPEC-037：市场卸载接口不能删除 default。"""
    with pytest.raises(HTTPException) as exc:
        tools.uninstall_graph_api(tools.UninstallGraphReq(name="default"))

    assert exc.value.status_code == 400
    assert "内置图" in exc.value.detail
