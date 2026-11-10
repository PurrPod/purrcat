"""Server API 路由契约（SPEC-014）。

锁定 15 个 router 的路径、方法与端点名，并对若干只读 GET 路由做
TestClient 级响应字段校验；不联网、不启动真实 Agent。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROUTERS = {
    "chat": "src.server.api.chat",
    "projects": "src.server.api.projects",
    "graph": "src.server.api.graph",
    "task": "src.server.api.task",
    "config": "src.server.api.config",
    "memory": "src.server.api.memory",
    "tools": "src.server.api.tools",
    "system": "src.server.api.system",
    "request": "src.server.api.request",
    "filesystem": "src.server.api.filesystem",
    "evolve": "src.server.api.evolve",
    "terminal": "src.server.api.terminal",
    "paradigms": "src.server.api.paradigms",
    "acp": "src.server.api.acp",
    "webmin": "src.server.api.webmin",
}

# (path, methods, endpoint name)，顺序即 FastAPI 匹配顺序，必须逐字保持。
EXPECTED_ROUTES = {
    "chat": [
        ("/api/sessions", "GET", "get_sessions"),
        ("/api/sessions/{session_id}/rename", "PUT", "rename_session_api"),
        ("/api/sessions/{session_id}/project", "PUT", "move_session_project_api"),
        ("/api/sessions/{session_id}/checkout", "POST", "checkout_session_api"),
        ("/api/sessions/{session_id}", "GET", "get_session_history_api"),
        ("/api/sessions/{session_id}/branches", "GET", "get_session_branches_api"),
        ("/api/sessions/new", "POST", "create_new_session"),
        ("/api/sessions/{session_id}/paradigm", "GET", "get_session_paradigm_api"),
        ("/api/sessions/{session_id}/paradigm", "POST", "switch_session_paradigm_api"),
        ("/api/sessions/{session_id}/branch", "POST", "branch_session_api"),
        ("/api/sessions/{session_id}", "DELETE", "delete_session_api"),
        ("/api/chat", "POST", "chat"),
        ("/api/chat/batch", "POST", "chat_batch"),
        ("/api/sessions/{session_id}/status", "GET", "get_session_status"),
        ("/api/chat/interrupt", "POST", "force_interrupt_api"),
        ("/api/chat/compress-memory", "POST", "compress_memory_api"),
        ("/api/agent/token", "GET", "get_token_status_api"),
        (
            "/api/sessions/{session_id}/branches/{branch_id}",
            "DELETE",
            "delete_session_branch_api",
        ),
    ],
    "projects": [
        ("/api/projects", "GET", "list_projects_api"),
        ("/api/projects", "POST", "create_project_api"),
        ("/api/projects/{project_id}", "PUT", "update_project_api"),
        ("/api/projects/{project_id}", "DELETE", "delete_project_api"),
    ],
    "graph": [
        ("/api/graphs/nodes", "GET", "get_all_nodes_api"),
        ("/api/graphs", "GET", "list_graphs_api"),
        ("/api/graphs/{name}", "GET", "get_graph_api"),
        ("/api/graphs/{name}/schema", "GET", "get_graph_schema_api"),
        ("/api/graphs/{name}", "POST", "save_graph_api"),
    ],
    "task": [
        ("/api/tasks", "GET", "list_tasks_api"),
        ("/api/tasks/run", "POST", "run_task_api"),
        ("/api/tasks/{task_id}/state", "GET", "get_task_state_endpoint"),
        ("/api/tasks/{task_id}/submit", "POST", "submit_instruction_api"),
        ("/api/tasks/{task_id}/push", "POST", "push_to_task"),
        ("/api/tasks/{task_id}/log", "GET", "get_task_log_endpoint"),
        ("/api/tasks/{task_id}/artifact", "GET", "get_task_artifact"),
        ("/api/tasks/{task_id}", "DELETE", "delete_task_endpoint"),
        ("/api/tasks/{task_id}/nodes/{node_id}/reset", "POST", "reset_node_api"),
        ("/api/tasks/{task_id}/stop", "POST", "stop_task_api"),
    ],
    "config": [
        ("/api/config/model", "GET", "api_get_model_config"),
        ("/api/config/model", "PUT", "api_update_model_config"),
        ("/api/config/sensor", "GET", "api_get_sensor_config"),
        ("/api/config/sensor", "PUT", "api_update_sensor_config"),
        ("/api/config/sensor/reload", "POST", "api_reload_sensor_manager"),
        ("/api/config/sensor/runtime", "GET", "api_get_sensor_runtime"),
        ("/api/config/sensor/{name}/stop", "POST", "api_stop_sensor"),
        ("/api/config/sensor/{name}/purge", "POST", "api_purge_sensor"),
        ("/api/config/sensor/{name}/restart", "POST", "api_restart_sensor"),
        ("/api/config/file", "GET", "api_get_file_config"),
        ("/api/config/file", "PUT", "api_update_file_config"),
        ("/api/config/mcp", "GET", "api_get_mcp_config"),
        ("/api/config/mcp", "PUT", "api_update_mcp_config"),
        ("/api/config/mcp/reload", "POST", "api_reload_mcp_runtime"),
        ("/api/config/acp", "GET", "api_get_acp_status"),
        ("/api/config/acp", "PUT", "api_update_acp_config"),
        ("/api/config/acp/redeploy", "POST", "api_redeploy_acp_relay"),
        ("/api/config/acp/reset-token", "POST", "api_reset_acp_token"),
        ("/api/config/deploy", "GET", "api_get_deploy_overview"),
        ("/api/config/deploy/{item}", "POST", "api_deploy_item"),
        ("/api/config/deploy/disk", "GET", "api_get_disk_status"),
        ("/api/config/deploy/disk/compact", "POST", "api_compact_disk"),
        ("/api/config/deploy/disk/prune", "POST", "api_prune_disk"),
        ("/api/config/deploy/disk/rebuild", "POST", "api_rebuild_sandbox"),
        ("/api/config/sandbox-registry", "GET", "api_get_sandbox_registry"),
        ("/api/config/sandbox-registry", "PUT", "api_update_sandbox_registry"),
        ("/api/config/markdown/{filename}", "GET", "api_get_markdown_file"),
        ("/api/config/markdown/{filename}", "PUT", "api_update_markdown_file"),
        ("/api/config/info", "GET", "api_get_info_config"),
        ("/api/config/setup-status", "GET", "api_setup_status"),
        ("/api/config/setup-data-root", "POST", "api_setup_data_root"),
        ("/api/config/change-data-root", "POST", "api_change_data_root"),
        ("/api/config/cron", "GET", "api_get_cron_config"),
        ("/api/config/cron", "PUT", "api_update_cron_config"),
        ("/api/config/meta", "GET", "api_get_config_meta"),
    ],
    "memory": [
        ("/api/memory/events", "GET", "get_events"),
        ("/api/memory/experiences", "GET", "get_experiences"),
        ("/api/memory/graph", "GET", "get_graph"),
        ("/api/memory/search", "GET", "search"),
        ("/api/memory/experiences/{exp_id}", "DELETE", "delete_experience"),
        ("/api/memory/events/{event_id}", "DELETE", "delete_event"),
        ("/api/memory/graph/relation", "DELETE", "delete_relation"),
        ("/api/memory/markdown", "GET", "get_memory_markdown_api"),
        ("/api/memory/markdown", "PUT", "update_memory_markdown_api"),
    ],
    "tools": [
        ("/api/tools/mcp", "GET", "get_mcp_tools_api"),
        ("/api/tools/skills", "GET", "get_skills_api"),
        ("/api/tools/skills/install", "POST", "install_skill_api"),
        ("/api/tools/skills/uninstall", "POST", "uninstall_skill_api"),
        ("/api/tools/skills/install-batch", "POST", "install_skills_batch_api"),
        ("/api/tools/cron", "GET", "get_crons_api"),
        ("/api/tools/mcp/refresh", "POST", "refresh_mcp_api"),
        ("/api/tools/mcp/install", "POST", "install_mcp_api"),
        ("/api/tools/mcp/uninstall", "POST", "uninstall_mcp_api"),
        ("/api/tools/mcp/list", "GET", "list_configured_mcps_api"),
        ("/api/tools/skills/refresh", "POST", "refresh_skills_api"),
        ("/api/tools/cron", "POST", "add_cron_api"),
        ("/api/tools/cron/{identifier}", "DELETE", "delete_cron_api"),
        ("/api/tools/heartbeat", "GET", "get_heartbeat_api"),
        ("/api/tools/heartbeat", "POST", "save_heartbeat_api"),
        ("/api/tools/market/sensors", "GET", "get_sensor_registry_api"),
        ("/api/tools/market/sensors/installed", "GET", "list_installed_sensors_api"),
        ("/api/tools/market/sensors/install", "POST", "install_sensor_api"),
        ("/api/tools/market/sensors/uninstall", "POST", "uninstall_sensor_api"),
        ("/api/tools/market/graphs", "GET", "get_graph_registry_api"),
        ("/api/tools/market/graphs/installed", "GET", "list_installed_graphs_api"),
        ("/api/tools/market/graphs/install", "POST", "install_graph_api"),
        ("/api/tools/market/graphs/uninstall", "POST", "uninstall_graph_api"),
        ("/api/tools/market/ui-plugins", "GET", "get_ui_plugin_registry_api"),
        (
            "/api/tools/market/ui-plugins/installed",
            "GET",
            "list_installed_ui_plugins_api",
        ),
        ("/api/tools/market/ui-plugins/install", "POST", "install_ui_plugin_api"),
        (
            "/api/tools/market/ui-plugins/uninstall",
            "POST",
            "uninstall_ui_plugin_api",
        ),
        ("/api/tools/market/agentloops", "GET", "get_agentloop_registry_api"),
        (
            "/api/tools/market/agentloops/installed",
            "GET",
            "list_installed_agentloops_api",
        ),
        ("/api/tools/market/agentloops/install", "POST", "install_agentloop_api"),
        (
            "/api/tools/market/agentloops/uninstall",
            "POST",
            "uninstall_agentloop_api",
        ),
    ],
    "system": [
        ("/api/system/env/detect", "GET", "detect_environment"),
        ("/api/system/env-status", "GET", "get_environment_status"),
        ("/api/system/env/status", "GET", "get_env_status_simple"),
        ("/api/system/image-status", "GET", "get_image_status"),
        ("/api/system/image/pull", "POST", "pull_image"),
        ("/api/system/env/install", "POST", "trigger_install"),
        ("/api/system/env/install/status", "GET", "get_install_status"),
        ("/api/system/container-engine", "GET", "get_container_engine_info"),
        ("/api/system/agent/upload", "POST", "upload_buffer_file"),
        ("/api/system/agent/stats", "GET", "get_agent_stats"),
    ],
    "request": [
        ("/api/requests", "GET", "list_pending_requests_api"),
        ("/api/requests/{req_id}/resolve", "POST", "resolve_request_api"),
        ("/api/requests/resolved", "GET", "list_resolved_requests_api"),
        ("/api/requests/{req_id}", "DELETE", "delete_request_api"),
    ],
    "filesystem": [
        ("/api/filesystem/list", "GET", "list_directory"),
        ("/api/filesystem/read", "GET", "read_file"),
        ("/api/filesystem/stat", "GET", "stat_file"),
        ("/api/filesystem/write", "POST", "write_file"),
        ("/api/filesystem/history_list", "GET", "get_history_list"),
        ("/api/filesystem/backups", "GET", "api_get_valid_backups"),
        ("/api/filesystem/undo", "POST", "ui_undo_action"),
        ("/api/filesystem/ack", "POST", "ui_ack_action"),
        ("/api/filesystem/ack_all", "POST", "ui_ack_all_action"),
        ("/api/filesystem/diffs", "GET", "api_get_global_diffs"),
        ("/api/filesystem/resolve", "GET", "resolve_path"),
        ("/api/filesystem/preview", "GET", "preview_file"),
    ],
    "evolve": [
        ("/api/evolve/list", "GET", "list_workplaces"),
        ("/api/evolve/init", "POST", "init_sandbox_api"),
        ("/api/evolve/file", "GET", "get_file_api"),
        ("/api/evolve/file", "PUT", "update_file_api"),
        ("/api/evolve/paradigm", "GET", "get_sandbox_paradigm_api"),
        ("/api/evolve/paradigm", "POST", "save_sandbox_paradigm_api"),
        ("/api/evolve/test/run", "POST", "run_evals_api"),
        ("/api/evolve/test/iterations", "GET", "list_iterations_api"),
        ("/api/evolve/test/report", "GET", "get_eval_report_api"),
        ("/api/evolve/test/benchmark", "GET", "get_benchmark_api"),
        ("/api/evolve/diff", "GET", "get_diff_api"),
        ("/api/evolve/handle", "POST", "handle_request_api"),
        ("/api/evolve/rollback", "POST", "rollback_skill_api"),
        ("/api/evolve/workplace/{workplace_id}", "DELETE", "delete_workplace_api"),
    ],
    "terminal": [("/api/terminal/ws", "WEBSOCKET", "terminal_websocket")],
    "paradigms": [
        ("/api/paradigms", "GET", "list_paradigms_api"),
        ("/api/paradigms/{name}", "GET", "get_paradigm_api"),
        ("/api/paradigms/{name}", "POST", "save_paradigm_api"),
        ("/api/paradigms/{name}", "DELETE", "delete_paradigm_api"),
    ],
    "acp": [
        ("/acp/rpc", "POST", "acp_rpc"),
        ("/acp/stream", "GET", "acp_stream"),
        ("/acp/file", "POST", "acp_upload_file"),
        ("/acp/file", "GET", "acp_download_file"),
    ],
    "webmin": [
        ("/api/webmin/manifest", "GET", "api_webmin_manifest"),
        (
            "/api/webmin/plugin-rpc/{plugin_id}/{handler}",
            "POST",
            "api_webmin_plugin_rpc",
        ),
        (
            "/api/webmin/plugin-backend/{plugin_id}/{action}",
            "POST",
            "api_webmin_plugin_backend",
        ),
        ("/api/webmin/config", "GET", "api_webmin_get_config"),
        ("/api/webmin/config", "PUT", "api_webmin_put_config"),
        ("/api/webmin/plugin/{plugin_id}/delete", "POST", "api_webmin_delete_plugin"),
        ("/api/webmin/wallpaper", "POST", "api_webmin_import_wallpaper"),
        ("/api/webmin/wallpaper/{filename}", "GET", "api_webmin_serve_wallpaper"),
        ("/api/webmin/plugin/{plugin_id}/{path:path}", "GET", "api_webmin_plugin"),
        (
            "/api/webmin/plugin-dir/{plugin_id}/{path:path}",
            "GET",
            "api_webmin_plugin_dir",
        ),
    ],
}


def _module(name: str):
    import importlib

    return importlib.import_module(ROUTERS[name])


def _route_key(route) -> tuple[str, str, str]:
    methods = getattr(route, "methods", None)
    method = "WEBSOCKET" if methods is None else ",".join(sorted(methods))
    return route.path, method, route.name


@pytest.mark.parametrize("router_name", sorted(EXPECTED_ROUTES))
def test_router_table_is_frozen(router_name):
    """SPEC-014 AC-1：每个 router 的路径/方法/端点名与重构前逐字一致。"""
    actual = [_route_key(r) for r in _module(router_name).router.routes]
    assert actual == EXPECTED_ROUTES[router_name]


def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_get_tools_mcp_groups_by_server(monkeypatch):
    """SPEC-014 AC-4：/api/tools/mcp 按 server 分组并保留 name/description。"""
    from src.server.api import tools

    schemas = [
        {
            "server": "alpha",
            "function": {"name": "run", "description": "run it", "parameters": {}},
        },
        {"server": "beta", "function": {"name": "peek", "description": ""}},
    ]
    monkeypatch.setattr(tools, "load_cached_schemas", lambda: schemas)

    resp = _client(tools.router).get("/api/tools/mcp")

    assert resp.status_code == 200
    assert resp.json() == {
        "alpha": [{"name": "run", "description": "run it"}],
        "beta": [{"name": "peek", "description": ""}],
    }


def test_get_tools_readonly_lists(monkeypatch, tmp_path):
    """SPEC-014 AC-4：已安装列表与配置列表的 GET 响应字段保持不变。"""
    from src.server.api import tools

    monkeypatch.setattr(tools, "list_crons", lambda: [{"id": "c1"}])
    monkeypatch.setattr(tools, "get_mcp_config", lambda: {"mcpServers": {"a": {}}})
    monkeypatch.setattr(tools, "get_sensor_config", lambda: {"demo": {"enabled": True}})
    monkeypatch.setattr(tools, "SENSOR_EXTENSION_DIR", str(tmp_path))
    (tmp_path / "demo.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        tools,
        "list_graphs",
        lambda: [{"name": "g2"}, {"name": "g1"}, {"name": "g1"}, "invalid"],
    )
    monkeypatch.setattr(tools, "_scan_installed_ui_plugins", lambda *args: ["ui-b"])
    monkeypatch.setattr(tools, "_scan_installed_agentloops", lambda *args: ["loop-b"])

    client = _client(tools.router)

    assert client.get("/api/tools/cron").json() == [{"id": "c1"}]
    assert client.get("/api/tools/mcp/list").json() == ["a"]
    assert client.get("/api/tools/market/sensors/installed").json() == [
        {"name": "demo", "enabled": True, "has_code": True}
    ]
    assert client.get("/api/tools/market/graphs/installed").json() == ["g1", "g2"]
    assert client.get("/api/tools/market/ui-plugins/installed").json() == ["ui-b"]
    assert client.get("/api/tools/market/agentloops/installed").json() == ["loop-b"]


def test_get_tools_heartbeat_contract(monkeypatch):
    """SPEC-014 AC-4：心跳配置响应字段保持不变。"""
    from src.agent import heartbeat
    from src.server.api import tools

    class _Manager:
        def get_config(self):
            return {"interval": 120, "active": True}

        def read_goal(self):
            return "# GOAL"

    monkeypatch.setattr(heartbeat, "get_heartbeat_manager", lambda: _Manager())

    resp = _client(tools.router).get("/api/tools/heartbeat")

    assert resp.status_code == 200
    assert resp.json() == {"interval": 120, "active": True, "goal": "# GOAL"}


def test_config_meta_contract():
    """SPEC-014 AC-4：/api/config/meta 的关键字段集合不变。"""
    from src.server.api import config

    data = _client(config.router).get("/api/config/meta").json()

    assert set(data) == {
        "PURRCAT_DIR",
        "DATA_ROOT",
        "BASE_DIR",
        "settings_path",
        "cron_path",
    }


def test_memory_search_empty_query_contract():
    """SPEC-014 AC-4：空查询直接返回空结果，不触碰记忆引擎。"""
    from src.server.api import memory

    assert _client(memory.router).get("/api/memory/search?q=").json() == {"result": ""}


def test_graph_list_contract(monkeypatch):
    """SPEC-014 AC-4：/api/graphs 原样透传图列表。"""
    from src.server.api import graph

    monkeypatch.setattr(graph, "list_graphs", lambda: [{"name": "flow"}])

    assert _client(graph.router).get("/api/graphs").json() == [{"name": "flow"}]


def test_requests_empty_list_contract(monkeypatch):
    """SPEC-014 AC-4：待处理请求为空时返回空数组。"""
    from src.server.api import request

    monkeypatch.setattr(request, "get_pending_requests", lambda: [])
    monkeypatch.setattr(request, "kick_pending_skill_tests", lambda: None)
    monkeypatch.setattr(request, "kick_pending_sensor_tests", lambda: None)

    assert _client(request.router).get("/api/requests").json() == []
