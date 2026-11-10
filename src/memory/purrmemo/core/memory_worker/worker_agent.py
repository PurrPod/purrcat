# purrmemo/core/memory_worker/worker_agent.py

import json
import os
import shutil
import time

from src.utils.config import MEMORY_DIR, MEMORY_PENDING_DIR
from src.memory.config import MEMORY_AGENT_POLLING_INTERVAL

from ..clock import now_iso
from ..ids import event_id_for, experience_id_for
from ..search_tool import start_forgetfulness_scheduler
from ..storage.event_engine import EventEngine
from ..storage.graph_engine import GraphEngine
from ..storage.vector_engine import VectorEngine
from .payload import iter_event_records, parse_pending_payload
from .prompts import build_messages
from .schema import MEMORY_WORKER_TOOL_SCHEMAS, WRITE_TOOL_NAMES
from .tools import add_relation, rag_search, reinforce_relation, weaken_relation

ARCHIVED_DIR = os.path.join(MEMORY_DIR, "buffer", "archived")
ERROR_DIR = os.path.join(MEMORY_DIR, "buffer", "error")

os.makedirs(MEMORY_PENDING_DIR, exist_ok=True)
os.makedirs(ARCHIVED_DIR, exist_ok=True)
os.makedirs(ERROR_DIR, exist_ok=True)


