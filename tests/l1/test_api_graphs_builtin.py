"""内置图的写保护：工厂、保存、删除都不能动它们（SPEC-037 / SPEC-040）。"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.harness.graph_init import BUILTIN_GRAPH_NAMES
from src.server.api import graph, tools


def _client():
    app = FastAPI()
    app.include_router(graph.router)
    return TestClient(app)


@pytest.mark.parametrize("name", BUILTIN_GRAPH_NAMES)
def test_save_builtin_graph_rejected(name: str) -> None:
    """SPEC-037：画布保存内置图直接 400，避免被启动修复覆盖。"""
    resp = _client().post(f"/api/graphs/{name}", json={"name": name})

    assert resp.status_code == 400
    assert "内置图" in resp.json()["detail"]


@pytest.mark.parametrize("name", BUILTIN_GRAPH_NAMES)
def test_uninstall_builtin_graph_rejected(name: str) -> None:
    """SPEC-040：市场卸载接口不能删除任何内置图。"""
    with pytest.raises(HTTPException) as exc:
        tools.uninstall_graph_api(tools.UninstallGraphReq(name=name))

    assert exc.value.status_code == 400
    assert "内置图" in exc.value.detail
