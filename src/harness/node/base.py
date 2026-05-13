import os
import sys
import json
import importlib
import datetime
import asyncio
from typing import Dict, Any, List
from json_repair import repair_json
from src.harness.utils.tool_helper import execute_global_tool


def _format_result(result_data) -> str:
    """内部辅助函数：格式化工具返回结果，防范底层已打包好的JSON被重复打包"""
    if isinstance(result_data, str):
        try:
            # 如果底层 route.py 已经返回了带 timestamp/type 的标准字符串，直接透传
            parsed = json.loads(result_data)
            if "content" in parsed and "timestamp" in parsed:
                return result_data
            else:
                result_data = parsed
        except json.JSONDecodeError:
            pass  # 是普通纯字符串，继续往下走
            
    finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(result_data, dict):
        result_data["timestamp"] = finish_time
        return json.dumps(result_data, ensure_ascii=False)
        
    return json.dumps({"content": str(result_data), "timestamp": finish_time}, ensure_ascii=False)


class BaseNode:
    def __init__(self, node_id: str, config: dict):
        self.node_id = node_id
        self.config = config
        self.outputs: Dict[str, Any] = {}
        self.module_path = sys.modules[self.__module__].__file__
        self.node_dir = os.path.dirname(self.module_path)
        self.tools_dir = os.path.join(self.node_dir, "tools")
        self._local_tools_registry = None
        self._local_tools_schemas = None

    def get_local_tools(self):
        """动态扫描并加载当前节点 tools 目录下的工具"""
        if self._local_tools_registry is not None:
            return self._local_tools_registry, self._local_tools_schemas
        self._local_tools_registry = {}
        self._local_tools_schemas = []
        if not os.path.isdir(self.tools_dir):
            return self._local_tools_registry, self._local_tools_schemas
        try:
            for item in os.listdir(self.tools_dir):
                item_path = os.path.join(self.tools_dir, item)
                if os.path.isdir(item_path) and not item.startswith('_'):
                    meta_path = os.path.join(item_path, f"{item}.json")
                    if os.path.exists(meta_path):
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            schema = json.load(f)
                        tool_name = schema["function"]["name"]
                        self._local_tools_schemas.append(schema)
                        # 动态导入工具模块
                        package_path = self.__module__.rsplit('.', 1)[0]
                        tool_module_path = f"{package_path}.tools.{item}.tool"
                        module = importlib.import_module(tool_module_path)
                        self._local_tools_registry[tool_name] = module.Tool
        except Exception as e:
            print(f"❌ 加载节点本地工具失败: {e}")
        return self._local_tools_registry, self._local_tools_schemas

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: List[str], context: Any) -> Dict[str, Any]:
        """由子类实现的具体执行逻辑"""
        raise NotImplementedError

    def inject_force_push_to_messages(self, messages: List[Dict], force_push_msgs: List[str]) -> List[Dict]:
        """专供输入为 MessageList 类型的节点调用，拦截并注入人类指令"""
        if not force_push_msgs:
            return messages
        injected_messages = list(messages) if messages else []
        for msg in force_push_msgs:
            injected_messages.append({
                "role": "user",
                "content": f"[人类/系统强制干预] {msg}"
            })
        return injected_messages

    def execute_tool_calling(self, tool_calls: list, context: Any) -> List[dict]:
        """
        🌟 核心路由与分发逻辑
        先拦截 call_tool 并调用节点专属工具，否则将请求抛给全局工具调度器。
        """
        tool_messages = []
        for tc in tool_calls:
            original_tool_name = tc.function.name
            arguments_str = tc.function.arguments
            # 安全解析参数 (防御模型幻觉导致 JSON 破损)
            try:
                arguments = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                try:
                    arguments = repair_json(arguments_str, return_objects=True) or {}
                except Exception:
                    arguments = None

            if not isinstance(arguments, dict):
                tool_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": original_tool_name,
                    "content": "❌ 系统拦截：工具参数格式严重损坏，请检查 JSON 格式！"
                })
                continue
            # ==========================================
            # 分发逻辑
            # ==========================================
            if original_tool_name == "call_tool":
                action = arguments.get("action", "execute")
                local_registry, local_schemas = self.get_local_tools()
                
                # 🌟 核心：大模型主动请求工具列表
                if action == "list":
                    if not local_schemas:
                        msg = "当前节点暂未挂载任何拓展业务工具。"
                        self.log(context, "SYSTEM", f"📦 大模型查询工具列表，结果为空")
                    else:
                        # 把所有私有工具的 Schema 平铺成易读的文本返回给它
                        schema_list_str = json.dumps([s["function"] for s in local_schemas], ensure_ascii=False, indent=2)
                        msg = f"当前可用的拓展业务工具有以下几种，请参考其参数格式并在下一步调用：\n{schema_list_str}"
                        self.log(context, "SYSTEM", f"📦 吐出 {len(local_schemas)} 个拓展工具给大模型")
                    
                    final_content = _format_result({"available_tools": msg})

                # 🌟 正常执行工具
                elif action == "execute":
                    target_tool_name = arguments.get("tool_name")
                    target_arguments = arguments.get("tool_args", {})
                    
                    if not target_tool_name or target_tool_name not in local_registry:
                        available_names = list(local_registry.keys())
                        error_msg = f"❌ 找不到拓展工具 '{target_tool_name}'。请先使用 action='list' 查询可用的工具列表。"
                        self.log(context, "WARNING", error_msg)
                        final_content = _format_result({"error": error_msg})
                    else:
                        try:
                            args_str = ", ".join([f"{k}={repr(v)}" for k, v in target_arguments.items()])
                            self.log(context, "TOOL_CALL", f"🔧 [拓展工具] {target_tool_name}({args_str})")
                            
                            ToolClass = local_registry[target_tool_name]
                            tool_instance = ToolClass(context=context)
                            raw_result = tool_instance.execute(target_arguments)
                            final_content = _format_result(raw_result)
                            
                        except Exception as e:
                            target_schema = next((s for s in local_schemas if s["function"]["name"] == target_tool_name), {})
                            schema_text = json.dumps(target_schema.get("function", {}).get("parameters", {}), ensure_ascii=False, indent=2)
                            error_msg = f"❌ 参数错误或执行异常: {str(e)}\n请严格参考规范重新提供 tool_args:\n{schema_text}"
                            self.log(context, "ERROR", error_msg)
                            final_content = _format_result({"error": error_msg})

            else:
                # 👉 路由到全局基础工具 (task_done, bash, yield_to_human 等)
                try:
                    args_str = ", ".join([f"{k}={repr(v)}" for k, v in arguments.items()])
                    self.log(context, "TOOL_CALL", f"🔧 [全局核心工具] {original_tool_name}({args_str})")
                    
                    raw_result = execute_global_tool(original_tool_name, arguments, context=context)
                    final_content = _format_result(raw_result)
                    
                    self.log(context, "TOOL", f"📦 核心工具回传结果: {final_content}")
                except Exception as e:
                    error_msg = f"❌ 核心工具执行崩溃: {e}"
                    self.log(context, "ERROR", error_msg)
                    final_content = _format_result({"error": error_msg})
            # 装填并返回结果
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": original_tool_name,
                "content": final_content
            })

        return tool_messages

    def log(self, context: Any, log_type: str, content: str, node_id: str = None):
        """
        统一的节点日志打印接口
        :param context: Task 引擎实例
        :param log_type: 日志级别 (如 "SYSTEM", "ERROR", "WARNING", "THOUGHT")
        :param content: 日志正文
        :param node_id: 节点 ID (可选，默认使用自身 node_id)
        """
        nid = node_id or self.node_id

        if hasattr(context, "log_and_notify"):
            context.log_and_notify(log_type, content, nid)
        else:
            print(f"[{log_type}] (Node: {nid}) {content}")

    def check_running_state(self, context: Any) -> bool:
        """
        时刻检查自身状态。如果 Task 将我的状态改为了 ERROR/READY/WAITING 等，
        说明我被强行终止或挂起了，应立刻停止流转。
        """
        current_state = context.node_state.get(self.node_id)
        if current_state != "running":
            return False
        return True

    def consume_pending_messages(self, context: Any) -> list:
        """
        安全地消费属于我的待处理消息。
        只有节点主动调用该方法时，消息才会被取出，避免并发问题。
        """
        with context._lock:
            if self.node_id in context.pending_push_message:
                return context.pending_push_message.pop(self.node_id)
        return []
