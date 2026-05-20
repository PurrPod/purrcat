import datetime
import json
import os
import re
import threading
import uuid

from .core.memory_worker.worker_agent import MemoryAgent
from .core.search_tool import RAGSearchTool
from .core.storage.graph_engine import GraphEngine
from .core.utils import SingletonMeta
from .visualize_graph import GraphVisualizer
from src.utils.config import MEMORY_PENDING_DIR, get_memory_config


class PurrMemoClient(metaclass=SingletonMeta):
    def __init__(self):
        self.search_tool = RAGSearchTool()
        self._daemon_started = False
        self.init()

    def _start_daemon(self):
        """启动守护进程监听 buffer/pending"""
        agent = MemoryAgent()
        daemon_thread = threading.Thread(target=agent.run, daemon=True)
        daemon_thread.start()
        self._daemon_started = True
        print("✅ 后台守护进程已启动，正在监听 pending 目录...")

    def init(self):
        """初始化 Memory Client，启动后台守护进程。

        该方法是幂等的，重复调用不会重复启动守护线程。
        """
        if not self._daemon_started:
            self._start_daemon()
        return True

    def _normalize_iso_time(self, time_str: str) -> str:
        time_str = time_str.strip()
        if re.match(r"^\d{8}$", time_str):
            return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}T00:00:00"
        elif re.match(r"^\d{8} \d{2}:\d{2}$", time_str):
            return f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}T{time_str[9:14]}:00"
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", time_str):
            return f"{time_str}T00:00:00"
        elif re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}$", time_str):
            return time_str.replace(" ", "T") + ":00"
        elif re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$", time_str):
            return time_str.replace(" ", "T")
        return time_str

    def _validate_memo_data(self, memo_data: dict) -> tuple[dict, list]:
        errors = []
        valid_data = {
            "short_term": "",
            "work_exp": [],
            "user_profile": [],
            "events": [],
            "cognition": [],
        }

        if not isinstance(memo_data, dict):
            return {}, ["memo_data must be a dict"]

        short_term = memo_data.get("short_term")
        if short_term is not None and not isinstance(short_term, str):
            errors.append(f"short_term must be a string, got {type(short_term).__name__}")
        elif short_term:
            valid_data["short_term"] = short_term.strip()

        work_exp = memo_data.get("work_exp", [])
        if not isinstance(work_exp, list):
            errors.append(f"work_exp must be a list, got {type(work_exp).__name__}")
        else:
            for i, w in enumerate(work_exp):
                if not isinstance(w, str) or not w.strip():
                    errors.append(f"work_exp[{i}] must be a non-empty string")
                else:
                    valid_data["work_exp"].append(w.strip())

        user_profile = memo_data.get("user_profile", [])
        if not isinstance(user_profile, list):
            errors.append(f"user_profile must be a list, got {type(user_profile).__name__}")
        else:
            for i, u in enumerate(user_profile):
                if not isinstance(u, str) or not u.strip():
                    errors.append(f"user_profile[{i}] must be a non-empty string")
                else:
                    valid_data["user_profile"].append(u.strip())

        events = memo_data.get("events", [])
        if not isinstance(events, list):
            errors.append(f"events must be a list, got {type(events).__name__}")
        else:
            for i, e in enumerate(events):
                if not isinstance(e, dict):
                    errors.append(f"events[{i}] must be an object with time and event")
                    continue
                if "time" not in e or "event" not in e:
                    errors.append(f"events[{i}] must contain time and event")
                    continue
                if not isinstance(e["time"], str) or not e["time"].strip():
                    errors.append(f"events[{i}].time must be a non-empty string")
                elif not isinstance(e["event"], str) or not e["event"].strip():
                    errors.append(f"events[{i}].event must be a non-empty string")
                else:
                    time_str = e["time"].strip()
                    time_pattern = (
                        r"^(\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?|"
                        r"\d{8}( \d{2}:\d{2})?)$"
                    )
                    if not re.match(time_pattern, time_str):
                        errors.append(
                            f"events[{i}].time format invalid: '{time_str}', expected YYYY-MM-DD HH:MM"
                        )
                    else:
                        valid_data["events"].append(
                            {
                                "time": self._normalize_iso_time(time_str),
                                "event": e["event"].strip(),
                            }
                        )

        cognition = memo_data.get("cognition", [])
        if not isinstance(cognition, list):
            errors.append(f"cognition must be a list, got {type(cognition).__name__}")
        else:
            for i, c in enumerate(cognition):
                if not isinstance(c, str) or not c.strip():
                    errors.append(f"cognition[{i}] must be a non-empty string")
                else:
                    valid_data["cognition"].append(c.strip())

        return valid_data, errors

    def _write_to_pending(
        self, events: list, cognition: list, user_profile: list, work_exp: list
    ) -> str:
        os.makedirs(MEMORY_PENDING_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"memory_{timestamp}_{unique_id}.json"
        filepath = os.path.join(MEMORY_PENDING_DIR, filename)

        data = {
            "user_profile": user_profile or [],
            "work_exp": work_exp or [],
            "events": events or [],
            "cognition": cognition or [],
            "timestamp": timestamp,
            "source": "memory_api",
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return filepath

    def search(self, query: str = "", filters: dict = None):
        """通过混合检索匹配记忆库里的数据"""
        filters = filters or {}

        if "top_k" not in filters:
            filters["top_k"] = 5

        if "date" in filters:
            raw_date = filters.pop("date")
            if raw_date and isinstance(raw_date, str):
                try:
                    parsed_date = datetime.datetime.strptime(
                        raw_date.strip(), "%Y-%m-%d"
                    )
                    start_time = parsed_date.strftime("%Y-%m-%dT00:00:00")
                    end_time = parsed_date.strftime("%Y-%m-%dT23:59:59.999999")
                    filters["time_range"] = (start_time, end_time)
                except ValueError:
                    print(
                        f"⚠️ [PurrMemo] 忽略无效的日期过滤参数 '{raw_date}'，期望格式为 YYYY-MM-DD"
                    )

        print(
            f"🔍 [PurrMemo] search_tool.search_memory_api | query={query!r} | filters={filters}"
        )
        result = self.search_tool.search_memory_api(query=query, filters=filters)
        print(
            f"🔍 [PurrMemo] search_memory_api 返回 | result长度={len(result) if result else 0}"
        )
        return result

    def add_memory(self, memo_data: dict) -> str:
        """写入待处理记忆，返回 pending 文件路径。"""
        valid_data, errors = self._validate_memo_data(memo_data)
        if errors:
            raise ValueError("; ".join(errors))

        filepath = self._write_to_pending(
            events=valid_data["events"],
            cognition=valid_data["cognition"],
            user_profile=valid_data["user_profile"],
            work_exp=valid_data["work_exp"],
        )
        return filepath

    def get_graph(self) -> dict:
        """获取图谱节点与边的简单表示。"""
        graph_engine = self.search_tool.graph_engine
        if not graph_engine or not getattr(graph_engine, "graph", None):
            return {"nodes": [], "edges": []}

        graph = graph_engine.graph
        nodes = []
        edges = []
        for node_id in graph.nodes:
            data = graph.nodes[node_id]
            nodes.append({"id": node_id, "label": data.get("name", node_id)})

        for source, target, edge_data in graph.edges(data=True):
            edges.append(
                {
                    "from": source,
                    "to": target,
                    "label": edge_data.get("relation_meaning", "unknown"),
                    "confidence": edge_data.get("confidence", 0.0),
                    "updated_at": edge_data.get("updated_at", ""),
                }
            )

        return {"nodes": nodes, "edges": edges}

    def get_recent_events(self, limit: int = 30):
        """获取最近的事件（从事件库）"""
        try:
            return self.search_tool.event_engine.get_events(limit=limit)
        except Exception:
            return []

    def get_recent_experiences(self, limit: int = 30):
        """获取最近的经验（从向量库）"""
        try:
            vector_engine = self.search_tool.vector_engine
            if not vector_engine or not getattr(vector_engine, 'collection', None):
                return []
            results = vector_engine.collection.get(include=["documents", "metadatas"])
            experiences = []
            if results and results.get("ids"):
                for i in range(len(results["ids"])):
                    meta = results["metadatas"][i] or {}
                    experiences.append({
                        "exp_id": results["ids"][i],
                        "content": results["documents"][i],
                        "timestamp": meta.get("timestamp", "")
                    })
            experiences.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return experiences[:limit]
        except Exception:
            return []

    def visualize_graph(self, output_file=None):
        """生成图谱可视化 HTML 文件"""
        try:
            visualizer = GraphVisualizer()
            visualizer.visualize(output_file=output_file)
            return True
        except Exception as e:
            print(f"可视化失败: {e}")
            return False


def get_memory_client():
    return PurrMemoClient()
