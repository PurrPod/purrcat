import asyncio
import json
import os
from typing import Any, Dict, List

from src.harness.enums import LogType
from src.harness.node.base import BaseNode, _format_result
from src.harness.utils.tool_helper import (
    execute_global_tool,
    extract_tool_calling,
)
from src.tool.utils.route import extract_tool_message_content
from src.utils._fs import read_jsonl

from json_repair import repair_json


def _loads_json_tolerant(s: str):
    """多重容错解析：标准解析 -> 容忍裸控制字符 -> json_repair 修复器（主 Agent 同款）"""
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(s, strict=False)
    except json.JSONDecodeError:
        pass
    try:
        return repair_json(s, return_objects=True)
    except Exception:
        return None


def _parse_tool_arguments(raw) -> tuple:
    """
    🌟 解析模型工具参数，返回 (arguments_dict, error_message_or_None)
    与主 Agent (src/agent/agent.py) 的容错能力对齐，并额外处理：
    - 部分网关直接返回已解析的 dict
    - 双重编码：模型把整个 JSON 当字符串输出（"'{\\"summary\\": ...}'"）
    - 多余包装：模型把参数包在 {"arguments": ...} 下（值可能是 dict 或再编码的字符串）
    """
    if isinstance(raw, dict):
        return raw, None

    if not raw or not isinstance(raw, str):
        return {}, None

    parsed = _loads_json_tolerant(raw)

    # 双重编码：解析结果是字符串，说明模型把 JSON 整体加了引号，再解一层
    if isinstance(parsed, str):
        inner = _loads_json_tolerant(parsed)
        if isinstance(inner, dict):
            parsed = inner

    if not isinstance(parsed, dict):
        return {}, (
            f"解析结果不是 JSON 对象 ({type(parsed).__name__}) | 原文片段(前200字符): {raw[:200]}"
        )

    # 多余包装：唯一的 "arguments" 键（值为 dict 或字符串化的 JSON）一律解包，最多剥三层
    for _ in range(3):
        if set(parsed.keys()) == {"arguments"}:
            inner = parsed["arguments"]
            if isinstance(inner, dict):
                parsed = inner
            elif isinstance(inner, str):
                inner_parsed = _loads_json_tolerant(inner)
                if isinstance(inner_parsed, dict):
                    parsed = inner_parsed
                else:
                    break
            else:
                break
        else:
            break

    return parsed, None


