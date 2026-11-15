"""MCP 设置页的工具清单接口：把 schema 缓存按服务器分组（SPEC-025）。"""

from __future__ import annotations

from src.server.api import config as config_api


def test_mcp_tools_grouped_by_server(monkeypatch):
    monkeypatch.setattr(
        "src.tool.callmcp.schema_manager.load_cached_schemas",
        lambda: [
            {
                "server": "cesium-map",
                "function": {"name": "show-map", "description": "展示地图"},
            },
            {
                "server": "cesium-map",
                "function": {"name": "geocode", "description": ""},
            },
            {"server": "", "function": {"name": "orphan"}},
            {"server": "broken", "function": {}},
        ],
    )

    out = config_api.api_get_mcp_tools()

    assert out["servers"] == {
        "cesium-map": [
            {"name": "show-map", "description": "展示地图"},
            {"name": "geocode", "description": ""},
        ]
    }
