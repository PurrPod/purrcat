import datetime
import importlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from dotenv import dotenv_values
from json_repair import repair_json
import yaml

from src.harness.enums import LogType
from src.harness.utils.tool_helper import execute_global_tool, extract_tool_calling


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

    return json.dumps(
        {"content": str(result_data), "timestamp": finish_time}, ensure_ascii=False
    )


class BaseNode:
    WORKFLOW_CORE_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "task_done",
                "description": "标记当前阶段任务完成。必须在此刻对成果进行全面总结。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "object",
                            "description": "对当前阶段的结构化总结数据（请严格按照系统要求的 JSON 键值对格式输出）"
                        }
                    },
                    "required": ["summary"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "yield_to_human",
                "description": "将控制权交还给人类，请求人工干预或确认",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "需要人类干预的原因"
                        }
                    },
                    "required": ["reason"]
                }
            }
        }
    ]

    def __init__(self, node_id: str, config: dict):
        self.node_id = node_id
        self.config = config
        self.outputs: Dict[str, Any] = {}
        self.module_path = sys.modules[self.__module__].__file__
        self.node_dir = os.path.dirname(self.module_path)
        self.tools_dir = os.path.join(self.node_dir, "tools")
        self._local_tools_registry = None
        self._local_tools_schemas = None
        self.metadata = self._load_metadata()
        # 🌟 新增 task_done_info 属性
        self.task_done_info = self.metadata.get("task_done_info", {})
        # 🌟 补上内存缓存
        self._checkpoint_cache = None

    def _load_metadata(self) -> dict:
        """
        动态扫描节点目录，按优先级解析配置文件到 self.metadata 中
        优先级：.env > metadata.yaml > metadata.yml > metadata.json
        """
        base_path = Path(self.node_dir)
        metadata = {}
        try:
            env_path = base_path / ".env"
            if env_path.exists():
                metadata.update(dotenv_values(env_path))
            yaml_path = base_path / "metadata.yaml"
            yml_path = base_path / "metadata.yml"
            valid_yaml = yaml_path if yaml_path.exists() else (yml_path if yml_path.exists() else None)
            if valid_yaml:
                with open(valid_yaml, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f)
                    if isinstance(yaml_data, dict):
                        metadata.update(yaml_data)
            json_path = base_path / "metadata.json"
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    if isinstance(json_data, dict):
                        metadata.update(json_data)
        except Exception as e:
            print(f"⚠️ [元数据加载警告] 节点 {self.__class__.__module__} 加载配置文件出错: {e}")
        return metadata

    # ==========================================
    # 🌟 新增：节点专有 Checkpoints 生命周期管理
    # ==========================================
    def _atomic_save(self, file_path: str, data: dict):
        """
        🌟 操作系统级别的原子写入，绝对不会因为断电/强杀导致 JSON 损坏
        """
        dir_name = os.path.dirname(file_path)
        os.makedirs(dir_name, exist_ok=True)

        tmp_path = os.path.join(dir_name, f".{uuid.uuid4().hex}.tmp")

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(tmp_path, file_path)

        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            self.log(None, "ERROR", f"❌ 节点原子落盘失败: {e}")

    def save_checkpoints(self, context: Any, data: dict):
        """实时更新缓存，并原子落盘"""
        self._checkpoint_cache = data # 🌟 写入时同步更新内存
        if not context or not hasattr(context, "checkpoint_dir"):
            return
        file_path = os.path.join(context.checkpoint_dir, "nodes_checkpoints", f"{self.node_id}.json")
        self._atomic_save(file_path, data)

    def update_checkpoints(self, context: Any, partial_outputs: dict = None, partial_inputs: dict = None):
        """增量保存（配合原子写，极其安全）"""
        if not context or not hasattr(context, "checkpoint_dir"):
            return

        existing = self.load_checkpoints(context) or {"inputs": {}, "outputs": {}}

        if partial_inputs:
            existing.setdefault("inputs", {}).update(partial_inputs)
        if partial_outputs:
            existing.setdefault("outputs", {}).update(partial_outputs)

        self.save_checkpoints(context, existing)

    def load_checkpoints(self, context: Any) -> dict:
        """优先读内存，内存没有再读盘"""
        if self._checkpoint_cache is not None:
            return self._checkpoint_cache

        if not context or not hasattr(context, "checkpoint_dir"):
            return {}

        file_path = os.path.join(context.checkpoint_dir, "nodes_checkpoints", f"{self.node_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self._checkpoint_cache = json.load(f)
                    return self._checkpoint_cache
            except Exception as e:
                self.log(context, "WARNING", f"⚠️ 读取存档损坏，按空数据处理: {e}")

        self._checkpoint_cache = {"inputs": {}, "outputs": {}}
        return self._checkpoint_cache

    def reset(self, context: Any, clear_backup: bool = True):
        """重置节点：清空内存的 outputs。根据参数决定是否物理删除 Checkpoint"""
        self.outputs = {}
        if clear_backup and context and hasattr(context, "checkpoint_dir"):
            file_path = os.path.join(context.checkpoint_dir, "nodes_checkpoints", f"{self.node_id}.json")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    self.log(context, "ERROR", f"清理 Checkpoint 失败: {e}")

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
                if os.path.isdir(item_path) and not item.startswith("_"):
                    meta_path = os.path.join(item_path, f"{item}.json")
                    if os.path.exists(meta_path):
                        with open(meta_path, "r", encoding="utf-8") as f:
                            schema = json.load(f)
                        tool_name = schema["function"]["name"]
                        self._local_tools_schemas.append(schema)
                        # 动态导入工具模块
                        package_path = self.__module__.rsplit(".", 1)[0]
                        tool_module_path = f"{package_path}.tools.{item}.tool"
                        module = importlib.import_module(tool_module_path)
                        self._local_tools_registry[tool_name] = module.Tool
        except Exception as e:
            print(f"❌ 加载节点本地工具失败: {e}")
        return self._local_tools_registry, self._local_tools_schemas

    def get_all_tools(self) -> List[dict]:
        """获取当前节点可用的所有大模型工具（系统基础工具 + 工作流原语）"""
        from src.harness.utils.tool_helper import get_system_schema
        tools = get_system_schema()
        tools.extend(self.WORKFLOW_CORE_TOOLS)
        return tools

    async def execute(
        self, inputs: Dict[str, Any], force_push_msgs: List[str], context: Any
    ) -> Dict[str, Any]:
        """由子类实现的具体执行逻辑"""
        raise NotImplementedError

    def inject_force_push_to_messages(
        self, messages: List[Dict], force_push_msgs: List[str]
    ) -> List[Dict]:
        """专供输入为 MessageList 类型的节点调用，拦截并注入人类指令"""
        if not force_push_msgs:
            return messages
        injected_messages = list(messages) if messages else []
        for msg in force_push_msgs:
            injected_messages.append(
                {"role": "user", "content": f"[人类/系统强制干预] {msg}"}
            )
        return injected_messages

    async def execute_tool_calling(self, response: Any, context: Any) -> tuple[list, bool, bool]:
        """
        统一处理普通工具、拓展工具与工作流原语。
        直接提取 OpenAI SDK Response 内的 Tool Calls。
        返回: (tool_messages, is_task_done, is_yield)
        """
        # 1. 提取 response 中的所有工具调用
        tool_calls = extract_tool_calling(response)
        
        tool_messages = []
        is_task_done = False
        is_yield = False

        for tc in tool_calls:
            original_tool_name = tc.function.name
            arguments_str = tc.function.arguments

            # 解析参数
            try:
                arguments = json.loads(arguments_str) if arguments_str else {}
            except json.JSONDecodeError:
                arguments = {}

            final_content = ""

            # ==========================================
            # 分发逻辑：工作流原语 (Workflow Primitives)
            # ==========================================
            if original_tool_name == "task_done":
                summary = arguments.get("summary", {})
                if not isinstance(summary, dict):
                    summary = {"raw": str(summary)}

                # 🌟 强校验逻辑：对照 self.task_done_info 检查必填项
                if self.task_done_info:
                    missing_keys = []
                    for req_key, req_desc in self.task_done_info.items():
                        if req_key not in summary:
                            missing_keys.append(f"'{req_key}' ({req_desc})")

                    if missing_keys:
                        # ⚠️ 校验失败：打回给大模型
                        error_msg = f"❌ [格式错误] 你尝试完成任务，但 summary 缺失了系统强制要求的关键信息：{', '.join(missing_keys)}。"
                        self.log(context, "WARNING", f"⚠️ [任务完结被拒] 大模型缺少必填参数: {missing_keys}")

                        # 把错误信息和期望的 schema 喂给大模型，让它知道错在哪
                        final_content = _format_result({
                            "error": error_msg,
                            "instruction": "请重新调用 task_done 工具，并确保 summary 参数严格包含上述提到的所有键值对！",
                            "required_schema": self.task_done_info
                        })
                    else:
                        # ✅ 校验完美通过
                        if context:
                            context.result = True
                        self.log(context, "SYSTEM", f"✅ [任务完结校验通过] 输出合规: {json.dumps(summary, ensure_ascii=False)}")
                        final_content = _format_result({"status": "success", "summary": summary})
                        is_task_done = True
                else:
                    # 节点本身没配置强校验，直接放行
                    if context:
                        context.result = True
                    self.log(context, "SYSTEM", f"✅ [任务完结信号] 大模型总结: {json.dumps(summary, ensure_ascii=False)}")
                    final_content = _format_result({"status": "success", "summary": summary})
                    is_task_done = True

            elif original_tool_name == "yield_to_human":
                reason = arguments.get("reason", "需要人工干预")
                self.log(context, "SYSTEM", f"⏸️ [请求干预] 理由: {reason}")
                context.node_state[self.node_id] = NodeState.WAITING
                final_content = _format_result({"status": "suspended", "message": "已挂起，等待人类注入指令"})
                is_yield = True

            # ==========================================
            # 分发逻辑：业务层级与全局工具
            # ==========================================
            elif original_tool_name == "call_tool":
                action = arguments.get("action", "execute")
                local_registry, local_schemas = self.get_local_tools()

                # 🌟 核心：大模型主动请求工具列表
                if action == "list":
                    if not local_schemas:
                        msg = "当前节点暂未挂载任何拓展业务工具。"
                        self.log(
                            context, LogType.SYSTEM, "📦 [查询工具] 当前无可用拓展工具"
                        )
                    else:
                        schema_list_str = json.dumps(
                            [s["function"] for s in local_schemas],
                            ensure_ascii=False,
                            indent=2,
                        )
                        msg = f"当前可用的拓展业务工具有以下几种，请参考其参数格式并在下一步调用：\n{schema_list_str}"
                        self.log(
                            context,
                            LogType.SYSTEM,
                            f"📦 [查询工具] 吐出 {len(local_schemas)} 个拓展工具",
                        )

                    final_content = _format_result({"available_tools": msg})

                # 🌟 正常执行工具
                elif action == "execute":
                    target_tool_name = arguments.get("tool_name")
                    target_arguments = arguments.get("tool_args", {})

                    if not target_tool_name or target_tool_name not in local_registry:
                        error_msg = f"⚠️ [工具缺失] 未找到 '{target_tool_name}'"
                        self.log(context, LogType.WARNING, error_msg)
                        final_content = _format_result({"error": error_msg})
                    else:
                        try:
                            args_str = ", ".join(
                                [f"{k}={repr(v)}" for k, v in target_arguments.items()]
                            )
                            if len(args_str) > 100:
                                args_str = args_str[:97] + "..."
                            self.log(
                                context,
                                LogType.TOOL_CALL,
                                f"🔧 [拓展工具] {target_tool_name}({args_str})",
                            )

                            ToolClass = local_registry[target_tool_name]
                            tool_instance = ToolClass(context=context)
                            raw_result = tool_instance.execute(target_arguments)
                            final_content = _format_result(raw_result)

                        except Exception as e:
                            error_msg = (
                                f"❌ [工具异常] {target_tool_name} 执行失败: {str(e)}"
                            )
                            self.log(context, LogType.ERROR, error_msg)
                            final_content = _format_result({"error": error_msg})

            else:
                # 抛给底层的 search / bash 等
                try:
                    args_str = ", ".join(
                        [f"{k}={repr(v)}" for k, v in arguments.items()]
                    )
                    if len(args_str) > 100:
                        args_str = args_str[:97] + "..."
                    self.log(
                        context,
                        LogType.TOOL_CALL,
                        f"🔧 [全局工具] {original_tool_name}({args_str})",
                    )

                    raw_result = execute_global_tool(
                        original_tool_name, arguments, context=context
                    )
                    final_content = _format_result(raw_result)

                    result_preview = str(final_content)[:50].replace("\n", " ")
                    self.log(
                        context,
                        LogType.TOOL,
                        f"📦 [工具返回] {original_tool_name} -> {result_preview}...",
                    )
                except Exception as e:
                    error_msg = f"❌ [工具崩溃] {original_tool_name}: {e}"
                    self.log(context, LogType.ERROR, error_msg)
                    final_content = _format_result({"error": error_msg})

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": original_tool_name,
                "content": final_content,
            })

        return tool_messages, is_task_done, is_yield

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
        时刻检查自身状态。如果 Task 将我的状态改为了 ERROR/KILLED/READY 等，
        说明我被强行终止或挂起了，应立刻停止流转。
        """
        current_state = context.node_state.get(self.node_id)
        if current_state not in ["running", "waiting"]:
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
