"""Request 工具 API 层 - 物理删除并自动化执行生效"""

import json
import os

from src.tool.request import _shared
from src.tool.request.request_operations import (
    REQUESTS_FILE,
    REQUEST_LOCK,
    read_requests,
    write_requests,
)
from src.utils.config import FILE_CONFIG_PATH, AGENT_VM_DIR
from src.utils.graph_api import graph_file


def get_pending_requests() -> list:
    """获取待处理请求"""
    if not os.path.exists(REQUESTS_FILE):
        return []
    with REQUEST_LOCK:
        try:
            data = read_requests()
        except json.JSONDecodeError:
            return []
    pending_list = [req for req in data.values() if req.get("status") == "pending"]
    pending_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return pending_list


def kick_pending_skill_tests():
    """主进程轮询钩子：为新的 skill_test 请求自动启动 Trigger 免审测试。

    Request 工具运行在隔离子进程中，无法在那里起后台线程（会随子进程退出被杀），
    故由主进程在 /api/requests 轮询时接管：发现未启动 trigger 的 skill_test 请求，
    在主进程内启动后台 Trigger 测试；若本地无 skill_eval 图，则自动将其移出待审队列
    （盲测无从审批，trigger 跑完即流程结束）。
    """
    if not os.path.exists(REQUESTS_FILE):
        return
    with REQUEST_LOCK:
        try:
            data = read_requests()
        except (json.JSONDecodeError, OSError):
            return

        changed = False
        for req in data.values():
            if (
                req.get("type") != "skill_test"
                or req.get("status") != "pending"
                or req.get("trigger_started")
            ):
                continue

            workplace_id, _, skill_name = req.get("target", "").partition("/")
            if not workplace_id or not skill_name:
                continue

            from src.evolve import run_skill_trigger_eval_background

            run_skill_trigger_eval_background(workplace_id, skill_name)
            req["trigger_started"] = True
            changed = True

            # 本地无 skill_eval 图：盲测自动跳过，请求脱离待审队列
            if not os.path.exists(graph_file("skill_eval")):
                req["status"] = "trigger_only"

        if changed:
            try:
                write_requests(data)
            except OSError:
                pass


def kick_pending_sensor_tests():
    """主进程轮询钩子：为新的 sensor_test 请求自动启动免审协议体检。

    与 skill_test 同理，体检必须在主进程内起后台线程。体检全绿后才能申请
    sensor_merge，故这里没有需要人类审批的环节，启动后直接把请求移出待审队列。
    """
    if not os.path.exists(REQUESTS_FILE):
        return
    with REQUEST_LOCK:
        try:
            data = read_requests()
        except (json.JSONDecodeError, OSError):
            return

        changed = False
        for req in data.values():
            if (
                req.get("type") != "sensor_test"
                or req.get("status") != "pending"
                or req.get("eval_started")
            ):
                continue

            workplace_id, _, sensor_name = req.get("target", "").partition("/")
            if not workplace_id or not sensor_name:
                continue

            from src.evolve import run_sensor_eval_background

            run_sensor_eval_background(workplace_id, sensor_name)
            req["eval_started"] = True
            req["status"] = "eval_only"
            changed = True

        if changed:
            try:
                write_requests(data)
            except OSError:
                pass


