"""Request 工具 API 层 - 物理删除并自动化执行生效"""

import json
import os
import urllib.request
import zipfile
import io

from src.tool.request.request_operations import REQUESTS_FILE, REQUEST_LOCK
from src.utils.config import FILE_CONFIG_PATH, SKILL_DIR, AGENT_VM_DIR, GRAPHS_DIR


def get_pending_requests() -> list:
    """获取待处理请求"""
    if not os.path.exists(REQUESTS_FILE):
        return []
    with REQUEST_LOCK:
        try:
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
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
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
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
            if not os.path.exists(os.path.join(GRAPHS_DIR, "skill_eval.json")):
                req["status"] = "trigger_only"

        if changed:
            try:
                with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except OSError:
                pass


def _grant_file_permission(req_type: str, target: str):
    """自动将目标路径写入 file.json 对应的权限组，实现人类授权豁免"""
    with open(FILE_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)

    if "permissions" not in config:
        config["permissions"] = {"blocked": [], "readonly": [], "writable": []}
    perms = config["permissions"]

    target_norm = target.replace("\\", "/")

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


def _grant_computer_use(duration: int):
    """🌟 自动下发 ComputerUse 的有时效性授权"""
    import time
    from datetime import datetime
    from src.utils.config import DATA_DIR

    auth_file = os.path.join(DATA_DIR, "checkpoints", "agent", "computer_use_auth.json")
    os.makedirs(os.path.dirname(auth_file), exist_ok=True)

    # 【修改点】：增加对特殊值（如 -1）的支持，用于代表"今日不再设限"
    if duration == -1:
        # 获取今天 23:59:59 的时间戳
        now = datetime.now()
        end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
        expire_at = end_of_day.timestamp()
    else:
        # 常规情况：当前时间戳 + duration（如 10, 30）分钟
        expire_at = time.time() + duration * 60

    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump({"expire_at": expire_at}, f)


def _install_skill_from_github(skill_name: str):
    """下载并安装特定 Skill"""
    url = "https://github.com/PurrPod/skillpod/archive/refs/heads/main.zip"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    response = urllib.request.urlopen(req)
    zip_data = response.read()

    dest_base = SKILL_DIR

    extracted = False
    with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
        for file_info in z.infolist():
            parts = file_info.filename.split("/")
            if (
                len(parts) >= 4
                and parts[1] in ["official", "community"]
                and parts[2] == skill_name
            ):
                rel_path = file_info.filename.split(f"/{skill_name}/", 1)[1]
                if not rel_path:
                    continue
                local_path = os.path.join(dest_base, skill_name, rel_path)
                if file_info.is_dir():
                    os.makedirs(local_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    with open(local_path, "wb") as f:
                        f.write(z.read(file_info.filename))
                extracted = True

    if not extracted:
        raise Exception(f"仓库未找到技能 '{skill_name}'")
    from src.tool.search.skill_search import SkillSearcher

    SkillSearcher().reload_index()


def resolve_request(
    req_id: str,
    approved: bool,
    feedback: str = "",
    ignore: bool = False,
    duration: int = 5,
) -> dict:
    if not os.path.exists(REQUESTS_FILE):
        return {"status": "error", "message": "文件不存在"}

    with REQUEST_LOCK:
        with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if req_id not in data:
            return {"status": "error", "message": "请求找不到"}

        req = data[req_id]
        req_type, target = req.get("type"), req.get("target")

        # 处理人类的通过决策
        if approved and not ignore:
            try:
                if req_type == "skill_install":
                    _install_skill_from_github(target)
                elif req_type in ["file_read", "file_write"]:
                    _grant_file_permission(req_type, target)
                elif req_type == "computer_use":
                    _grant_computer_use(duration)
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
                            f"老板已批准盲测，技能 '{skill_name}' 的后台盲测已自动启动，"
                            f"完成后将通过系统级通知汇报结果，请挂起等待，禁止轮询。"
                            f"（Trigger 激发测试此前已免审直接运行）\n(老板批注: {feedback})"
                        )
                    else:
                        approved = False
                        feedback = f"测试启动失败：未找到 {target} 对应的工厂沙盒目录（应为 'uuid/技能名'）。"
                # ---- 技能合并逻辑 ----
                elif req_type == "skill_merge":
                    import glob
                    from src.evolve import skill_request_handle

                    paths = glob.glob(
                        os.path.join(AGENT_VM_DIR, "skill_workplace", "*", target)
                    )
                    if paths:
                        workplace_root = os.path.dirname(paths[0])
                        sys_note = skill_request_handle(
                            workplace_root, target, is_approved=True
                        )
                        feedback = f"{sys_note}\n(老板批注: {feedback})"
                    else:
                        feedback = f"合并失败：未找到 {target} 对应的工厂沙盒目录。"
                # ---- MCP 合并逻辑 ----
                elif req_type == "mcp_merge":
                    import glob
                    from src.evolve import mcp_request_handle

                    paths = glob.glob(
                        os.path.join(AGENT_VM_DIR, "mcp_workplace", "*", target)
                    )
                    if paths:
                        workplace_root = os.path.dirname(paths[0])
                        sys_note = mcp_request_handle(
                            workplace_root, target, is_approved=True
                        )
                        feedback = f"{sys_note}\n(老板批注: {feedback})"
                    else:
                        feedback = (
                            f"合并失败：未找到 {target} 对应的 MCP 工厂沙盒目录。"
                        )
            except Exception as e:
                approved = False
                feedback = f"老板已同意，但执行失败: {str(e)}。{feedback}"

        # 处理人类的拒绝决策
        elif not approved and not ignore:
            if req_type == "skill_test":
                feedback = f"老板拒绝了测试申请，请根据以下原因调整沙盒代码或测试用例后再次申请：\n【拒绝理由】: {feedback}"
            elif req_type in ["skill_merge", "mcp_merge"]:
                # 让Agent收到拒绝的理由并继续改进
                feedback = f"老板拒绝了代码合并请求，请在沙盒工厂中根据以下原因继续修复：\n【拒绝理由】: {feedback}"

        # 🌟 dependency_check 类型为系统启动检查，与 Agent 任务无关，不需要回调通知 Agent
        if not ignore and req_type != "dependency_check":
            decision_text = "【同意并已生效】" if approved else "【被拒绝】"
            callback_msg = f"🔔 【系统通知】请求 (ID: {req_id}) | 目标: {target} | 结果: {decision_text}\n系统反馈/批注: {feedback}"
            if approved and req_type not in [
                "skill_test",
                "skill_merge",
                "mcp_merge",
            ]:
                callback_msg += (
                    "\n系统已为你自动下发权限或安装插件，请直接继续执行被挂起的任务。"
                )

            from src.agent import agent_force_push

            agent_force_push(callback_msg, type="system")

        del data[req_id]
        with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
            with open(REQUESTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if req_id in data:
                del data[req_id]
                with open(REQUESTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
        except Exception:
            pass
    return False
