"""请求解析 / 响应组装 / 路径校验等纯函数的 L0 用例（SPEC-014 AC-3）。"""

from __future__ import annotations

import json
import os

import pytest
from fastapi import HTTPException

from src.server.api import (
    chat,
    common,
    config,
    filesystem,
    projects,
    system,
    task,
    webmin_manifest,
)

# ── common：JSON / 路径 / 错误映射 ──


def test_save_and_read_json_roundtrip(tmp_path):
    """SPEC-014 AC-3：JSON 落盘与读取保持内容与 UTF-8 文本。"""
    path = tmp_path / "nested" / "config.json"
    data = {"name": "中文", "values": [1, 2]}

    assert common.save_json_file(str(path), data) is True
    assert common.read_json_file(str(path)) == data


def test_read_json_file_returns_default_on_bad_content(tmp_path):
    """SPEC-014 AC-3：文件缺失或 JSON 损坏时返回默认值。"""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    assert common.read_json_file(str(tmp_path / "missing.json"), {"a": 1}) == {"a": 1}
    assert common.read_json_file(str(bad), []) == []


def test_save_json_file_reports_failure_without_raising(tmp_path):
    """SPEC-014 AC-3：写入失败只返回 False，不把异常抛给路由层。"""
    blocker = tmp_path / "blocked"
    blocker.write_text("", encoding="utf-8")

    assert common.save_json_file(str(blocker / "x.json"), {}) is False


@pytest.mark.parametrize(
    ("name", "unsafe"),
    [
        ("demo", False),
        ("", True),
        ("a/b", True),
        ("a\\b", True),
        ("a..b", True),
    ],
)
def test_is_unsafe_name(name, unsafe):
    """SPEC-014 AC-3：目录名白名单拒绝空串、分隔符与上跳片段。"""
    assert common.is_unsafe_name(name) is unsafe


def test_safe_basename_handles_windows_separators():
    """SPEC-014 AC-3：反斜杠路径也能取到最后一段。"""
    assert common.safe_basename("a\\b\\demo") == "demo"
    assert common.safe_basename(None) == ""


def test_is_within_root_and_resolve_within(tmp_path):
    """SPEC-014 AC-3：路径越界判断与相对路径解析。"""
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "sub" / "file.txt").write_text("x", encoding="utf-8")

    assert common.is_within_root(str(root), str(root / "sub" / "file.txt")) is True
    assert common.is_within_root(str(root), str(tmp_path / "outside")) is False

    resolved = common.resolve_within(str(root), "sub/file.txt")
    assert resolved == os.path.abspath(root / "sub" / "file.txt")
    assert common.resolve_within(str(root), "../outside") is None
    assert common.resolve_within(str(root), "/sub") == os.path.abspath(root / "sub")


def test_unexpected_error_maps_prefix_and_status():
    """SPEC-014 AC-3：未预期异常映射为带前缀的 HTTPException。"""
    err = common.unexpected_error("刷新失败: ", ValueError("boom"), status_code=502)

    assert err.status_code == 502
    assert err.detail == "刷新失败: boom"


# ── webmin_manifest：插件清单归一化 ──


@pytest.mark.parametrize(
    ("plugin", "area", "behavior", "slot_id", "slot_type"),
    [
        ({"id": "rail"}, "rail", "fixed", "rail", "fixed"),
        ({"id": "p1", "slot": "panel"}, "panel", "panel", "panel", "panel"),
        (
            {"id": "pet1", "slot": {"area": "pet"}},
            "pet",
            "float",
            "float:pet1",
            "float",
        ),
        (
            {"id": "pop1", "slot": {"area": "popup"}},
            "popup",
            "modal",
            "modal:pop1",
            "modal",
        ),
    ],
)
def test_plugin_area_slot_id_and_behavior(plugin, area, behavior, slot_id, slot_type):
    """SPEC-014 AC-3：区域是唯一维度，slot id 与行为类别由区域推导。"""
    assert webmin_manifest.plugin_area(plugin) == area
    assert webmin_manifest.area_behavior(area) == behavior
    assert webmin_manifest.slot_id(plugin) == slot_id
    assert webmin_manifest.slot_def(plugin)["type"] == slot_type


