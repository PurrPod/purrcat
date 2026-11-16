# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Graph（任务图）校验器 —— 格式 / 功能 / 关键词汇 三重校验。

本文件同时承担两个角色（单一事实来源，逻辑不会漂移）：
1. 宿主侧权威校验：合并网关调用 ``validate_graph_folder``，未全绿禁止合并；
2. 沙盒自测脚本：工厂会把本文件逐字拷贝为沙盒里的 ``evals/validate.py``，
   直接 ``uv run evals/validate.py`` 即可离线自查。

因此本文件禁止依赖任何包内相对导入，只用标准库。
"""

import json
import os
import sys

# ==========================================
# 专有词汇表（关键词汇校验的白名单）
# ==========================================

# 合法节点类型（对应 src/harness/node/extensions/<type>/<type>.json）
NODE_TYPES = {
    "task_input",
    "task_output",
    "string",
    "template_renderer",
    "message_card_builder",
    "appender",
    "json_builder",
    "json_extractor",
    "env_loader",
    "skill_info",
    "mcp_info",
    "agent_loop",
    "human_intervention",
    "command",
    "file_reader",
    "file_writer",
}

# 已废弃节点类型（信封协议重构中移除）
DEPRECATED_TYPES = {
    "image_generator",
    "preview",
    "text_file_reader",
    "if_else_router",
    "switch_router",
    "python_runner",
}

# 各类型的静态端口（dynamic 端口由 config 动态生成，此处不含）
STATIC_INPUTS = {
    "agent_loop": ["messages", "agentloop"],
    "appender": ["base_list", "append_list"],
    "command": ["command", "os", "trigger"],
    "env_loader": [],
    "file_reader": ["trigger", "source"],
    "file_writer": ["trigger", "content", "filename"],
    "human_intervention": ["trigger", "context_data", "prompt"],
    "json_builder": ["trigger"],
    "json_extractor": ["data"],
    "mcp_info": ["trigger"],
    "message_card_builder": ["content", "trigger"],
    "skill_info": ["trigger"],
    "string": ["trigger"],
    "task_input": [],
    "task_output": [],
    "template_renderer": ["template", "trigger"],
}
STATIC_OUTPUTS = {
    "agent_loop": ["messages", "summary"],
    "appender": ["merged_list"],
    "command": ["stdout", "stderr", "exit_code", "skipped"],
    "env_loader": [],
    "file_reader": ["content", "file"],
    "file_writer": ["file"],
    "human_intervention": ["human_reply", "context_data"],
    "json_builder": ["json_string"],
    "json_extractor": [],
    "mcp_info": ["mcp_kit_string"],
    "message_card_builder": ["message_list"],
    "skill_info": ["skill_kit_string"],
    "string": ["text", "number", "boolean", "json"],
    "task_input": [],
    "task_output": [],
    "template_renderer": ["rendered_text"],
}
# 具备动态端口的类型（dynamic_inputs / dynamic_outputs / dynamic_vars）
DYNAMIC_INPUT_TYPES = {"task_output", "json_builder", "template_renderer"}
DYNAMIC_OUTPUT_TYPES = {"task_input", "env_loader", "json_extractor"}

REQUIRED_TOP = ["name", "description", "description-zh"]


def _check(checks, title, ok, level, detail=""):
    checks.append({"title": title, "ok": bool(ok), "level": level, "detail": detail})
    return bool(ok)


def validate_graph_doc(doc, expected_name=None):
    """校验一个已解析的 graph.json dict，返回结构化报告。"""
    checks = []

    if not isinstance(doc, dict):
        _check(checks, "graph.json 顶层为对象", False, "error", "顶层必须是 JSON 对象")
        return _report(checks)
    _check(checks, "graph.json 顶层为对象", True, "error")

    # ---- 格式校验（每条断言都登记，通过项 ok=True，便于全量查看） ----
    for key in REQUIRED_TOP:
        ok = bool(doc.get(key))
        _check(
            checks,
            f"必填字段 `{key}` 非空",
            ok,
            "error",
            "" if ok else f"缺少或为空：`{key}`",
        )

    name = doc.get("name")
    if expected_name and name:
        ok = str(name) == expected_name
        _check(
            checks,
            "name 与文件夹名一致",
            ok,
            "error",
            ""
            if ok
            else f"name={name!r}，文件夹={expected_name!r}（CI 与市场安装都要求两者一致）",
        )

    ok = "version" in doc
    _check(checks, "声明 version", ok, "warn", "" if ok else '建议加 "version": "2.0"')

    nodes = doc.get("nodes")
    edges = doc.get("edges")
    ok = isinstance(nodes, list)
    _check(checks, "nodes 为数组", ok, "error", "" if ok else "nodes 必须是数组")
    if not ok:
        return _report(checks)
    ok = isinstance(edges, list)
    _check(checks, "edges 为数组", ok, "error", "" if ok else "edges 必须是数组")
    if not ok:
        return _report(checks)

    # ---- 关键词汇 + 功能校验：节点（扫描后汇总为每条断言的通过情况） ----
    ids = {}
    has_task_input = False
    has_task_output = False
    global_vars = set()
    bad_obj = []  # 非对象的 nodes 项
    bad_id = []  # 缺 id 或 id 重复
    bad_name = []  # 缺节点显示名
    bad_deprecated = []  # 使用了已废弃类型
    bad_type = []  # 类型不在白名单
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            bad_obj.append(f"nodes[{i}]")
            continue
        nid = node.get("id")
        ntype = node.get("type")
        if not nid:
            bad_id.append(f"nodes[{i}]（缺 id）")
        elif nid in ids:
            bad_id.append(f"`{nid}`（与 nodes[{ids[nid]}] 重复）")
        else:
            ids[nid] = i
        if not node.get("name"):
            bad_name.append(f"`{nid}`")

        if ntype in DEPRECATED_TYPES:
            bad_deprecated.append(f"`{nid}`（{ntype}）")
        elif ntype not in NODE_TYPES:
            bad_type.append(f"`{nid}`（{ntype}）")

        if ntype == "task_input":
            has_task_input = True
            for gv in node.get("config", {}).get("global_vars", []) or []:
                if isinstance(gv, dict) and gv.get("name"):
                    global_vars.add(gv["name"])
        if ntype == "task_output":
            has_task_output = True

    _check(
        checks,
        "所有 nodes 项均为对象",
        not bad_obj,
        "error",
        f"非对象项：{bad_obj}" if bad_obj else "",
    )
    _check(
        checks,
        "节点 id 唯一且非空",
        not bad_id,
        "error",
        f"异常节点：{bad_id}" if bad_id else "",
    )
    _check(
        checks,
        "所有节点均含显示名 name",
        not bad_name,
        "warn",
        f"缺 name 的节点：{bad_name}" if bad_name else "",
    )
    _check(
        checks,
        "节点类型未使用已废弃类型",
        not bad_deprecated,
        "error",
        f"已废弃：{bad_deprecated}；下线清单：{sorted(DEPRECATED_TYPES)}"
        if bad_deprecated
        else "",
    )
    _check(
        checks,
        "节点类型均属于白名单",
        not bad_type,
        "error",
        f"未知类型：{bad_type}；合法值：{sorted(NODE_TYPES)}" if bad_type else "",
    )

    # ---- 功能校验：边引用 + 端口（同样汇总为每条断言的通过情况） ----
    incoming = {nid: 0 for nid in ids}
    bad_edge_obj = []  # 非对象的 edges 项
    bad_src = []  # source 指向未定义节点
    bad_dst = []  # target 指向未定义节点
    bad_source_handle = []  # sourceHandle 不属于上游输出端口
    bad_target_handle = []  # targetHandle 不属于下游输入端口
    for j, edge in enumerate(edges):
        if not isinstance(edge, dict):
            bad_edge_obj.append(f"edges[{j}]")
            continue
        src, dst = edge.get("source"), edge.get("target")
        if src not in ids:
            bad_src.append(f"edges[{j}]（source={src!r}）")
        if dst not in ids:
            bad_dst.append(f"edges[{j}]（target={dst!r}）")
        elif src in ids:
            incoming[dst] = incoming.get(dst, 0) + 1

        src_type = (
            nodes[ids[src]].get("type")
            if src in ids and isinstance(nodes[ids[src]], dict)
            else None
        )
        dst_type = (
            nodes[ids[dst]].get("type")
            if dst in ids and isinstance(nodes[ids[dst]], dict)
            else None
        )

        # 端口名校验（dynamic 端口名由 config 决定，故仅做警告级提示）
        sh = edge.get("sourceHandle")
        if (
            sh
            and sh not in STATIC_OUTPUTS.get(src_type, [])
            and src_type not in DYNAMIC_OUTPUT_TYPES
        ):
            bad_source_handle.append(
                f"edges[{j}]（{sh!r} 不属于 {src_type} 的输出端口）"
            )
        th = edge.get("targetHandle")
        if (
            th
            and th not in STATIC_INPUTS.get(dst_type, [])
            and dst_type not in DYNAMIC_INPUT_TYPES
        ):
            bad_target_handle.append(
                f"edges[{j}]（{th!r} 不属于 {dst_type} 的输入端口）"
            )

    _check(
        checks,
        "所有 edges 项均为对象",
        not bad_edge_obj,
        "error",
        f"非对象项：{bad_edge_obj}" if bad_edge_obj else "",
    )
    _check(
        checks,
        "所有边的 source 指向已定义节点",
        not bad_src,
        "error",
        f"异常边：{bad_src}" if bad_src else "",
    )
    _check(
        checks,
        "所有边的 target 指向已定义节点",
        not bad_dst,
        "error",
        f"异常边：{bad_dst}" if bad_dst else "",
    )
    _check(
        checks,
        "所有 sourceHandle 属于上游输出端口（动态端口除外）",
        not bad_source_handle,
        "warn",
        f"可疑边：{bad_source_handle}" if bad_source_handle else "",
    )
    _check(
        checks,
        "所有 targetHandle 属于下游输入端口（动态端口除外）",
        not bad_target_handle,
        "warn",
        f"可疑边：{bad_target_handle}" if bad_target_handle else "",
    )

    # ---- 功能校验：孤立节点 ----
    orphans = []  # 既无入边又没有 trigger 端口的节点
    for nid, idx in ids.items():
        node = nodes[idx]
        ntype = node.get("type")
        if ntype in ("task_input", "env_loader"):
            continue  # 无输入端口的开局节点
        if incoming.get(nid, 0) == 0 and "trigger" not in STATIC_INPUTS.get(ntype, []):
            orphans.append(f"`{nid}`（{ntype}）")
    _check(
        checks,
        "所有无 trigger 端口的节点均有上游输入",
        not orphans,
        "warn",
        f"既无连边又无 trigger 端口，开局不会执行：{orphans}" if orphans else "",
    )

    _check(
        checks,
        "存在 task_output 节点",
        has_task_output,
        "warn",
        "" if has_task_output else "图中未声明全局输出节点",
    )

    # ---- 功能校验：global_schema ----
    gs = doc.get("global_schema")
    if gs is not None:
        ok = isinstance(gs, dict)
        _check(
            checks,
            "global_schema 为对象",
            ok,
            "error",
            "" if ok else "global_schema 必须是对象",
        )
        if ok:
            bad_gs_obj = [f"`{k}`" for k, v in gs.items() if not isinstance(v, dict)]
            bad_gs_type = [
                f"`{k}`"
                for k, v in gs.items()
                if isinstance(v, dict) and "type" not in v
            ]
            _check(
                checks,
                "global_schema 各项均为对象",
                not bad_gs_obj,
                "error",
                f"非对象项：{bad_gs_obj}" if bad_gs_obj else "",
            )
            _check(
                checks,
                "global_schema 各项均声明 `type`",
                not bad_gs_type,
                "warn",
                f"缺少 type，前端表单无法渲染：{bad_gs_type}" if bad_gs_type else "",
            )
            if has_task_input:
                missing = [
                    k
                    for k, v in gs.items()
                    if isinstance(v, dict)
                    and v.get("required")
                    and k not in global_vars
                ]
                _check(
                    checks,
                    "必填 global_schema 键已声明为 task_input 全局变量",
                    not missing,
                    "warn",
                    f"未在 task_input.global_vars 中声明：{missing}" if missing else "",
                )

    return _report(checks)


def _report(checks):
    errors = sum(1 for c in checks if c["level"] == "error" and not c["ok"])
    warnings = sum(1 for c in checks if c["level"] == "warn" and not c["ok"])
    return {"checks": checks, "errors": errors, "warnings": warnings, "ok": errors == 0}


def validate_graph_folder(folder, expected_name=None):
    """校验一个 graph 文件夹（含 graph.json），返回结构化报告。"""
    checks = []
    path = os.path.join(folder, "graph.json")
    if not os.path.isfile(path):
        _check(checks, "graph.json 存在", False, "error", f"未找到 {path}")
        return _report(checks)
    _check(checks, "graph.json 存在", True, "error")
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        _check(checks, "graph.json 可解析", False, "error", f"解析失败：{e}")
        return _report(checks)
    _check(checks, "graph.json 可解析", True, "error")
    res = validate_graph_doc(doc, expected_name)
    res["checks"] = checks + res["checks"]
    res["errors"] = sum(
        1 for c in res["checks"] if c["level"] == "error" and not c["ok"]
    )
    res["warnings"] = sum(
        1 for c in res["checks"] if c["level"] == "warn" and not c["ok"]
    )
    res["ok"] = res["errors"] == 0
    return res


def _locate_folder():
    """沙盒自测用：在父目录里找含 graph.json 的文件夹。"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(os.path.join(root, "graph.json")):
        return root, os.path.basename(root)
    for item in sorted(os.listdir(root)):
        sub = os.path.join(root, item)
        if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "graph.json")):
            return sub, item
    return None, None


