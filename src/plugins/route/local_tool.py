import json
import importlib
import inspect
import asyncio
from typing import Any


def _format_response(msg_type: str, content: Any) -> str:
    return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)


def call_local_tool(plugin_name: str, tool_name: str, arguments: dict, **kwargs) -> str:
    """调用本地工具（支持同步和异步函数）"""
    try:
        try:
            module_path = f"src.plugins.plugin_collection.{plugin_name}.{plugin_name}"
            plugin_module = importlib.import_module(module_path)
        except ImportError:
            module_path = f"src.plugins.plugin_collection.{plugin_name}"
            plugin_module = importlib.import_module(module_path)

        if not hasattr(plugin_module, tool_name):
            return _format_response("error", f"❌ 插件 '{plugin_name}' 中无函数：{tool_name}")

        target_func = getattr(plugin_module, tool_name)

        # 兼容异步本地工具执行
        if inspect.iscoroutinefunction(target_func):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                result = asyncio.get_event_loop().run_until_complete(target_func(**arguments))
            else:
                result = asyncio.run(target_func(**arguments))
        else:
            result = target_func(**arguments)

        if isinstance(result, str):
            return result
        else:
            return _format_response("text", str(result) if result is not None else "Success (No Output)")
    except Exception as e:
        return _format_response("error", f"❌ 调用本地工具时发生异常: {str(e)}")