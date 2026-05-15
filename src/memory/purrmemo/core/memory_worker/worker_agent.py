# purrmemo/core/memory_worker/worker_agent.py

import os
import json
import time
import shutil
import hashlib
from datetime import datetime
from src.utils.config import get_memory_config, MEMORY_PENDING_DIR, MEMORY_DIR

from ..storage.event_engine import EventEngine
from ..storage.vector_engine import VectorEngine
from ..storage.graph_engine import GraphEngine

from .tools import rag_search, add_relation, reinforce_relation, weaken_relation
from src.model import AgentModel
from ..search_tool import start_forgetfulness_scheduler

ARCHIVED_DIR = os.path.join(MEMORY_DIR, "buffer", "archived")
ERROR_DIR = os.path.join(MEMORY_DIR, "buffer", "error")

os.makedirs(MEMORY_PENDING_DIR, exist_ok=True)
os.makedirs(ARCHIVED_DIR, exist_ok=True)
os.makedirs(ERROR_DIR, exist_ok=True)


class MemoryAgent:
    def __init__(self):
        self.history = []
        self.event_engine = EventEngine()

        try:
            self.vector_engine = VectorEngine()
        except Exception:
            self.vector_engine = None
            print("VectorEngine 不可用，将在无向量搜索模式下运行")

        try:
            self.graph_engine = GraphEngine()
            start_forgetfulness_scheduler(self.graph_engine, interval_hours=24)
        except Exception:
            self.graph_engine = None
            print("GraphEngine 不可用，将无法处理图谱相关操作")

    def _run_llm_step(self, cognition_data: list):
        """
        批量处理认知信息：一次 LLM 调用 + 完整 reAct 会话历史

        Args:
            cognition_data: 认知条目列表，如 ["用户喜欢吃苹果", "用户讨厌香蕉"]
        """
        if not cognition_data:
            return

        model = AgentModel(task_id="memory_worker")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "rag_search",
                    "description": "批量检索知识库中是否存在相关节点",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity_keywords": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "关键词列表，从认知信息中提取的核心实体",
                            }
                        },
                        "required": ["entity_keywords"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "add_relation",
                    "description": "新增三元组关系",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_node": {"type": "string"},
                            "relation": {"type": "string"},
                            "target_node": {"type": "string"},
                            "source_event_id": {"type": "string", "default": "unknown"},
                        },
                        "required": ["source_node", "relation", "target_node"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reinforce_relation",
                    "description": "强化已有关系",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_node": {"type": "string"},
                            "relation": {"type": "string"},
                            "target_node": {"type": "string"},
                        },
                        "required": ["source_node", "relation", "target_node"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "weaken_relation",
                    "description": "削弱已有关系（通常需要紧接着 add_relation）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "source_node": {"type": "string"},
                            "relation": {"type": "string"},
                            "target_node": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "source_node",
                            "relation",
                            "target_node",
                            "reason",
                        ],
                    },
                },
            },
        ]

        tool_map = {
            "rag_search": rag_search,
            "add_relation": add_relation,
            "reinforce_relation": reinforce_relation,
            "weaken_relation": weaken_relation,
        }

        system_msg = {
            "role": "system",
            "content": "你是一个严谨的知识图谱构建助手。收到一批认知条目，你需要：\n1. 先用 rag_search 批量检索关键词\n2. 根据检索结果调用 add_relation/reinforce_relation/weaken_relation\n3. 所有条目处理完毕后回复'完成'",
        }

        user_content = "【待处理的认知条目】\n"
        for i, item in enumerate(cognition_data, 1):
            user_content += f"{i}. {item}\n"
        user_content += "\n请开始处理：先用 rag_search 检索，然后逐条写入图谱。"

        messages = [system_msg, {"role": "user", "content": user_content}]

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

                if tool_name in [
                    "add_relation",
                    "reinforce_relation",
                    "weaken_relation",
                ]:
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

    def _process_file(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            error_path = os.path.join(ERROR_DIR, os.path.basename(file_path))
            shutil.move(file_path, error_path)
            return False

        try:
            timestamp = data.get("timestamp", datetime.now().isoformat())

            # 预定义变量，防止未定义引用
            event_id = None
            cognition = data.get("cognition", [])
            user_profile = data.get("user_profile", [])

            # 1. 处理 Events (事件库 + 向量库双写)
            events = data.get("events", [])
            for event in events:
                event_content = (
                    event.get("event", "") if isinstance(event, dict) else event
                )
                event_time = (
                    event.get("time", timestamp)
                    if isinstance(event, dict)
                    else timestamp
                )
                event_id = f"evt_{hashlib.md5(event_content.encode()).hexdigest()}"

                # A. 存入 SQLite (纯文本存入即可)
                self.event_engine.insert_event(
                    event_id=event_id, content=event_content, timestamp=event_time
                )
                # B. 存入 ChromaDB (由它全权负责向量)
                if self.vector_engine:
                    self.vector_engine.insert_event_vector(
                        event_id, event_content, event_time
                    )

            # 2. 处理 work_exp 和 user_profile (存入向量库的经验池)
            experiences = data.get("work_exp", []) + user_profile
            if self.vector_engine and experiences:
                for exp_text in experiences:
                    exp_id = f"exp_{hashlib.md5(exp_text.encode()).hexdigest()}"
                    self.vector_engine.insert_experience(
                        exp_id=exp_id, content=exp_text, timestamp=timestamp
                    )

            # 3. 处理 user_profile 和 cognition (抛给大模型提取图谱关系)
            graph_materials = cognition + user_profile
            if graph_materials and self.graph_engine:
                self._run_llm_step(graph_materials)
                self.graph_engine.save_graph()

            # 3. 归档日志记录
            archive_path = os.path.join(ARCHIVED_DIR, os.path.basename(file_path))
            shutil.move(file_path, archive_path)

            self.history.append(
                {
                    "event_id": event_id,
                    "file": os.path.basename(file_path),
                    "processed_at": datetime.now().isoformat(),
                    "events_count": len(events),
                    "has_graph_materials": bool(cognition or user_profile),
                }
            )
            return True
        except Exception as e:
            print(f"❌ Worker 处理文件失败: {e}")
            return False

    def run(self):
        polling_interval = (
            get_memory_config().get("memory_agent", {}).get("polling_interval", 5)
        )
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