def _print_report(title, report):
    checks = report["checks"]
    total = len(checks)
    passed = sum(1 for c in checks if c["ok"])
    print("=" * 68)
    print(title)
    print("=" * 68)
    for i, c in enumerate(checks, 1):
        if c["ok"]:
            mark = "✅ PASS"
        elif c["level"] == "error":
            mark = "❌ FAIL"
        else:
            mark = "⚠️  WARN"
        line = f"{i:>2}. {mark} [{c['level']}] {c['title']}"
        if c["detail"]:
            line += f" — {c['detail']}"
        print(line)
    print(
        f"\n共 {total} 项，通过 {passed}/{total}；"
        f"错误 {report['errors']}，警告 {report['warnings']}，"
        f"结论：{'✅ 通过' if report['ok'] else '❌ 未通过'}"
    )
    return report["ok"]


def main():
    folder, name = _locate_folder()
    if not folder:
        print("❌ 未在沙盒中找到含 graph.json 的文件夹")
        return 1
    report = validate_graph_folder(folder, expected_name=name)
    ok = _print_report(f"Graph 校验：{name}/graph.json", report)

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "validation.json"), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except OSError:
        pass

    print(
        "\n提示：修正 ✗ 项后重跑本脚本；全绿后再用 KernelUpgrade(action='merge', type='graph') 申请合并。"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