def _grant_file_permission(req_type: str, target: str):
    """自动将目标路径写入 file.json 对应的权限组，实现人类授权豁免"""
    with open(FILE_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    if "permissions" not in config:
        config["permissions"] = {"blocked": [], "readonly": [], "writable": []}
    perms = config["permissions"]

    target_norm = _shared.normalize_target_path(target)

    if req_type == "file_read":
        if target_norm in perms["blocked"]:
            perms["blocked"].remove(target_norm)
        if (
            target_norm not in perms["readonly"]
            and target_norm not in perms["writable"]
        ):
            perms["readonly"].append(target_norm)

    elif req_type == "file_write":
        if target_norm in perms["blocked"]:
            perms["blocked"].remove(target_norm)
        if target_norm in perms["readonly"]:
            perms["readonly"].remove(target_norm)
        if target_norm not in perms["writable"]:
            perms["writable"].append(target_norm)

    with open(FILE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _split_merge_target(target: str) -> tuple[str, str]:
    """合并目标统一为 'uuid/名字'，返回 (workplace_id, name)。"""
    return _shared.split_merge_target(target)


def resolve_request(
    req_id: str,
    approved: bool,
    feedback: str = "",
    ignore: bool = False,
) -> dict:
    if not os.path.exists(REQUESTS_FILE):
        return {"status": "error", "message": "文件不存在"}

    with REQUEST_LOCK:
        data = read_requests()
        if req_id not in data:
            return {"status": "error", "message": "请求找不到"}

        req = data[req_id]
        req_type, target = req.get("type"), req.get("target")

        # 处理人类的通过决策
        if approved and not ignore:
            try:
                if req_type in ["file_read", "file_write"]:
                    _grant_file_permission(req_type, target)
                # ---- 技能盲测逻辑：批准后由系统自动在后台运行 ----
                elif req_type == "skill_test":
                    from src.evolve import run_skill_eval_background

                    workplace_id, _, skill_name = target.partition("/")
                    sandbox_dir = os.path.join(
                        AGENT_VM_DIR, "skill_workplace", workplace_id, skill_name
                    )
                    if workplace_id and skill_name and os.path.exists(sandbox_dir):
                        from src.agent.manager import manager

                        main_session_id = manager.get_active_session_id()
                        run_skill_eval_background(
                            workplace_id, skill_name, main_session_id
                        )
                        feedback = (
                            f"用户已批准盲测，技能 '{skill_name}' 的后台盲测已自动启动，"
                            f"完成后将通过系统级通知汇报结果，请挂起等待，禁止轮询。"
                            f"（Trigger 激发测试此前已免审直接运行）\n(用户批注: {feedback})"
                        )
                    else:
                        approved = False
                        feedback = f"测试启动失败：未找到 {target} 对应的工厂沙盒目录（应为 'uuid/技能名'）。"
                # ---- 技能合并逻辑 ----
                elif req_type == "skill_merge":
                    from src.evolve import skill_request_handle

                    workplace_id, name = _split_merge_target(target)
                    workplace_root = os.path.join(
                        AGENT_VM_DIR, "skill_workplace", workplace_id
                    )
                    if name and os.path.isdir(os.path.join(workplace_root, name)):
                        sys_note = skill_request_handle(
                            workplace_root, name, is_approved=True
                        )
                        feedback = f"{sys_note}\n(用户批注: {feedback})"
                    else:
                        feedback = f"合并失败：未找到沙盒对象 '{target}'（应为 'uuid/技能名'）。"
                # ---- MCP 合并逻辑 ----
                elif req_type == "mcp_merge":
                    from src.evolve import mcp_request_handle

                    workplace_id, name = _split_merge_target(target)
                    workplace_root = os.path.join(
                        AGENT_VM_DIR, "mcp_workplace", workplace_id
                    )
                    if name and os.path.isdir(os.path.join(workplace_root, name)):
                        sys_note = mcp_request_handle(
                            workplace_root, name, is_approved=True
                        )
                        feedback = f"{sys_note}\n(用户批注: {feedback})"
                    else:
                        feedback = f"合并失败：未找到沙盒对象 '{target}'（应为 'uuid/MCP名'）。"
                # ---- Sensor 合并逻辑 ----
                elif req_type == "sensor_merge":
                    from src.evolve import sensor_request_handle

                    # sensor 沙盒结构：sensor_workplace/<uuid>/<name>.py（单文件而非目录）
                    workplace_id, name = _split_merge_target(target)
                    workplace_root = os.path.join(
                        AGENT_VM_DIR, "sensor_workplace", workplace_id
                    )
                    if name and os.path.isfile(
                        os.path.join(workplace_root, f"{name}.py")
                    ):
                        sys_note = sensor_request_handle(
                            workplace_root, name, is_approved=True
                        )
                        feedback = f"{sys_note}\n(用户批注: {feedback})"
                    else:
                        feedback = f"合并失败：未找到沙盒对象 '{target}'（应为 'uuid/Sensor名'）。"
                # ---- AgentLoop 合并逻辑 ----
                elif req_type == "agentloop_merge":
                    from src.evolve import agentloop_request_handle

                    # agentloop 沙盒结构：agentloop_workplace/<uuid>/<name>.yaml（单文件）
                    workplace_id, name = _split_merge_target(target)
                    workplace_root = os.path.join(
                        AGENT_VM_DIR, "agentloop_workplace", workplace_id
                    )
                    if name and os.path.isfile(
                        os.path.join(workplace_root, f"{name}.yaml")
                    ):
                        sys_note = agentloop_request_handle(
                            workplace_root, name, is_approved=True
                        )
                        feedback = f"{sys_note}\n(用户批注: {feedback})"
                    else:
                        feedback = f"合并失败：未找到沙盒对象 '{target}'（应为 'uuid/范式名'）。"
                # ---- Graph 合并逻辑 ----
                elif req_type == "graph_merge":
                    from src.evolve import graph_request_handle

                    # graph 沙盒结构：graph_workplace/<uuid>/<name>/graph.json（文件夹）
                    workplace_id, name = _split_merge_target(target)
                    workplace_root = os.path.join(
                        AGENT_VM_DIR, "graph_workplace", workplace_id
                    )
                    if name and os.path.isfile(
                        os.path.join(workplace_root, name, "graph.json")
                    ):
                        sys_note = graph_request_handle(
                            workplace_root, name, is_approved=True
                        )
                        feedback = f"{sys_note}\n(用户批注: {feedback})"
                    else:
                        feedback = (
                            f"合并失败：未找到沙盒对象 '{target}'（应为 'uuid/图名'）。"
                        )
            except Exception as e:
                approved = False
                feedback = f"用户已同意，但执行失败: {str(e)}。{feedback}"

        # 处理人类的拒绝决策
        elif not approved and not ignore:
            feedback = _shared.format_rejection_feedback(req_type, feedback)

        # 🌟 dependency_check 类型为系统启动检查，与 Agent 任务无关，不需要回调通知 Agent
        if not ignore and req_type != "dependency_check":
            callback_msg = _shared.build_decision_callback(
                req_id, target, approved, req_type, feedback
            )

            from src.agent import agent_force_push

            agent_force_push(callback_msg, type="system")

        del data[req_id]
        write_requests(data)

    return {"status": "success", "message": "处理完毕并移除"}


def get_resolved_requests() -> list:
    """已废弃，直接返回空列表防前端报错"""
    return []


def delete_request(req_id: str) -> bool:
    """手动删除记录 (防前端按钮报错)"""
    if not os.path.exists(REQUESTS_FILE):
        return False
    with REQUEST_LOCK:
        try:
            data = read_requests()
            if req_id in data:
                del data[req_id]
                write_requests(data)
                return True
        except Exception:
            pass
    return False