class MemoryAgent:
    def __init__(
        self,
        event_engine=None,
        vector_engine=None,
        graph_engine=None,
        start_scheduler=True,
        model_factory=None,
    ):
        self.history = []
        self.event_engine = event_engine if event_engine is not None else EventEngine()
        self._model_factory = model_factory

        if vector_engine is not None:
            self.vector_engine = vector_engine
        else:
            self.vector_engine = None
            try:
                self.vector_engine = VectorEngine()
            except Exception:
                print("VectorEngine 不可用，将在无向量搜索模式下运行")

        if graph_engine is not None:
            self.graph_engine = graph_engine
            try:
                if start_scheduler:
                    start_forgetfulness_scheduler(self.graph_engine, interval_hours=24)
            except Exception:
                self.graph_engine = None
                print("GraphEngine 不可用，将无法处理图谱相关操作")
        else:
            self.graph_engine = None
            try:
                self.graph_engine = GraphEngine()
                if start_scheduler:
                    start_forgetfulness_scheduler(self.graph_engine, interval_hours=24)
            except Exception:
                self.graph_engine = None
                print("GraphEngine 不可用，将无法处理图谱相关操作")

    def _create_model(self):
        """构造记忆工人的模型；未注入工厂时保持原有的懒加载行为。"""
        if self._model_factory is not None:
            return self._model_factory()
        from src.model import AgentModel

        return AgentModel(task_id="memory_worker")

    def _run_llm_step(self, cognition_data: list):
        """
        批量处理认知信息：一次 LLM 调用 + 完整 reAct 会话历史

        Args:
            cognition_data: 认知条目列表，如 ["用户喜欢吃苹果", "用户讨厌香蕉"]
        """
        if not cognition_data:
            return

        model = self._create_model()

        tools = MEMORY_WORKER_TOOL_SCHEMAS

        tool_map = {
            "rag_search": rag_search,
            "add_relation": add_relation,
            "reinforce_relation": reinforce_relation,
            "weaken_relation": weaken_relation,
        }

        messages = build_messages(cognition_data)

        max_turns = 50
        write_count = 0

        for turn in range(max_turns):
            response = model.chat(
                messages=messages,
                tools=tools,
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

            if not msg_resp.tool_calls:
                break

            tool_results = []
            for tc in msg_resp.tool_calls:
                tool_name = tc.function.name

                if tool_name in WRITE_TOOL_NAMES:
                    write_count += 1

                try:
                    tool_args = json.loads(tc.function.arguments)
                    tool_result = tool_map[tool_name](**tool_args)
                except Exception as e:
                    tool_result = f"执行失败: {str(e)}"
                    print(f"{tool_name} 失败: {e}")

                tool_results.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": tool_result}
                )
                messages.append(tool_results[-1])

    def _vector_ready(self) -> bool:
        """嵌入模型是否已就绪（下载完成且可加载）。"""
        if self.vector_engine is None:
            return False
        try:
            self.vector_engine.embedding_model  # 触发懒加载
            return True
        except Exception:
            return False

    def _process_file(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            error_path = os.path.join(ERROR_DIR, os.path.basename(file_path))
            shutil.move(file_path, error_path)
            return False

        try:
            memo = parse_pending_payload(data)
            timestamp = memo.timestamp
            cognition = memo.cognition
            user_profile = memo.user_profile
            work_exp = memo.work_exp
            events = memo.events

            event_id = None

            # 🌟 嵌入模型未就绪（首启仍在下载 / 直连 HF 下载失败）时，向量写入必然失败。
            # 此时不要继续处理并归档，文件留在 pending 等模型就绪后自动重试，
            # 否则工作经验会被静默丢弃 —— 表现为"别的记忆库都满了，vector 经验库一直为空"
            if (
                self.vector_engine
                and (events or work_exp or user_profile)
                and not self._vector_ready()
            ):
                print(
                    f"⏳ [Worker] 嵌入模型未就绪，"
                    f"{os.path.basename(file_path)} 留在 pending 待重试"
                )
                return False

            # 1. 处理 Events (事件库 + 向量库双写)
            for event_content, event_time in iter_event_records(events, timestamp):
                event_id = event_id_for(event_content)

                self.event_engine.insert_event(
                    event_id=event_id, content=event_content, timestamp=event_time
                )
                if self.vector_engine:
                    self.vector_engine.insert_event_vector(
                        event_id, event_content, event_time
                    )

            # 2. 处理 work_exp 和 user_profile (存入向量库的经验池)
            experiences = work_exp + user_profile
            if self.vector_engine and experiences:
                for exp_text in experiences:
                    exp_id = experience_id_for(exp_text)
                    self.vector_engine.insert_experience(
                        exp_id=exp_id, content=exp_text, timestamp=timestamp
                    )

            # ================= 新增解耦逻辑 =================
            # 触发 MEMORY.md 的文本归档更新 (由于是阻塞调用，文件会排队更新，非常安全)
            if work_exp or user_profile:
                try:
                    from src.tool.memo.memo_operations import _smart_update_memory_md

                    print("⏳ [Worker] 检测到经验更新，正在后台重建 MEMORY.md ...")
                    _smart_update_memory_md(work_exp, user_profile)
                except Exception as e:
                    print(f"❌ [Worker] 重建 MEMORY.md 异常: {e}")
            # ===============================================

            # 3. 处理 cognition 和 user_profile (抛给大模型提取图谱关系)
            graph_materials = cognition + user_profile
            if graph_materials and self.graph_engine:
                self._run_llm_step(graph_materials)
                self.graph_engine.save_graph()

            # 4. 归档日志记录
            archive_path = os.path.join(ARCHIVED_DIR, os.path.basename(file_path))
            shutil.move(file_path, archive_path)

            self.history.append(
                {
                    "event_id": event_id,
                    "file": os.path.basename(file_path),
                    "processed_at": now_iso(),
                    "events_count": len(events),
                    "has_graph_materials": bool(cognition or user_profile),
                }
            )
            return True
        except Exception as e:
            print(f"❌ Worker 处理文件失败: {e}")
            return False

    def run(self):
        polling_interval = MEMORY_AGENT_POLLING_INTERVAL
        while True:
            try:
                files = [
                    f
                    for f in os.listdir(MEMORY_PENDING_DIR)
                    if f.startswith("memory_") and f.endswith(".json")
                ]
                for file_name in files:
                    file_path = os.path.join(MEMORY_PENDING_DIR, file_name)
                    if os.path.exists(file_path):
                        self._process_file(file_path)
                time.sleep(polling_interval)
            except Exception:
                time.sleep(polling_interval)
