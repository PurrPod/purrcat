# purrmemo/core/memory_worker/worker_agent.py

import os
import json
import time
import shutil
import hashlib
import threading
from datetime import datetime
from ..config import MEMORY_AGENT_CONFIG, OPENAI_API_CONFIG, PENDING_DIR, ARCHIVED_DIR, ERROR_DIR
from ..storage.event_engine import EventEngine

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

    def _run_llm_step(self, cognition_data):
        try:
            from openai import OpenAI
            prompt = MEMORY_WORKER_PROMPT + "\n\n请处理以下认知信息：\n"
            for i, cognition in enumerate(cognition_data):
                prompt += f"{i+1}. {cognition}\n"

            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "add_relation",
                        "description": "新增联系，当检索发现知识库中不存在该事实，或者需要建立层级关系时使用",
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
                        "description": "强化联系，当新的认知与知识库中已有的关系一致时使用",
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
                        "description": "削弱联系，当新的认知与已有关系产生冲突时使用",
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
                },
                {
                    "type": "function",
                    "function": {
                        "name": "rag_search",
                        "description": "图谱检索工具，必须优先调用以检查实体是否存在",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "entity_keyword": {"type": "string"}
                            },
                            "required": ["entity_keyword"]
                        }
                    }
                }
            ]

            client = OpenAI(
                api_key=OPENAI_API_CONFIG['api_key'],
                base_url=OPENAI_API_CONFIG['base_url']
            )

            messages = [
                {"role": "system", "content": "你是一个严谨的知识图谱构建助手。"},
                {"role": "user", "content": prompt}
            ]

            tool_map = {
                'add_relation': add_relation,
                'reinforce_relation': reinforce_relation,
                'weaken_relation': weaken_relation,
                'rag_search': rag_search
            }

            max_tool_calls = 10
            tool_calls_count = 0
            tool_calls_record = []
            
            # 【核心逻辑新增】检测模型是否真正调用了写入操作
            has_write_operation = False 

            while tool_calls_count < max_tool_calls:
                response = client.chat.completions.create(
                    model=OPENAI_API_CONFIG['model_name'],
                    messages=messages,
                    tools=tools,
                )

                message = response.choices[0].message
                
                reasoning_content = None
                if hasattr(message, 'reasoning_content') and message.reasoning_content:
                    reasoning_content = message.reasoning_content

                if hasattr(message, 'tool_calls') and message.tool_calls:
                    # 1. 将包含所有工具调用的 Assistant 消息完整加入（解决并发调用Bug）
                    assistant_message = {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments
                                }
                            } for tc in message.tool_calls
                        ]
                    }
                    if reasoning_content:
                        assistant_message["reasoning_content"] = reasoning_content
                    messages.append(assistant_message)

                    # 2. 依次执行每个工具并追加 Tool 结果消息
                    for tc in message.tool_calls:
                        tool_name = tc.function.name
                        
                        # 检查是否有实质性的写入操作
                        if tool_name in ['add_relation', 'weaken_relation', 'reinforce_relation']:
                            has_write_operation = True
                            
                        # 【核心逻辑新增】工具参数解析容错兜底
                        try:
                            tool_args = json.loads(tc.function.arguments)
                        except json.JSONDecodeError as e:
                            print(f"[容错] 解析工具参数失败: {e}")
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": f"参数格式错误(必须是合法JSON): {tc.function.arguments}"
                            })
                            continue

                        # 【核心逻辑新增】工具执行容错兜底
                        if tool_name in tool_map:
                            try:
                                tool_result = tool_map[tool_name](**tool_args)
                                print(f"[工具调用成功] {tool_name}: {tool_result}")
                            except Exception as e:
                                tool_result = f"工具执行内部异常: {str(e)}"
                                print(f"[工具执行报错] {tool_name} 失败: {e}")
                        else:
                            tool_result = f"未知的工具: {tool_name}"

                        # 追加单个 Tool 执行结果
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(tool_result)
                        })

                        tool_calls_record.append({'tool': tool_name, 'args': tool_args})
                        tool_calls_count += 1
                else:
                    # 【核心逻辑新增】程序强制写入检测（防偷懒）
                    if not has_write_operation and cognition_data:
                        print("[警报] 模型意图结束，但未检测到实质性节点更新，强制打回重造！")
                        messages.append({
                            "role": "assistant", 
                            "content": message.content if message.content else "（思考完成）"
                        })
                        messages.append({
                            "role": "user",
                            "content": "⚠️ 系统检测警告：你只进行了检索或纯文本回复，**没有**调用任何实质性写入工具（add_relation/weaken_relation/reinforce_relation）。请**必须**基于上面的检索结果，立刻调用相应的工具将认知信息写入图谱！不要解释，直接调用工具！"
                        })
                        # 强制让大模型再思考一次并调用工具
                        continue 
                    
                    # 真正完成了写入任务，结束循环
                    break

            return {'tool_calls': tool_calls_record, 'cognition_list': cognition_data, 'raw_response': message.content}
        except ImportError:
            return self._process_cognition_fallback(cognition_data)
        except Exception as e:
            print(f"调用 LLM 失败: {e}")
            return self._process_cognition_fallback(cognition_data)

    def _process_cognition_fallback(self, cognition_data):
        tool_calls = []
        for cognition in cognition_data:
            entities, relation = self._extract_entities_from_cognition(cognition)
            if len(entities) == 2 and relation:
                source_node = entities[0]
                target_node = entities[1]
                search_result = rag_search(source_node)
                if '未找到' in search_result:
                    tool_calls.append({'tool': 'add_relation', 'args': {'source_node': source_node, 'relation': relation, 'target_node': target_node}})
                elif '讨厌' in search_result and relation == '喜欢':
                    tool_calls.append({'tool': 'weaken_relation', 'args': {'source_node': source_node, 'relation': '讨厌', 'target_node': target_node, 'reason': '冲突'}})
                    tool_calls.append({'tool': 'add_relation', 'args': {'source_node': source_node, 'relation': relation, 'target_node': target_node}})
                else:
                    tool_calls.append({'tool': 'reinforce_relation', 'args': {'source_node': source_node, 'relation': relation, 'target_node': target_node}})
        return {'tool_calls': tool_calls, 'cognition_list': cognition_data}

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

            events = data.get('events', [])
            for event in events:
                if isinstance(event, dict):
                    event_content = event.get('event', '')
                    event_time = event.get('time', timestamp)
                else:
                    event_content = event
                    event_time = timestamp

                # 计算事件向量
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

            work_exps = data.get('work_exp', [])
            for exp in work_exps:
                exp_id = hashlib.md5(exp.encode()).hexdigest()
                self.vector_engine.insert_experience(
                    exp_id=f"exp_{exp_id}",
                    content=exp,
                    timestamp=timestamp,
                    source_event_id=event_id
                )

            cognition = data.get('cognition', [])
            if cognition and graph_engine_available:
                self._run_llm_step(cognition)

            if graph_engine_available:
                self.graph_engine._save_graph()

            archive_path = os.path.join(ARCHIVED_DIR, os.path.basename(file_path))
            shutil.move(file_path, archive_path)

            self.history.append({
                'event_id': event_id,
                'file': os.path.basename(file_path),
                'processed_at': datetime.now().isoformat(),
                'events_count': len(events),
                'work_exps_count': len(work_exps),
                'has_cognition': bool(cognition)
            })

            self._save_checkpoint()
            print(f"处理文件成功: {os.path.basename(file_path)}")
            return True
        except Exception as e:
            print(f"处理文件失败: {e}")
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