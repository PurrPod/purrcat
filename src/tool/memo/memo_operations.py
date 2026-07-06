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
            "你是一个极其克制且追求高效的后台记忆整理 Agent。\n"
            "\n"
            "当前有两个存储层：\n"
            "- 记忆数据库（事无巨细的全量日志，长期保留，不用你管）\n"
            "- MEMORY.md（注入工作主 Agent 系统提示词的\"浅层意识缓存\"，只保留最通用、最高频的核心经验）\n"
            "\n"
            "你的任务：根据最新传入的工作经验和用户画像，智能更新 MEMORY.md。\n"
            "\n"
            "【定位铁律】\n"
            "MEMORY.md 是主 Agent 在每一步决策时都会扫一眼的东西。它必须极度精炼、极度通用、没有一丝水分。\n"
            "任何只对某个特定项目、某次特定运行有意义的细节，都不配进入这个文件。\n"
            "\n"
            "【内容格式要求】\n"
            "- 每条经验必须能用一句话说清：什么情况下，应该立刻采取什么行动或想起什么规则。不超过 80 字。\n"
            "- 不要求固定句式，但密度必须高——能一句话回答\"下次遇到什么情况，应该立刻想到什么\"即可，硬凑格式反而失真。\n"
            "- 说不到点子上的、绕弯子的、凑字数的内容，一律不收录\n"
            "\n"
            "【通用性判别标准】\n"
            "以下内容 **绝对不得收录**：\n"
            "- 特定文件路径、IP地址、版本号\n"
            "- 单次运行结果（如\"某次测试通过率 97%\"）\n"
            "- 仅适用于某个特定项目、特定目录结构的操作步骤\n"
            "\n"
            "以下内容 **优先收录**：\n"
            "- 跨项目反复出现的方法论（如\"三层解耦架构\"）\n"
            "- 反直觉的系统行为（如\"bash cp 无法跨环境到宿主机路径\"）\n"
            "- 曾被重复踩过的坑（同一类问题出现 2 次以上，说明有长期价值）\n"
            "- 用户不可触碰的红线或隐性期待\n"
            "\n"
            "【数量与淘汰规则】\n"
            "- MEMORY.md 中经验总数 **必须 ≤ 15 条**\n"
            "- 每新增 1 条经验，必须从现有经验中淘汰至少 1 条（直接从文档中移除，不留删除线或批注）\n"
            "- 淘汰时，优先移除：① 最久未更新的经验 ② 适用场景最窄的经验 ③ 与其他经验重叠度最高的经验\n"
            "- 同类经验必须合并为一条，禁止出现两条指向同一场景的独立条目\n"
            "\n"
            "【写入方式】\n"
            "你必须调用 overwrite_memory_md 工具，用整理后的全量内容（≤15 条）完整覆写 MEMORY.md。"
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
