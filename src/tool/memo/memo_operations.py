"""Memo 备忘录核心操作模块"""

import json
import os
import threading
import uuid
import datetime
from src.utils.config import MEMORY_PENDING_DIR, AGENT_CORE_DIR, get_agent_model
from src.model import AgentModel

MEMORY_MD_PATH = os.path.join(AGENT_CORE_DIR, "MEMORY.md")

OVERWRITE_MEMORY_MD_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "overwrite_memory_md",
        "description": "智能整合新旧记忆后，全量覆盖写入 Markdown 档案",
        "parameters": {
            "type": "object",
            "properties": {
                "new_markdown_content": {
                    "type": "string",
                    "description": "整合后的全新 Markdown 纯文本内容"
                }
            },
            "required": ["new_markdown_content"]
        }
    }
}


def _validate_memo_data(memo_data: dict) -> tuple[dict, list]:
    """
    校验 memo_data 参数，返回 (valid_data, errors)

    Args:
        memo_data: 记忆数据字典

    Returns:
        (valid_data, errors) - 校验后的数据和错误列表
    """
    errors = []
    valid_data = {
        "short_term": "",
        "work_exp": [],
        "user_profile": [],
        "events": [],
        "cognition": []
    }

    if not isinstance(memo_data, dict):
        return {}, ["memo_data 必须是对象"]

    short_term = memo_data.get("short_term")
    if short_term is not None and not isinstance(short_term, str):
        errors.append(f"short_term 必须是字符串，收到 {type(short_term).__name__}")
    elif short_term:
        valid_data["short_term"] = short_term.strip()

    work_exp = memo_data.get("work_exp", [])
    if not isinstance(work_exp, list):
        errors.append(f"work_exp 必须是数组，收到 {type(work_exp).__name__}")
    else:
        for i, w in enumerate(work_exp):
            if not isinstance(w, str) or not w.strip():
                errors.append(f"work_exp[{i}] 无效：每条经验必须是非空字符串")
            elif len(w.strip()) > 500:
                errors.append(f"work_exp[{i}] 过长（{len(w.strip())}字符），建议每条不超过500字符")
            else:
                valid_data["work_exp"].append(w.strip())

    user_profile = memo_data.get("user_profile", [])
    if not isinstance(user_profile, list):
        errors.append(f"user_profile 必须是数组，收到 {type(user_profile).__name__}")
    else:
        for i, u in enumerate(user_profile):
            if not isinstance(u, str) or not u.strip():
                errors.append(f"user_profile[{i}] 无效：每条画像必须是非空字符串")
            else:
                valid_data["user_profile"].append(u.strip())

    events = memo_data.get("events", [])
    if not isinstance(events, list):
        errors.append(f"events 必须是数组，收到 {type(events).__name__}")
    else:
        for i, e in enumerate(events):
            if not isinstance(e, dict):
                errors.append(f"events[{i}] 无效：每条事件必须是对象 {{time, event}}")
            elif "time" not in e or "event" not in e:
                errors.append(f"events[{i}] 缺少字段：需要 time 和 event")
            elif not isinstance(e["time"], str) or not e["time"].strip():
                errors.append(f"events[{i}].time 无效：必须是非空字符串")
            elif not isinstance(e["event"], str) or not e["event"].strip():
                errors.append(f"events[{i}].event 无效：必须是非空字符串")
            else:
                valid_data["events"].append({"time": e["time"].strip(), "event": e["event"].strip()})

    cognition = memo_data.get("cognition", [])
    if not isinstance(cognition, list):
        errors.append(f"cognition 必须是数组，收到 {type(cognition).__name__}")
    else:
        for i, c in enumerate(cognition):
            if not isinstance(c, str) or not c.strip():
                errors.append(f"cognition[{i}] 无效：每条认知必须是非空字符串")
            elif len(c.strip()) > 500:
                errors.append(f"cognition[{i}] 过长（{len(c.strip())}字符），建议每条不超过500字符")
            else:
                valid_data["cognition"].append(c.strip())

    return valid_data, errors


def _smart_update_memory_md(work_exp: list, user_profile: list):
    """通过 AgentModel + reAct 循环智能更新 MEMORY.md"""
    if not work_exp and not user_profile:
        return

    def _async_rewrite_task():
        current_md = ""
        if os.path.exists(MEMORY_MD_PATH):
            with open(MEMORY_MD_PATH, "r", encoding="utf-8") as f:
                current_md = f.read()

        model = AgentModel(task_id="memory_writer")
        messages = []
        system_prompt = "你是一个后台记忆整理 Agent。当前系统有一个长期记忆档案 MEMORY.md。你需要把最新传入的工作经验和用户画像，智能地融合进现有的 Markdown 内容中。去重、合并相似项，保持条理清晰。你必须调用 overwrite_memory_md 工具来完成最终的写入操作。"
        user_prompt = f"【现有长期记忆档案】\n{current_md if current_md else '（暂无）'}\n\n【本次新增工作经验】\n{work_exp if work_exp else '（无）'}\n\n【本次新增用户画像】\n{user_profile if user_profile else '（无）'}"

        messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        max_iterations = 10
        has_write_operation = False

        for iteration in range(max_iterations):
            try:
                response = model.chat(messages=messages, tools=[OVERWRITE_MEMORY_MD_TOOL_SCHEMA])
                msg_resp = response.choices[0].message

                assist_msg = {"role": "assistant", "content": msg_resp.content or ""}
                rc = getattr(msg_resp, "reasoning_content", None)
                if rc is None and hasattr(msg_resp, "model_dump"):
                    rc = msg_resp.model_dump().get("reasoning_content")
                if rc is not None:
                    assist_msg["reasoning_content"] = rc

                if msg_resp.tool_calls:
                    assist_msg["tool_calls"] = [
                        {
                            "id": t.id,
                            "type": t.type,
                            "function": {"name": t.function.name, "arguments": t.function.arguments}
                        } for t in msg_resp.tool_calls
                    ]
                    messages.append(assist_msg)

                    for t in msg_resp.tool_calls:
                        if t.function.name == "overwrite_memory_md":
                            has_write_operation = True
                            try:
                                args = json.loads(t.function.arguments)
                                new_md_content = args.get("new_markdown_content", "")
                                with open(MEMORY_MD_PATH, "w", encoding="utf-8") as f:
                                    f.write(new_md_content)
                                print("✅ 后台模型已智能更新 MEMORY.md")
                            except Exception as e:
                                print(f"❌ 写入 MEMORY.md 失败: {e}")
                            break

                    if has_write_operation:
                        break
                else:
                    if not has_write_operation:
                        messages.append({"role": "user", "content": "⚠️ 系统检测警告：你没有调用 overwrite_memory_md 工具。请必须调用该工具将整合后的记忆写入 MEMORY.md！"})
                        continue
                    break

            except Exception as e:
                print(f"❌ reAct 循环异常: {e}")
                break

        if not has_write_operation:
            print("⚠️ 警告：reAct 循环结束但未检测到 overwrite_memory_md 调用")

    threading.Thread(target=_async_rewrite_task, daemon=True).start()


def _write_to_pending(events: list, cognition: list, user_profile: list) -> str:
    """
    将待处理记忆写入 pending，供后台 worker 抓取
    """
    os.makedirs(MEMORY_PENDING_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"memory_{timestamp}_{unique_id}.json"
    filepath = os.path.join(MEMORY_PENDING_DIR, filename)

    data = {
        "user_profile": user_profile or [],
        "events": events or [],
        "cognition": cognition or [],
        "timestamp": timestamp,
        "source": "main agent"
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath
