"""Memo 备忘录核心操作模块"""

import json
import os
import threading

from src.model import AgentModel
from src.utils.config import AGENT_CORE_DIR

MEMORY_MD_PATH = os.path.join(AGENT_CORE_DIR, "MEMORY.md")
MEMORY_MD_LOCK = threading.Lock()

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
                    "description": "整合后的全新 Markdown 纯文本内容",
                }
            },
            "required": ["new_markdown_content"],
        },
    },
}


def _smart_update_memory_md(work_exp: list, user_profile: list):
    """通过 AgentModel 智能更新 MEMORY.md (同步阻塞方法，供 Worker 排队调用)"""
    if not work_exp and not user_profile:
        return

    with MEMORY_MD_LOCK:
        current_md = ""
        if os.path.exists(MEMORY_MD_PATH):
            with open(MEMORY_MD_PATH, "r", encoding="utf-8") as f:
                current_md = f.read()

        model = AgentModel(task_id="memory_writer")
        system_prompt = (
            "你是一个极其克制且追求高效的后台记忆整理 Agent。当前系统有一个长期记忆档案 MEMORY.md。\n"
            "你需要把最新传入的工作经验和用户画像，智能地融合进现有的 Markdown 内容中。\n"
            "【核心整理原则】\n"
            "1. 拒绝流水账：剔除所有仅针对特定任务、特定数据（如特定测试的通过率、单次运行日志）的冗余细节，这些不属于长期记忆。\n"
            "2. 提取与浓缩：对现有的记忆条目进行高度浓缩与萃取，只保留【通用的、未来极大可能会用到、无论做什么事情都有必要记得】的核心经验。\n"
            "3. 数量限制：如果工作经验或用户画像条目数量过多，请强制将其精简、合并。任何一个类别的核心记忆条目绝对【不能超过30条】。超过时必须进行优胜劣汰，舍弃低价值记忆。\n"
            "4. 结构清晰：保持 Markdown 条理清晰，去重合并相似项。\n"
            "你必须调用 overwrite_memory_md 工具来完成最终的全量写入操作。"
        )
        user_prompt = f"【现有长期记忆档案】\n{current_md if current_md else '（暂无）'}\n\n【本次新增工作经验】\n{work_exp if work_exp else '（无）'}\n\n【本次新增用户画像】\n{user_profile if user_profile else '（无）'}"

        messages = [{"role": "system", "content": system_prompt}]
        messages.append({"role": "user", "content": user_prompt})

        has_write_operation = False

        for iteration in range(10):
            try:
                response = model.chat(
                    messages=messages, tools=[OVERWRITE_MEMORY_MD_TOOL_SCHEMA]
                )
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
                            "function": {
                                "name": t.function.name,
                                "arguments": t.function.arguments,
                            },
                        }
                        for t in msg_resp.tool_calls
                    ]
                    messages.append(assist_msg)

                    for t in msg_resp.tool_calls:
                        if t.function.name == "overwrite_memory_md":
                            try:
                                args = json.loads(t.function.arguments)
                                new_md_content = args.get("new_markdown_content", "")
                                temp_path = f"{MEMORY_MD_PATH}.tmp"
                                with open(temp_path, "w", encoding="utf-8") as f:
                                    f.write(new_md_content)
                                os.replace(temp_path, MEMORY_MD_PATH)
                                print("✅ 后台模型已智能更新 MEMORY.md")
                                has_write_operation = True
                            except json.JSONDecodeError as e:
                                print(f"❌ 工具参数解析失败，转义错误: {e}")
                            except Exception as e:
                                print(f"❌ 写入 MEMORY.md 失败: {e}")
                            break

                    if has_write_operation:
                        break
                    else:
                        messages.append(
                            {
                                "role": "user",
                                "content": "写入失败，请修正后重新调用工具。",
                            }
                        )

            except Exception as e:
                print(f"❌ reAct 循环异常: {e}")
                break

        if not has_write_operation:
            print("⚠️ 警告：reAct 循环结束但未检测到 overwrite_memory_md 调用")