def test_slot_def_keeps_float_size_and_center():
    """SPEC-014 AC-3：浮窗可选尺寸与居中声明原样保留。"""
    plugin = {
        "id": "pet1",
        "slot": {"area": "pet", "size": {"w": 300, "h": 360}, "center": True},
    }

    assert webmin_manifest.slot_def(plugin) == {
        "type": "float",
        "area": "pet",
        "size": {"w": 300, "h": 360},
        "center": True,
    }


def test_normalize_shared_catalog_filters_incomplete_entries():
    """SPEC-014 AC-3：共享运行时清单只保留 version+base 完整的条目。"""
    raw = {
        "marked": {"version": "1.0", "base": "/shared/marked/1.0"},
        "bad": {"version": "", "base": "/x"},
        "also-bad": "not-a-dict",
    }

    assert webmin_manifest.normalize_shared_catalog(raw) == {
        "marked": {"version": "1.0", "base": "/shared/marked/1.0"}
    }
    assert webmin_manifest.normalize_shared_catalog([]) == {}


def test_normalize_requires_reports_resolution_state():
    """SPEC-014 AC-3：requires 解析共享运行时版本、base 与 ok 标记。"""
    catalog = {"a": {"version": "1.0", "base": "/shared/a/1.0"}}
    raw = ["a", {"name": "b", "range": "^2"}, {"name": ""}, 1]

    assert webmin_manifest.normalize_requires(raw, catalog) == [
        {
            "name": "a",
            "range": "",
            "version": "1.0",
            "base": "/shared/a/1.0",
            "ok": True,
        },
        {"name": "b", "range": "^2", "version": "", "base": "", "ok": False},
    ]


def test_sanitize_rail_clamps_and_defaults():
    """SPEC-014 AC-3：图标栏 stage 只在 0/1，opacity 夹紧到 [0,1]。"""
    assert webmin_manifest.sanitize_rail(
        {"stage": "2", "opacity": "1.5", "hidden": []}
    ) == {"stage": 0, "opacity": 1.0, "hidden": {}}
    assert webmin_manifest.sanitize_rail(
        {"stage": 1, "opacity": "bad", "hidden": {"rail": 1}}
    ) == {"stage": 1, "opacity": 1.0, "hidden": {"rail": 1}}


def test_normalize_active_filters_empty_values():
    """SPEC-014 AC-3：单例槽选中项只保留非空字符串/整数。"""
    assert webmin_manifest.normalize_active(
        {"a": "x", "b": 0, "c": 1, "d": None, "e": True, "f": ""}
    ) == {"a": "x", "b": "0", "c": "1", "e": "True"}


def test_plugin_origin_and_builtin_root(tmp_path):
    """SPEC-014 AC-3：插件实际所在根与内置根判断。"""
    user_root = tmp_path / "user"
    builtin_root = tmp_path / "builtin"
    plugin_dir = builtin_root / "demo"
    plugin_dir.mkdir(parents=True)
    root_to_dir = {"user": str(user_root), "builtin": str(builtin_root)}

    assert webmin_manifest.plugin_origin(str(plugin_dir), root_to_dir) == "builtin"
    assert webmin_manifest.is_builtin(str(plugin_dir), str(builtin_root)) is True
    assert webmin_manifest.plugin_origin(str(tmp_path / "elsewhere"), root_to_dir) == ""


def test_sort_plugins_orders_by_slot_then_name():
    """SPEC-014 AC-3：插件按 slot 顺序排列，浮窗/弹窗排在已锚定区域之后。"""
    plugins = [
        {"id": "pop", "name": "m", "slot": {"area": "popup"}},
        {"id": "panel", "name": "p", "slot": "panel"},
        {"id": "side", "name": "b", "slot": "sidebar"},
        {"id": "side2", "name": "a", "slot": "sidebar"},
    ]

    assert [p["id"] for p in webmin_manifest.sort_plugins(plugins)] == [
        "side2",
        "side",
        "panel",
        "pop",
    ]


