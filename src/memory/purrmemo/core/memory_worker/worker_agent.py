# purrmemo/core/memory_worker/worker_agent.py

import os
import json
import time
import shutil
import hashlib
import threading
from datetime import datetime
from ..config import MEMORY_AGENT_CONFIG
from src.utils.config import MEMORY_PENDING_DIR, MEMORY_DIR
PENDING_DIR = MEMORY_PENDING_DIR
ARCHIVED_DIR = os.path.join(MEMORY_DIR, "buffer", "archived")
ERROR_DIR = os.path.join(MEMORY_DIR, "buffer", "error")

# 确保目录存在
os.makedirs(PENDING_DIR, exist_ok=True)
os.makedirs(ARCHIVED_DIR, exist_ok=True)
os.makedirs(ERROR_DIR, exist_ok=True)
from ..storage.event_engine import EventEngine
from ...visualize_graph import GraphVisualizer

# 尝试导入向量引擎和图谱引擎，处理依赖问题
try:
    from ..storage.vector_engine import VectorEngine
    vector_engine_available = True
except ImportError as e:
    print(f"VectorEngine 导入失败: {e}")
    vector_engine_available = False

try:
    from ..storage.graph_engine import GraphEngine
    graph_engine_available = True
except ImportError as e:
    print(f"GraphEngine 导入失败: {e}")
    graph_engine_available = False

from .prompt import MEMORY_WORKER_PROMPT
from .tools import rag_search, add_relation, reinforce_relation, weaken_relation, MEMORY_WORKER_TOOLS
from src.model import AgentModel
from ..search_tool import start_forgetfulness_scheduler

