"""Memo 备忘录核心操作模块"""

import json
import os
import threading
from typing import List, Dict, Any

from src.utils.config import SRC_DIR


MEMO_FILE_LOCK = threading.Lock()


def _validate_params(short_term: str = None, events: list = None, 
                     work_exp: list = None, cognition: list = None,
                     reminders: str = None, project_state: str = None) -> tuple:
    """
    参数校验
    
    Returns:
        (valid_events, valid_work_exp, valid_cognition, errors)
    """
    errors = []
    
    # short_term 必填校验
    if not short_term or not short_term.strip():
        errors.append("short_term 不能为空，请提供当前工作上下文")
    
    # events 校验
    valid_events = []
    if events is not None:
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
                    valid_events.append({"time": e["time"].strip(), "event": e["event"].strip()})
    
    # work_exp 校验
    valid_work_exp = []
    if work_exp is not None:
        if not isinstance(work_exp, list):
            errors.append(f"work_exp 必须是数组，收到 {type(work_exp).__name__}")
        else:
            for i, w in enumerate(work_exp):
                if not isinstance(w, str) or not w.strip():
                    errors.append(f"work_exp[{i}] 无效：每条经验必须是非空字符串")
                elif len(w.strip()) > 500:
                    errors.append(f"work_exp[{i}] 过长（{len(w.strip())}字符），建议每条不超过500字符")
                else:
                    valid_work_exp.append(w.strip())
    
    # cognition 校验
    valid_cog = []
    if cognition is not None:
        if not isinstance(cognition, list):
            errors.append(f"cognition 必须是数组，收到 {type(cognition).__name__}")
        else:
            for i, c in enumerate(cognition):
                if not isinstance(c, str) or not c.strip():
                    errors.append(f"cognition[{i}] 无效：每条认知必须是非空字符串")
                elif len(c.strip()) > 500:
                    errors.append(f"cognition[{i}] 过长（{len(c.strip())}字符），建议每条不超过500字符")
                else:
                    valid_cog.append(c.strip())
    
    # reminders 校验
    if reminders is not None and not isinstance(reminders, str):
        errors.append("reminders 必须是字符串")
    
    # project_state 校验
    if project_state is not None and not isinstance(project_state, str):
        errors.append("project_state 必须是字符串")
    
    return valid_events, valid_work_exp, valid_cog, errors


def _update_core_information(flush_data: str):
    """
    异步更新核心档案
    
    Args:
        flush_data: 要合并到核心档案的数据
    """
    def background_task():
        from src.model import Model
        from src.utils.config import get_agent_model
        
        profile_path = os.path.join(SRC_DIR, "agent", "core", "memory.md")
        
        def get_profile():
            with MEMO_FILE_LOCK:
                if os.path.exists(profile_path):
                    with open(profile_path, "r", encoding="utf-8") as f:
                        return f.read().strip() or "（当前档案为空）"
                return "（当前档案为空）"
        
        def update_profile(content: str):
            with MEMO_FILE_LOCK:
                os.makedirs(os.path.dirname(profile_path), exist_ok=True)
                with open(profile_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return "更新成功"
        
        temp_tools = [
            {
                "type": "function",
                "function": {
                    "name": "get",
                    "description": "读取当前核心档案内容",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update",
                    "description": "<覆盖>更新核心档案内容",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string",
                                        "description": "全新的完整档案内容，纯文本，不要有Markdown代码块的反引号"}
                        },
                        "required": ["content"]
                    }
                }
            }
        ]
        
        system_prompt = """你是一个专门负责知识库维护的后台记忆整理中枢。核心职责是**严格筛选，宁缺毋滥**。

【核心文档结构规范】
现有的 memory.md 包含三大固定板块，合并新记忆时**必须严格归类到这三个板块下，并保持原有的标题结构不变（可以加上Markdown的 # 标识标题）**：
# 用户偏好与工作风格
# 重要技术发现
# 避坑经验
你的任务：
1. 先用 get 获取当前文档。
2. 逐条判断新记忆是否真的有长期保留价值（情绪化表达、一次性事件、无关紧要的细节直接丢弃）。
3. 将有价值的信息，智能归类、合并去重到上述三大板块中。如果现有记录更详细，则保留现有记录。
4. 保持文档极度精简，每条记录一句话以内，使用无序列表 `- `。
5. 最后必须调用 update 工具写入最终的合并文档。"""
        
        user_prompt = f"【新产生的长期记忆备忘录】:\n{flush_data}"
        bg_model = Model(get_agent_model())
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        max_rounds = 5
        for _ in range(max_rounds):
            response = bg_model.chat(messages=messages, tools=temp_tools, temperature=0.1)
            msg_resp = response.choices[0].message
            assist_msg = {"role": "assistant", "content": msg_resp.content or ""}
            tool_calls = msg_resp.tool_calls
            
            if tool_calls:
                assist_msg["tool_calls"] = [
                    {
                        "id": t.id,
                        "type": t.type,
                        "function": {"name": t.function.name, "arguments": t.function.arguments}
                    } for t in tool_calls
                ]
            
            messages.append(assist_msg)
            
            if not tool_calls:
                has_updated = any(m.get("name") == "update" for m in messages if m.get("role") == "tool")
                if has_updated:
                    print("📝 [Background] 核心记忆档案合并与落盘成功！")
                    break
                else:
                    messages.append(
                        {"role": "user", "content": "打回：你必须调用 update 工具来保存最终的结果！请立即调用。"})
                    continue
            
            for t in tool_calls:
                t_name = t.function.name
                res = ""
                if t_name == "get":
                    res = get_profile()
                elif t_name == "update":
                    try:
                        args = json.loads(t.function.arguments)
                        res = update_profile(args.get("content", ""))
                    except Exception as e:
                        res = f"参数解析失败: {e}"
                else:
                    res = "未知工具"
                messages.append({"role": "tool", "tool_call_id": t.id, "name": t_name, "content": str(res)})
    
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()


def _push_to_purrmemo(events: list, work_exp: list, cognition: list, 
                      reminders: str, project_state: str) -> bool:
    """
    推送到 PurrMemo
    
    Returns:
        True if successful, False otherwise
    """
    from src.loader.purrmemo_client import push_memo
    
    try:
        return push_memo(
            events=events or [],
            work_exp=work_exp or [],
            cognition=cognition or [],
            reminders=reminders,
            project_state=project_state,
        )
    except Exception as e:
        raise RuntimeError(f"PurrMemo 推送异常: {e}")


def build_flush_data(events: list, work_exp: list, cognition: list, 
                     reminders: str, project_state: str) -> str:
    """
    构建要写入的数据
    
    Returns:
        格式化的字符串数据
    """
    flush_parts = []
    if events:
        flush_parts.append(f"[事件]\n" + "\n".join(f"- {e['time']}: {e['event']}" for e in events if isinstance(e, dict)))
    if work_exp:
        flush_parts.append(f"[工作经验]\n" + "\n".join(f"- {w}" for w in work_exp if w))
    if cognition:
        flush_parts.append(f"[认知/决策]\n" + "\n".join(f"- {c}" for c in cognition if c))
    if reminders:
        flush_parts.append(f"[待办提醒]\n{reminders}")
    if project_state:
        flush_parts.append(f"[项目状态]\n{project_state}")
    
    if flush_parts:
        return "\n\n---\n\n".join(flush_parts)
    return ""