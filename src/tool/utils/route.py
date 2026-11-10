"""工具路由枢纽：解析、执行、媒体处理与输出封包。

拆分说明：
- 工具解析与隔离名单留在本模块（注册契约与文档锚点）
- 媒体落盘 / vision 直注 → media.py
- 线程与子进程执行 → execution.py
- 超长输出落盘与预览 → output_limit.py
"""

from __future__ import annotations

import importlib
import json
import time
import traceback
from typing import Any

from src.tool.utils.execution import execute_tool as _execute_tool_impl
from src.tool.utils.media import handle_media_content, is_openai_content_parts
from src.tool.utils.output_limit import (
    overflow_prompt,
    safe_truncate,
    write_overflow_cache,
)
from src.tool.utils.token_limit import (
    count_tokens,
    get_output_token_limit,
)
from src.utils.config import BUFFER_DIR

# 工具名到函数名的映射表
TOOL_FUNC_MAP = {
    "filesystem": "FileSystem",
    "bash": "Bash",
    "brainstorm": "BrainStorm",
    "cron": "Cron",
    "callmcp": "CallMCP",
    "memo": "Memo",
    "request": "Request",
    "search": "Search",
    "fetch": "Fetch",
    "task": "Task",
    "kernelupgrade": "KernelUpgrade",  # 🌟 新增注册
}

# 🌟 进程隔离名单：只有这些「易卡死」的工具才丢进子进程执行（可被物理级 terminate）
# 其余工具（memo/filesystem/cron/task/brainstorm/callmcp/kernelupgrade）持有进程内状态
# （如 brainstorm/task 会 lazy import AgentManager、callmcp 持有 MCP 长连接），
# 子进程化会出灾难性后果，保持进程内执行
# ⚠️ callmcp 曾被隔离导致 MCP 连接随子进程退出被销毁（Chrome 等被连带关闭），
# 防卡死改由 tool_caller 中的 asyncio.wait_for 超时兜底
PROCESS_ISOLATED_TOOLS = {
    "bash",  # 长时命令 / 死循环
    "request",  # 网络请求
    "fetch",  # 网络抓取
    "search",  # 向量检索（含嵌入计算）
}

# 系统注入参数：模型不可见，由 Agent / Harness / dispatch 自动补齐。
# 注入点：agent.py（Bash 的 session_id、Task 的 _session_id/_request_bytes/
# _request_limit_bytes、BrainStorm 的 _tool_call_id）、harness/agent_node.py
# （session_id、_is_sub_branch）、dispatch_tool（Task 的 _vision_mode）。
SYSTEM_INJECTED_ARGUMENTS = frozenset(
    {
        "session_id",
        "_is_sub_branch",
        "_session_id",
        "_request_bytes",
        "_request_limit_bytes",
        "_tool_call_id",
        "_vision_mode",
    }
)


def resolve_tool(tool_name: str):
    """按工具名解析出真实可调用函数；dispatch 与注册契约测试共用同一份规则。"""
    tool_name_lower = tool_name.lower()
    func_name = TOOL_FUNC_MAP.get(tool_name_lower, tool_name.capitalize())

    module_path = f"src.tool.{tool_name_lower}.{tool_name_lower}"
    try:
        tool_module = importlib.import_module(module_path)
    except ImportError:
        module_path = f"src.tool.{tool_name_lower}"
        tool_module = importlib.import_module(module_path)

    target_func = getattr(tool_module, func_name, None)
    if target_func is None:
        raise AttributeError(f"工具模块 '{module_path}' 中未找到函数: {func_name}")
    return target_func


def _unpack_result(result_obj: Any) -> tuple[Any, dict]:
    """兼容新版 {"content","metadata"} 与旧工具的直接返回。"""
    if isinstance(result_obj, dict) and "metadata" in result_obj:
        return result_obj.get("content", ""), result_obj.get("metadata", {})
    return result_obj, {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "type": "text",
        "snip": "",
    }


def _pack_vision_parts(content_data: list, metadata: dict) -> str:
    """vision 直注结果跳过截断与格式化，只把 snip 并入文本 part。"""
    snip = str(metadata.get("snip") or "").strip()
    if snip:
        for part in content_data:
            if part.get("type") == "text":
                part["text"] = f"{part['text']}\n{snip}"
                break
    metadata = dict(metadata)
    metadata["type"] = "text"
    return json.dumps(
        {"content": content_data, "metadata": metadata}, ensure_ascii=False
    )