class AgentNode(BaseNode):
    """
    专门处理 LLM 对话、工具调用、大循环控制以及人类干预的节点基类

    🌟 新架构特性：节点自治数据管理
    - 每个节点拥有自己的专属文件夹：nodes/node_id/
    - 对话历史使用 JSONL 格式追加写入（memory.jsonl）
    - 大文件存放在 artifacts/ 子目录
    """

    # 标识该节点支持接受外部指令注入，用于 Dashboard 过滤
    can_inject = True

    def get_memory_file_path(self, context) -> str:
        """获取该节点的记忆文件路径：nodes/node_id/memory.jsonl"""
        node_dir = os.path.join(context.checkpoint_dir, "nodes", self.node_id)
        os.makedirs(node_dir, exist_ok=True)
        return os.path.join(node_dir, "memory.jsonl")

    def _sync_dump_memory(self, context, messages: List[Dict]):
        """实时写盘小助手，保证执行期间前端能实时探班气泡"""
        node_dir = os.path.join(context.checkpoint_dir, "nodes", self.node_id)
        os.makedirs(node_dir, exist_ok=True)
        # 写到 live_memory.json，与 API 接口的优先级 2 完美对齐
        out_file = os.path.join(node_dir, "live_memory.json")
        try:
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False)
        except Exception:
            pass

    def get_artifacts_dir(self, context) -> str:
        """获取该节点的大文件存放目录：nodes/node_id/artifacts/"""
        artifacts_dir = os.path.join(
            context.checkpoint_dir, "nodes", self.node_id, "artifacts"
        )
        os.makedirs(artifacts_dir, exist_ok=True)
        return artifacts_dir

    def load_memory_from_file(self, context) -> List[Dict]:
        """从 JSONL 文件加载对话历史（追加写入格式）"""
        memory_path = self.get_memory_file_path(context)
        if not os.path.exists(memory_path):
            return []

        def _warn_broken_line(line: str):
            # 并发追加可能产生残行，跳过而不是让节点每次重启都崩溃
            self.log(
                context,
                "WARNING",
                f"⚠️ [记忆残行] 跳过无法解析的行: {line[:80]}",
            )

        try:
            return read_jsonl(memory_path, on_error=_warn_broken_line)
        except Exception as e:
            self.log(context, "WARNING", f"⚠️ [记忆加载失败] {e}")
            return []

    def append_memory_to_file(self, context, new_messages: List[Dict]):
        """追加写入新消息到 JSONL 文件（O(1) 复杂度）"""
        memory_path = self.get_memory_file_path(context)

        try:
            with open(memory_path, "a", encoding="utf-8") as f:
                for msg in new_messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        except Exception as e:
            self.log(context, "WARNING", f"⚠️ [记忆追加失败] {e}")

    def clear_memory_file(self, context):
        """清空节点的记忆文件（用于重置）"""
        memory_path = self.get_memory_file_path(context)
        if os.path.exists(memory_path):
            os.remove(memory_path)

    def migrate_old_memory(self, old_memory: dict, context):
        """将旧格式的 node_memory 迁移到新的 JSONL 格式"""
        messages = old_memory.get("messages", [])
        if messages:
            self.append_memory_to_file(context, messages)

    async def run_tool_calls(self, response: Any, context: Any) -> list:
        """统一处理普通工具与拓展工具（不含任务完结/挂起原语）。

        与主 Agent 对齐的参数容错解析；工具执行放入独立线程池，避免异步跨线程
        子进程死锁；vision 模式下工具图片直注对话。
        """
        tool_calls = extract_tool_calling(response)
        tool_messages = []

        for tc in tool_calls:
            original_tool_name = tc.function.name

            arguments, args_parse_error = _parse_tool_arguments(tc.function.arguments)

            # 🌟 解析失败必须把真实原因告知模型，而不是伪装成"缺字段"误导它反复重试
            if args_parse_error:
                self.log(
                    context,
                    "ERROR",
                    f"❌ [参数JSON解析失败] {original_tool_name}: {args_parse_error}",
                )
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": original_tool_name,
                        "content": _format_result(
                            {
                                "error": f"❌ 工具 {original_tool_name} 的 arguments 无法解析为 JSON 对象：{args_parse_error}",
                                "instruction": "请重新调用该工具：arguments 必须是单个合法的 JSON 对象（不要输出字符串包裹的 JSON，不要额外包一层 arguments 键）；字符串内的换行写成 \\n；若参数过长被截断，请精简参数内容后重试。",
                            }
                        ),
                    }
                )
                continue

            self.log(context, "SYSTEM", f"  🔧 [执行工具] {original_tool_name}")
            args_preview = json.dumps(arguments, ensure_ascii=False)[:100]
            self.log(
                context,
                "SYSTEM",
                f"     📥 参数: {args_preview}{'...' if len(json.dumps(arguments, ensure_ascii=False)) > 100 else ''}",
            )

            final_content = ""

            try:
                self.log(
                    context,
                    LogType.TOOL_CALL,
                    f"🔧 [全局工具] {original_tool_name}",
                )

                # 🌟 核心：把当前 Task 的 task_id 注入进去充当 session_id，
                # 让 Bash 工具在后台运行时隔离在独立沙盒 Session 中
                arguments["session_id"] = context.task_id
                arguments["_is_sub_branch"] = True  # 声明继承子分支越权防护特性

                # 🟢 使用 to_thread 将工具执行放入独立线程池，避免异步跨线程子进程死锁
                raw_result = await asyncio.to_thread(
                    execute_global_tool,
                    original_tool_name,
                    arguments,
                    context=context,
                )

                # 🌟 vision 直注结果：tool 消息 content 直接用 OpenAI
                # 多模态 parts 列表（含 image_url），跳过 _format_result
                vision_parts = extract_tool_message_content(raw_result)
                if isinstance(vision_parts, list):
                    final_content = vision_parts
                else:
                    final_content = _format_result(raw_result)
                self.log(
                    context,
                    LogType.TOOL,
                    f"📦 [工具返回] {original_tool_name} -> {str(final_content)[:50]}...",
                )
            except Exception as e:
                final_content = _format_result(
                    {"error": f"❌ [工具崩溃] {original_tool_name}: {e}"}
                )

            tool_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": original_tool_name,
                    "content": final_content,
                }
            )

            # 🌟 与主循环对齐：Memo add 后把 memo_data 追加进全局常驻缓存 memo.json
            # （滚动保留最近 30 条），保证 memo_injection / search 无 query 能取到最新缓存
            if original_tool_name == "Memo" and arguments.get("action") == "add":
                memo_data = arguments.get("memo_data")
                if isinstance(memo_data, dict) and memo_data:
                    self._update_global_memo(memo_data)

        return tool_messages

    @staticmethod
    def _update_global_memo(memo_data: dict):
        """把单条记忆追加到全局常驻缓存 memo.json，滚动保留最近 30 条（对齐主循环）。"""
        from src.agent.session_store import SessionStore

        memo = SessionStore.load_global_memo() or []
        memo.append(memo_data)
        if len(memo) > 30:
            memo = memo[-30:]
        SessionStore.save_global_memo(memo)

    @staticmethod
    def _sanitize_messages(messages: List[Dict]) -> List[Dict]:
        """
        🌟 历史消毒：修复崩溃/强杀留下的悬空 tool_calls
        assistant 发起了工具调用但没有配对的 tool 响应时，直接回放会导致：
        - 严格网关直接 400
        - 模型协议混乱，后续输出畸形参数（双重编码/多余包装）
        参照项目既有经验：被中断的工具调用必须补一条合成 tool 消息。
        """
        if not messages:
            return messages

        result = []
        pending = []  # 尚未等到响应的 (tool_call_id, name)

        def _flush_pending():
            for tc_id, name in pending:
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "name": name or "unknown",
                        "content": "[系统提示] 该工具调用因进程中断未留下结果，请忽略并继续当前任务。",
                    }
                )
            pending.clear()

        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                _flush_pending()
                pending = [
                    (t.get("id"), (t.get("function") or {}).get("name", ""))
                    for t in msg["tool_calls"]
                ]
                result.append(msg)
            elif msg.get("role") == "tool":
                pending = [p for p in pending if p[0] != msg.get("tool_call_id")]
                result.append(msg)
            else:
                _flush_pending()
                result.append(msg)

        _flush_pending()
        return result
