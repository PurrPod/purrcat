"""工具市场注册表、校验与 payload 的 L0 用例（SPEC-014 AC-2）。"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.server.api import (
    tools_registry,
    tools_serialization,
    tools_validation,
)

# ── 注册表数据抽取 ──


def test_tools_router_keeps_expected_endpoint_count_and_names():
    """SPEC-014 AC-2：工具市场路由数量与端点名保持不变。"""
    from src.server.api import tools

    routes = tools.router.routes
    assert len(routes) == 31
    names = {r.name for r in routes}
    assert {
        "get_mcp_tools_api",
        "install_skills_batch_api",
        "install_mcp_api",
        "get_sensor_registry_api",
        "install_sensor_api",
        "get_graph_registry_api",
        "install_graph_api",
        "get_ui_plugin_registry_api",
        "install_ui_plugin_api",
        "get_agentloop_registry_api",
        "install_agentloop_api",
    } <= names


def test_group_mcp_tools_keeps_only_name_and_description():
    """SPEC-014 AC-2：MCP 工具分组只保留 name/description 两个 schema 字段。"""
    schemas = [
        {
            "server": "alpha",
            "function": {
                "name": "run",
                "description": "run it",
                "parameters": {"type": "object"},
            },
        },
        {"server": "alpha", "function": {"name": "peek"}},
        {"function": {"name": "orphan", "description": "no server"}},
    ]

    grouped = tools_serialization.group_mcp_tools(schemas)

    assert grouped == {
        "alpha": [
            {"name": "run", "description": "run it"},
            {"name": "peek", "description": ""},
        ],
        "unknown": [{"name": "orphan", "description": "no server"}],
    }


def test_extract_registry_graphs_accepts_list_or_wrapped_dict():
    """SPEC-014 AC-2：graphs 注册表兼容裸数组与 {graphs:[...]} 两种形态。"""
    graphs = [{"name": "g"}]

    assert tools_registry.extract_registry_graphs(graphs) == graphs
    assert tools_registry.extract_registry_graphs({"graphs": graphs}) == graphs
    assert tools_registry.extract_registry_graphs({"items": graphs}) == graphs
    assert tools_registry.extract_registry_graphs({"graphs": "bad"}) == []


def test_extract_registry_items_prefers_explicit_key():
    """SPEC-014 AC-2：显式 key 优先于通用的 items/data 兜底。"""
    preferred = [{"name": "plugin"}]

    assert (
        tools_registry.extract_registry_items(
            {"plugins": preferred, "items": [{"name": "other"}]}, "plugins"
        )
        == preferred
    )
    assert tools_registry.extract_registry_items({"data": preferred}) == preferred


def test_normalize_dependency_list_filters_unknown_types_and_empty_ids():
    """SPEC-014 AC-2：依赖类型必须在白名单内且 id 非空。"""
    raw = [
        {"type": "skill", "id": " demo "},
        {"type": "unknown", "id": "x"},
        {"type": "mcp", "id": " "},
        "not-a-dict",
    ]

    assert tools_registry.normalize_dependency_list(raw) == [
        {"type": "skill", "id": "demo"}
    ]


@pytest.mark.parametrize(
    ("branch", "default", "expected"),
    [
        ("dev", "main", ["dev"]),
        ("", "master", ["master", "main"]),
        ("", "", ["main", "master"]),
    ],
)
def test_default_branch_candidates(branch, default, expected):
    """SPEC-014 AC-2：裸仓库分支探测顺序固定。"""
    assert tools_registry.default_branch_candidates(branch, default) == expected


# ── 已安装扫描 ──


def test_installed_sensor_entries_reports_enabled_and_code_presence(tmp_path):
    """SPEC-014 AC-2：已安装 Sensor 列表只含 name/enabled/has_code。"""
    (tmp_path / "s1.py").write_text("", encoding="utf-8")
    config = {"s1": {"enabled": True}, "s2": {"enabled": False}, "s3": "bad"}

    assert tools_registry.installed_sensor_entries(config, str(tmp_path)) == [
        {"name": "s1", "enabled": True, "has_code": True},
        {"name": "s2", "enabled": False, "has_code": False},
        {"name": "s3", "enabled": False, "has_code": False},
    ]


def test_scan_installed_ui_plugins_requires_plugin_json(tmp_path):
    """SPEC-014 AC-2：只列出含 plugin.json 的目录，跳过 .trash。"""
    for name in ("alpha", "beta", "ghost", "alpha.trash"):
        (tmp_path / name).mkdir()
    (tmp_path / "alpha" / "plugin.json").write_text("{}", encoding="utf-8")
    (tmp_path / "alpha.trash" / "plugin.json").write_text("{}", encoding="utf-8")

    assert tools_registry.scan_installed_ui_plugins((str(tmp_path),)) == ["alpha"]


def test_scan_installed_agentloops_strips_yaml_suffix(tmp_path):
    """SPEC-014 AC-2：AgentLoop 列表按文件名去掉 yaml 后缀。"""
    (tmp_path / "a.yaml").write_text("", encoding="utf-8")
    (tmp_path / "b.yml").write_text("", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("", encoding="utf-8")

    assert tools_registry.scan_installed_agentloops(str(tmp_path)) == ["a", "b"]
    assert tools_registry.scan_installed_agentloops(str(tmp_path / "missing")) == []


def test_installed_graph_names_dedupes_and_sorts():
    """SPEC-014 AC-2：Graph 已安装列表去重排序并忽略非法条目。"""
    entries = [{"name": "g2"}, {"name": "g1"}, {"name": "g1"}, "bad", {"name": ""}]

    assert tools_registry.installed_graph_names(entries) == ["g1", "g2"]


# ── 名称与 URL 校验 ──


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/owner/repo", ("owner", "repo", "", "")),
        ("https://github.com/owner/repo.git", ("owner", "repo", "", "")),
        (
            "https://github.com/owner/repo/tree/dev/skills/demo",
            ("owner", "repo", "dev", "skills/demo"),
        ),
        (
            "https://github.com/owner/repo/blob/main/skills/demo/SKILL.md",
            ("owner", "repo", "main", "skills/demo"),
        ),
    ],
)
def test_parse_skill_github_url(url, expected):
    """SPEC-014 AC-2：三类 GitHub 链接解析结果固定。"""
    assert tools_validation.parse_skill_github_url(url) == expected


def test_parse_skill_github_url_rejects_other_hosts():
    """SPEC-014 AC-2：非 GitHub 链接返回 400 且保留原文案前缀。"""
    with pytest.raises(HTTPException) as exc:
        tools_validation.parse_skill_github_url("https://gitlab.com/owner/repo")

    assert exc.value.status_code == 400
    assert exc.value.detail.startswith("URL格式错误！")


def test_require_plain_name_rejects_traversal():
    """SPEC-014 AC-2：插件/AgentLoop 名称拒绝路径分隔符与上跳。"""
    assert tools_validation.require_plain_name(" demo ", "bad") == "demo"
    for bad in ("", "a/b", "a\\b", "..", "x..y"):
        with pytest.raises(HTTPException):
            tools_validation.require_plain_name(bad, "bad")


def test_safe_install_name_takes_basename():
    """SPEC-014 AC-2：安装目录名取最后一段，空值与点目录分别报错。"""
    assert tools_validation.safe_install_name("a/b", "empty", "invalid") == "b"
    with pytest.raises(HTTPException) as empty:
        tools_validation.safe_install_name("  ", "empty", "invalid")
    assert empty.value.detail == "empty"
    with pytest.raises(HTTPException) as invalid:
        tools_validation.safe_install_name("..", "empty", "invalid")
    assert invalid.value.detail == "invalid"


def test_safe_path_component_is_basename_only():
    """SPEC-014 AC-2：依赖安装名只取最后一段，空值与 .. 统一报同一错误。"""
    assert tools_validation.safe_path_component("a/b", "invalid") == "b"
    for bad in ("", ".."):
        with pytest.raises(HTTPException) as exc:
            tools_validation.safe_path_component(bad, "invalid")
        assert exc.value.detail == "invalid"


def test_validate_registry_files_rejects_parent_traversal():
    """SPEC-014 AC-2：注册表文件清单拒绝绝对路径与 .. 片段。"""
    assert tools_validation.validate_registry_files(["plugin.json", "js/app.js"]) == [
        "plugin.json",
        "js/app.js",
    ]
    for bad in ("/etc/passwd", "../x", "a/../../b", "a\\..\\b"):
        with pytest.raises(HTTPException) as exc:
            tools_validation.validate_registry_files([bad])
        assert exc.value.status_code == 502


def test_parse_mcp_config_json_validates_top_level_key():
    """SPEC-014 AC-2：MCP 配置 JSON 语法与 mcpServers 顶层键校验。"""
    assert tools_validation.parse_mcp_config_json('{"mcpServers": {"a": {}}}') == {
        "mcpServers": {"a": {}}
    }
    with pytest.raises(HTTPException) as syntax:
        tools_validation.parse_mcp_config_json("{")
    assert syntax.value.detail == "输入的不是合法的 JSON 格式，请检查语法"
    with pytest.raises(HTTPException) as key:
        tools_validation.parse_mcp_config_json('{"servers": {}}')
    assert key.value.detail == "JSON 格式必须以 'mcpServers' 为顶层键"


# ── 响应组装 ──


def test_merge_sensor_entry_keeps_user_env_and_drops_capabilities():
    """SPEC-014 AC-2：重装 Sensor 时保留用户已填 env，并丢弃废弃 capabilities。"""
    sensor = {
        "name": "demo",
        "enabled": True,
        "env": {"KEEP": "new-default", "ADD": "value"},
        "description": "desc",
        "capabilities": ["old"],
    }
    existing = {"enabled": False, "env": {"KEEP": "user-value", "EXTRA": "x"}}

    merged = tools_serialization.merge_sensor_entry(sensor, existing)

    assert merged == {
        "enabled": False,
        "env": {"KEEP": "user-value", "ADD": "value", "EXTRA": "x"},
        "description": "desc",
    }


def test_heartbeat_payload_clamps_to_minimum():
    """SPEC-014 AC-2：心跳间隔不低于宿主最小间隔。"""
    assert tools_serialization.heartbeat_payload(10, True, 60) == {
        "interval": 60,
        "active": True,
    }
    assert tools_serialization.heartbeat_payload(120, False, 60) == {
        "interval": 120,
        "active": False,
    }


def test_skill_batch_response_marks_partial_on_failures():
    """SPEC-014 AC-2：批量安装结果状态与消息随失败数变化。"""
    ok = tools_serialization.skill_batch_response(["a", "b"], [])
    assert ok == {
        "status": "success",
        "installed": ["a", "b"],
        "failed": [],
        "message": "批量安装完成：成功 2 个",
    }

    partial = tools_serialization.skill_batch_response(["a"], [{"path": "x"}])
    assert partial["status"] == "partial"
    assert partial["message"] == "批量安装完成：成功 1 个，失败 1 个"


def test_registry_payloads_expose_version_repository_and_items():
    """SPEC-014 AC-2：四类市场响应都包含 version/repository + 条目 key。"""
    assert tools_serialization.sensor_registry_payload(
        {"version": "1", "repository": "r", "sensors": [{"name": "s"}]}
    ) == {"version": "1", "repository": "r", "sensors": [{"name": "s"}]}

    graph = tools_serialization.graph_registry_payload(
        {"version": "2", "graphs": [{"name": "g"}]}
    )
    assert graph == {"version": "2", "repository": None, "graphs": [{"name": "g"}]}

    plugin = tools_serialization.ui_plugin_registry_payload([{"name": "p"}])
    assert plugin == {"version": None, "repository": None, "plugins": [{"name": "p"}]}

    loop = tools_serialization.agentloop_registry_payload(
        {"agentloops": [{"name": "a"}]}
    )
    assert loop == {"version": None, "repository": None, "agentloops": [{"name": "a"}]}