def test_build_manifest_entry_fills_derived_fields(tmp_path):
    """SPEC-014 AC-3：manifest 条目补齐 root/origin/rootOk/slot/dependency。"""
    builtin_root = tmp_path / "builtin"
    plugin_dir = builtin_root / "p1"
    plugin_dir.mkdir(parents=True)
    root_to_dir = {"builtin": str(builtin_root), "user": str(tmp_path / "user")}
    raw = {
        "id": "p1",
        "name": "P1",
        "dir": str(plugin_dir),
        "root": "user",
        "slot": {"area": "pet", "size": {"w": 1}},
        "dependency": [{"type": "skill", "id": "s"}],
        "requires": ["marked"],
    }

    entry = webmin_manifest.build_manifest_entry(
        raw,
        {"hello": "world"},
        catalog={"marked": {"version": "1", "base": "/m"}},
        dep_types=("skill",),
        builtin=True,
        backend={"status": "stopped"},
        origin="user",
        root_to_dir=root_to_dir,
    )

    assert entry["config"] == {"hello": "world"}
    assert entry["builtin"] is True
    assert entry["root"] == "user"
    assert entry["rootOk"] is True
    assert entry["slot"] == "float:p1"
    assert entry["slotDef"]["type"] == "float"
    assert entry["dependency"] == [{"type": "skill", "id": "s"}]
    assert entry["requires"][0]["ok"] is True
    assert entry["configSchema"] == []


# ── chat：会话列表与状态 payload ──


def test_build_session_list_defaults_and_sorts():
    """SPEC-014 AC-3：会话列表字段默认值固定并按 updated_at 倒序。"""
    sessions = {
        "s1": {"alias": "one", "updated_at": "2026-01-01", "messages_count": 2},
        "s2": {"updated_at": "2026-02-01", "project_id": "proj"},
    }

    assert chat.build_session_list(sessions) == [
        {
            "id": "s2",
            "alias": "s2",
            "messages_count": 0,
            "updated_at": "2026-02-01",
            "project_id": "proj",
        },
        {
            "id": "s1",
            "alias": "one",
            "messages_count": 2,
            "updated_at": "2026-01-01",
            "project_id": "",
        },
    ]


def test_build_session_status_for_current_and_other_sessions():
    """SPEC-014 AC-3：状态裁剪只对当前会话透出思考与阶段。"""
    thinking = {
        "session_id": "s1",
        "state": "processing",
        "live_phase": "tools",
        "live_reasoning": "why",
        "compressing": True,
    }

    assert chat.build_session_status(thinking, "s1") == {
        "is_thinking": True,
        "state": "processing",
        "compressing": True,
        "live_reasoning": "why",
        "phase": "tools",
    }
    assert chat.build_session_status(thinking, "s2") == {
        "is_thinking": False,
        "state": "idle",
        "compressing": True,
        "live_reasoning": "",
        "phase": "idle",
    }
    assert (
        chat.build_session_status({"session_id": "s1", "state": "aborting"}, "s1")[
            "phase"
        ]
        == "aborting"
    )
    assert (
        chat.build_session_status(
            {"session_id": "s1", "state": "idle", "live_reasoning": "stale"}, "s1"
        )["live_reasoning"]
        == ""
    )


def test_apply_buffer_to_events_replaces_content_and_keeps_extra_keys():
    """SPEC-014 AC-3：批量事件逐条替换 content，其余字段原样保留。"""
    calls = []

    def buffer_fn(content, event_type):
        calls.append((content, event_type))
        return f"[{event_type}]{content}"

    events = [
        {"type": "user", "content": "hi", "id": 1},
        {"content": "no-type"},
    ]

    assert chat.apply_buffer_to_events(events, buffer_fn) == [
        {"type": "user", "content": "[user]hi", "id": 1},
        {"content": "[user]no-type"},
    ]
    assert calls == [("hi", "user"), ("no-type", "user")]


# ── projects / system / task / filesystem 纯逻辑 ──


def test_count_sessions_and_filter_project_ids():
    """SPEC-014 AC-3：项目会话计数与筛选结果一致。"""
    sessions = {
        "s1": {"project_id": "p1"},
        "s2": {"project_id": "p1"},
        "s3": {"project_id": "p2"},
        "s4": {},
        "s5": None,
    }

    assert projects.count_sessions_by_project(sessions) == {"p1": 2, "p2": 1}
    assert projects.session_ids_for_project(sessions, "p1") == ["s1", "s2"]


def test_summarize_usage_days_marks_today_and_heatmap():
    """SPEC-014 AC-3：用量汇总按日期生成热力图并回填今日三项指标。"""
    summaries = {
        "2026-01-01": [
            {"calls": 1, "total_tokens": 10, "cached_tokens": 2},
            {"calls": 2, "total_tokens": 20, "cached_tokens": 3},
        ],
        "2026-01-02": [{"calls": 4, "total_tokens": 40, "cached_tokens": 5}],
    }

    assert system.summarize_usage_days(summaries, "2026-01-02") == {
        "today": {"calls": 4, "total_tokens": 40, "cached_tokens": 5},
        "heatmap": {"2026-01-01": 3, "2026-01-02": 4},
    }