class MemoryAgent:
    def __init__(self):
        self.history = []
        self.event_engine = EventEngine()

        if vector_engine_available:
            self.vector_engine = VectorEngine()
        else:
            self.vector_engine = None
            print("VectorEngine 不可用，将在无向量搜索模式下运行")

        if graph_engine_available:
            self.graph_engine = GraphEngine()
            start_forgetfulness_scheduler(self.graph_engine, interval_hours=24)
        else:
            self.graph_engine = None
            print("GraphEngine 不可用，将无法处理图谱相关操作")
        
        self._file_locks = {}
        self._locks_mutex = threading.Lock()

    def _extract_entities_from_cognition(self, cognition_text):
        entities = []
        relation = None
        if '是一种' in cognition_text:
            parts = cognition_text.split('是一种')
            if len(parts) == 2:
                entities = [parts[0].strip(), parts[1].strip()]
                relation = '是一种'
        elif '喜欢' in cognition_text:
            parts = cognition_text.split('喜欢')
            if len(parts) == 2:
                entities = [parts[0].strip(), parts[1].strip()]
                relation = '喜欢'
        elif '讨厌' in cognition_text:
            parts = cognition_text.split('讨厌')
            if len(parts) == 2:
                entities = [parts[0].strip(), parts[1].strip()]
                relation = '讨厌'
        return entities, relation

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
                                "description": "关键词列表，从认知信息中提取的核心实体"
                            }
                        },
                        "required": ["entity_keywords"]
                    }
                }
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
                            "source_event_id": {"type": "string", "default": "unknown"}
                        },
                        "required": ["source_node", "relation", "target_node"]
                    }
                }
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
                            "target_node": {"type": "string"}
                        },
                        "required": ["source_node", "relation", "target_node"]
                    }
                }
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
                            "reason": {"type": "string"}
                        },
                        "required": ["source_node", "relation", "target_node", "reason"]
                    }
                }
            }
        ]

        tool_map = {
            'rag_search': rag_search,
            'add_relation': add_relation,
            'reinforce_relation': reinforce_relation,
            'weaken_relation': weaken_relation
        }

        system_msg = {
            "role": "system",
            "content": "你是一个严谨的知识图谱构建助手。收到一批认知条目，你需要：\n1. 先用 rag_search 批量检索关键词\n2. 根据检索结果调用 add_relation/reinforce_relation/weaken_relation\n3. 所有条目处理完毕后回复'完成'"
        }

        user_content = "【待处理的认知条目】\n"
        for i, item in enumerate(cognition_data, 1):
            user_content += f"{i}. {item}\n"
        user_content += "\n请开始处理：先用 rag_search 检索，然后逐条写入图谱。"

        messages = [
            system_msg,
            {"role": "user", "content": user_content}
        ]

        max_turns = 50
        write_count = 0
        expected_writes = len(cognition_data)

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
                        "function": {"name": t.function.name, "arguments": t.function.arguments}
                    } for t in msg_resp.tool_calls
                ]

            messages.append(assist_msg)

            if not msg_resp.tool_calls:
                if write_count >= expected_writes:
                    print(f"✅ 图谱更新完成，共执行 {write_count} 次写入")
                    break
                else:
                    messages.append({
                        "role": "user",
                        "content": f"⚠️ 你还没有完成所有认知条目的写入（已完成 {write_count}/{expected_writes}）。请继续调用写入工具。"
                    })
                    continue

            tool_results = []
            for tc in msg_resp.tool_calls:
                tool_name = tc.function.name

                if tool_name in ['add_relation', 'reinforce_relation', 'weaken_relation']:
                    write_count += 1

                try:
                    tool_args = json.loads(tc.function.arguments)
                    tool_result = tool_map[tool_name](**tool_args)
                    print(f"[{turn}] {tool_name}: {tool_result}")
                except Exception as e:
                    tool_result = f"执行失败: {str(e)}"
                    print(f"[{turn}] {tool_name} 失败: {e}")

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result
                })
                messages.append(tool_results[-1])

            if write_count >= expected_writes:
                print(f"✅ 图谱更新完成，共执行 {write_count} 次写入")
                break

        print(f"📊 reAct 循环结束，写入 {write_count} 次 / 预期 {expected_writes} 次")

    def _process_cognition_fallback(self, cognition_data: list):
        """兜底处理：当 LLM 不可用时用启发式规则"""
        for cognition in cognition_data:
            entities, relation = self._extract_entities_from_cognition(cognition)
            if len(entities) == 2 and relation:
                source_node = entities[0]
                target_node = entities[1]
                search_result = rag_search([source_node])
                if '全新知识' in search_result:
                    add_relation(source_node, relation, target_node)
                elif '讨厌' in search_result and relation == '喜欢':
                    weaken_relation(source_node, '讨厌', target_node, '冲突')
                    add_relation(source_node, relation, target_node)
                else:
                    reinforce_relation(source_node, relation, target_node)

    def _process_file_with_lock(self, file_path):
        lock_key = os.path.abspath(file_path)
        with self._locks_mutex:
            if lock_key not in self._file_locks:
                self._file_locks[lock_key] = threading.Lock()
            lock = self._file_locks[lock_key]

        lock_acquired = lock.acquire(timeout=30)
        if not lock_acquired:
            return False

        try:
            if not os.path.exists(file_path):
                return False
            return self._process_file(file_path)
        except Exception as e:
            return False
        finally:
            lock.release()
            with self._locks_mutex:
                if lock_key in self._file_locks:
                    del self._file_locks[lock_key]

    def _process_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            error_path = os.path.join(ERROR_DIR, os.path.basename(file_path))
            shutil.move(file_path, error_path)
            return False

        try:
            event_id = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
            timestamp = data.get('timestamp', datetime.now().isoformat())

            # 1. 处理事件：读取字段改为 'events'
            events = data.get('events', [])
            for event in events:
                if isinstance(event, dict):
                    event_content = event.get('event', '')
                    event_time = event.get('time', timestamp)
                else:
                    event_content = event
                    event_time = timestamp

                event_vector = None
                if self.vector_engine:
                    event_vector = self.vector_engine._get_embedding(event_content)

                self.event_engine.insert_event(
                    event_id=f"event_{event_id}_{hashlib.md5(event_content.encode()).hexdigest()}",
                    content=event_content,
                    vector=event_vector,
                    timestamp=event_time,
                    source=os.path.basename(file_path)
                )

            # (已彻底移除 work_exps 的解析和插入逻辑)

            # 2. 处理图谱抽取：将 cognition 和 user_profile 拼合
            cognition = data.get('cognition', [])
            user_profile = data.get('user_profile', [])

            # 这些东西都可以作为认知素材，提取进入知识图谱
            graph_materials = cognition + user_profile

            if graph_materials and self.graph_engine:
                self._run_llm_step(graph_materials)
            if self.graph_engine:
                self.graph_engine._save_graph()
                try:
                    viz = GraphVisualizer()
                    viz.visualize()
                    print("✅ 图谱可视化已更新")
                except Exception as e:
                    print(f"⚠️ 图谱可视化更新失败: {e}")

            # 3. 归档日志记录
            archive_path = os.path.join(ARCHIVED_DIR, os.path.basename(file_path))
            shutil.move(file_path, archive_path)

            self.history.append({
                'event_id': event_id,
                'file': os.path.basename(file_path),
                'processed_at': datetime.now().isoformat(),
                'events_count': len(events),
                'has_graph_materials': bool(graph_materials)
            })
            print(f"✅ 后台 Worker 处理成功: {os.path.basename(file_path)}")
            return True
        except Exception as e:
            print(f"❌ Worker 处理文件失败: {e}")
            return False

    def run(self):
        print("Worker Agent 启动，开始轮询待处理文件...")
        while True:
            try:
                files = [f for f in os.listdir(PENDING_DIR) if f.startswith('memory_') and f.endswith('.json')]
                for file_name in files:
                    file_path = os.path.join(PENDING_DIR, file_name)
                    self._process_file_with_lock(file_path)
                time.sleep(MEMORY_AGENT_CONFIG['polling_interval'])
            except Exception as e:
                time.sleep(MEMORY_AGENT_CONFIG['polling_interval'])