def _apply_output_limit(
    content_data: Any,
    *,
    tool_name_lower: str,
    metadata: dict,
    arguments: dict,
    available_tokens: int | None,
) -> Any:
    """超长输出落盘并改为预览；返回最终 content。"""
    if isinstance(content_data, (dict, list)):
        actual_content_str = json.dumps(content_data, ensure_ascii=False, indent=2)
    else:
        actual_content_str = str(content_data)

    max_output_tokens = get_output_token_limit(available_tokens)
    is_fetch_skill = (
        tool_name_lower == "fetch" and arguments.get("source", "").lower() == "skill"
    )
    content_token_count = count_tokens(actual_content_str)
    if content_token_count <= max_output_tokens or is_fetch_skill:
        return content_data

    file_name = write_overflow_cache(actual_content_str, tool_name_lower, BUFFER_DIR)
    content_data = overflow_prompt(
        tool_name=tool_name_lower,
        content_token_count=content_token_count,
        max_output_tokens=max_output_tokens,
        file_name=file_name,
        preview=safe_truncate(content_data, max_output_tokens),
    )
    metadata["type"] = "warning"
    metadata["snip"] = "字数超长已被截断并落盘"
    return content_data


def dispatch_tool(
    tool_name: str,
    arguments: dict,
    available_tokens: int = None,
    cancel_event=None,
    vision_mode: bool = False,
):
    """
    核心路由枢纽：纯净的数据流处理
    cancel_event: threading.Event，被 set 时物理掐断正在执行的工具并返回伪造打断结果
    vision_mode: 调用方模型开启了 vision 直注（图片不落盘，直接以 OpenAI
    多模态格式返回，由调用方解包进 tool 消息的 content）
    """
    try:
        tool_name_lower = tool_name.lower()

        # 🌟 vision 直注模式下，告知 Task 工具调用方支持视觉
        # （action=vision 时直接返回图片本体，不再走视觉顾问模型）
        if vision_mode and tool_name_lower == "task":
            arguments["_vision_mode"] = True

        target_func = resolve_tool(tool_name)
        result_obj = _execute_tool_impl(
            target_func,
            arguments,
            cancel_event=cancel_event,
            isolated=tool_name_lower in PROCESS_ISOLATED_TOOLS,
        )

        content_data, metadata = _unpack_result(result_obj)

        # 多媒体字典退化为路径提示；vision 模式下图片直接变成 OpenAI parts
        content_data = handle_media_content(
            content_data,
            tool_name_lower,
            buffer_dir=BUFFER_DIR,
            vision_mode=vision_mode,
        )

        # 🌟 vision 直注结果：base64 不能被 token 截断/yaml 转换污染
        if is_openai_content_parts(content_data):
            return _pack_vision_parts(content_data, metadata)

        content_data = _apply_output_limit(
            content_data,
            tool_name_lower=tool_name_lower,
            metadata=metadata,
            arguments=arguments,
            available_tokens=available_tokens,
        )

        # 强制将遗漏的 dict/list 转换为自然语言纯文本（防 JSON 解析）
        if isinstance(content_data, (dict, list)):
            import yaml

            content_data = yaml.dump(
                content_data, allow_unicode=True, default_flow_style=False
            )
            content_data = f"【系统格式化输出】\n{content_data}"

        return json.dumps(
            {"content": str(content_data), "metadata": metadata}, ensure_ascii=False
        )

    except Exception as e:
        traceback.print_exc()
        err_msg = f"❌ 工具 [{tool_name}] 调度/执行发生异常: {str(e)}"
        return json.dumps(
            {
                "content": err_msg,
                "metadata": {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "error",
                    "snip": "❌ 执行异常",
                },
            },
            ensure_ascii=False,
        )


# ==========================================
# 🌟 vision 直注结果的调用方辅助函数
# ==========================================


def extract_tool_message_content(result: Any) -> Any:
    """dispatch_tool 返回值 → tool 消息的 content。

    vision 直注结果（{"content": [OpenAI parts], "metadata": ...}）解包为
    多模态 parts 列表（符合 OpenAI tool 消息 content 数组规范）；
    普通结果原样返回字符串。
    """
    if isinstance(result, str):
        try:
            obj = json.loads(result)
            if isinstance(obj, dict) and is_openai_content_parts(obj.get("content")):
                return obj["content"]
        except Exception:
            pass
    return result


def build_display_result(result: Any) -> str:
    """dispatch_tool 返回值 → 前端/ACP 总线展示用结果。

    vision 直注结果剥离 image_url parts（base64 不外泄），只保留文本占位。
    """
    parts = extract_tool_message_content(result)
    if isinstance(parts, list):
        texts = [
            str(p.get("text", ""))
            for p in parts
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        try:
            metadata = json.loads(result).get("metadata", {})
        except Exception:
            metadata = {}
        return json.dumps(
            {"content": "\n".join(t for t in texts if t), "metadata": metadata},
            ensure_ascii=False,
        )
    return result