def test_group_logs_by_node_defaults_to_system():
    """SPEC-014 AC-3：任务日志按 node_id 分组，缺省归入 system。"""
    logs = [
        {"node_id": "n1", "msg": "a"},
        {"node_id": "n1", "msg": "b"},
        {"msg": "c"},
        {"node_id": "", "msg": "d"},
    ]

    assert task.group_logs_by_node(logs) == {
        "n1": [{"node_id": "n1", "msg": "a"}, {"node_id": "n1", "msg": "b"}],
        "system": [{"msg": "c"}, {"node_id": "", "msg": "d"}],
    }


def test_locate_checkpoint_dir_prefers_memory(tmp_path):
    """SPEC-014 AC-3：checkpoint 定位内存优先，磁盘按包含关系兜底。"""
    base = tmp_path / "checkpoints"
    (base / "nice_task-1").mkdir(parents=True)

    class _Task:
        checkpoint_dir = "memory-dir"

    assert task.locate_checkpoint_dir("t1", {"t1": _Task()}, str(base)) == "memory-dir"
    assert task.locate_checkpoint_dir("task-1", {}, str(base)) == str(
        base / "nice_task-1"
    )
    assert task.locate_checkpoint_dir("missing", {}, str(base)) is None


def test_agent_vm_fallback_relative_strips_drive_and_prefix():
    """SPEC-014 AC-3：漏写 agent_vm 层时生成回退路径，已含该层则跳过。"""
    assert filesystem.agent_vm_fallback_relative("D:/work/a.txt") == (
        "/agent_vm/work/a.txt"
    )
    assert filesystem.agent_vm_fallback_relative("/work/a.txt") == (
        "/agent_vm/work/a.txt"
    )
    assert filesystem.agent_vm_fallback_relative("C:\\work\\a.txt") == (
        "/agent_vm/work/a.txt"
    )
    assert filesystem.agent_vm_fallback_relative("/agent_vm/a.txt") is None


def test_parse_history_filename_handles_valid_and_garbage_names():
    """SPEC-014 AC-3：历史备份文件名解析，非法条目返回 None。"""
    expected_path = "/" + "a%b".replace("%", os.sep)
    assert filesystem.parse_history_filename("a%b@backup1") == {
        "id": "a%b@backup1",
        "path": expected_path,
        "backup_id": "backup1",
        "time": "",
    }
    assert filesystem.parse_history_filename("a%b@backup1.empty") is None
    assert filesystem.parse_history_filename("no-at-sign") is None


# ── config：数据根与 ACP 端口校验 ──


def test_validate_data_root_accepts_absolute_and_rejects_relative(tmp_path):
    """SPEC-014 AC-3：数据根必须是绝对路径且不能是磁盘根。"""
    assert config._validate_data_root(str(tmp_path)) == os.path.normpath(str(tmp_path))

    for bad in ("", "   ", "relative/path"):
        with pytest.raises(HTTPException) as exc:
            config._validate_data_root(bad)
        assert exc.value.status_code == 400

    if os.name == "nt":
        with pytest.raises(HTTPException) as exc:
            config._validate_data_root("D:\\")
        assert exc.value.status_code == 400


def test_validate_acp_port_accepts_only_valid_int_range():
    """SPEC-014 AC-3：ACP 端口只接受 1-65535 的整数。"""
    assert config._validate_acp_port(8000) == 8000
    for bad in (0, 65536, -1, "8000", None):
        with pytest.raises(HTTPException) as exc:
            config._validate_acp_port(bad)
        assert exc.value.status_code == 400
        assert exc.value.detail == "端口必须是 1-65536 的整数"


def test_common_read_json_file_is_json_compatible(tmp_path):
    """SPEC-014 AC-3：读取结果与标准库 json 一致（含嵌套结构）。"""
    path = tmp_path / "x.json"
    data = {"a": [1, {"b": None}]}
    path.write_text(json.dumps(data), encoding="utf-8")

    assert common.read_json_file(str(path)) == data
