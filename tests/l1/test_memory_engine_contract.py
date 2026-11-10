"""记忆引擎与客户端的公开契约（SPEC-012 AC-4/AC-5/AC-6）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import networkx as nx
import pytest

from src.memory.purrmemo.client import PurrMemoClient
from src.memory.purrmemo.core import ids
from src.memory.purrmemo.core.memory_worker import worker_agent
from src.memory.purrmemo.core.search_tool import RAGSearchTool
from src.memory.purrmemo.core.storage.event_engine import EventEngine
from src.memory.purrmemo.core.storage.graph_engine import GraphEngine
from src.memory.purrmemo.core.storage.graph_io import load_graph
from src.memory.purrmemo.core.storage.vector_engine import VectorEngine
from src.memory.purrmemo.core.utils import SingletonMeta


@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch):
    """单例缓存按用例隔离，保证每个引擎都能绑定 tmp_path。"""
    monkeypatch.setattr(SingletonMeta, "_instances", {})
    monkeypatch.setattr(SingletonMeta, "_locks", {})


class _Vector(list):
    def tolist(self):
        return list(self)


class FakeEmbedding:
    def encode(self, text):
        return _Vector([float(len(text)), 1.0])


class FakeCollection:
    def __init__(self):
        self.ids = []
        self.documents = []
        self.metadatas = []
        self.embeddings = []
        self.distances = {}

    def count(self):
        return len(self.ids)

    def upsert(self, ids, embeddings, documents, metadatas):
        for index, record_id in enumerate(ids):
            if record_id in self.ids:
                position = self.ids.index(record_id)
            else:
                self.ids.append(record_id)
                self.documents.append(None)
                self.metadatas.append(None)
                self.embeddings.append(None)
                position = len(self.ids) - 1
            self.embeddings[position] = embeddings[index]
            self.documents[position] = documents[index]
            self.metadatas[position] = metadatas[index]

    def get(self, ids=None, include=None):
        if ids is None:
            selected = list(range(len(self.ids)))
        else:
            selected = [
                self.ids.index(record_id) for record_id in ids if record_id in self.ids
            ]
        return {
            "ids": [self.ids[i] for i in selected],
            "documents": [self.documents[i] for i in selected],
            "metadatas": [self.metadatas[i] for i in selected],
        }

    def query(self, query_embeddings, n_results):
        selected = list(range(min(n_results, len(self.ids))))
        return {
            "ids": [[self.ids[i] for i in selected]],
            "documents": [[self.documents[i] for i in selected]],
            "metadatas": [[self.metadatas[i] for i in selected]],
            "distances": [[self.distances.get(self.ids[i], 0.0) for i in selected]],
        }

    def delete(self, ids):
        for record_id in ids:
            if record_id in self.ids:
                position = self.ids.index(record_id)
                del self.ids[position]
                del self.documents[position]
                del self.metadatas[position]
                del self.embeddings[position]


class FakeClient:
    def __init__(self):
        self.collections = {}

    def get_or_create_collection(self, name, metadata=None):
        return self.collections.setdefault(name, FakeCollection())


class FakeGraphVector:
    def __init__(self):
        self.inserted = []

    def insert_graph_node(self, node_id, node_name):
        self.inserted.append((node_id, node_name))
        return True


def build_vector_engine(tmp_path):
    return VectorEngine(
        persist_directory=str(tmp_path / "chroma"),
        client=FakeClient(),
        embedding_model=FakeEmbedding(),
        embedding_model_name="fake",
    )


def test_event_engine_crud_and_fts(tmp_path):
    """SPEC-012 AC-4：事件库 CRUD、时间区间与 FTS5 检索。"""
    engine = EventEngine(db_path=str(tmp_path / "events.db"), table_name="events")

    assert engine.insert_event(
        "e1", "苹果 香蕉", timestamp="2026-01-01T10:00:00", source="test"
    )
    assert engine.insert_event("e2", "香蕉", timestamp="2026-01-02T10:00:00")

    assert engine.get_event_by_id("e1") == {
        "event_id": "e1",
        "content": "苹果 香蕉",
        "timestamp": "2026-01-01T10:00:00",
        "source": "test",
    }
    assert [row["event_id"] for row in engine.get_events()] == ["e2", "e1"]
    assert [row["event_id"] for row in engine.get_events(limit=1)] == ["e2"]
    assert [
        row["event_id"]
        for row in engine.get_events(
            "2026-01-01T00:00:00", "2026-01-01T23:59:59.999999"
        )
    ] == ["e1"]

    hits = engine.search_fts_bm25("苹果")
    assert [hit["id"] for hit in hits] == ["e1"]
    assert hits[0]["data"]["content"] == "苹果 香蕉"
    assert hits[0]["score"] >= 0
    assert engine.search_fts_bm25("   ") == []

    assert engine.delete_event("e1") is True
    assert engine.get_event_by_id("e1") is None
    assert engine.delete_event("missing") is False


def test_event_engine_cleanup_old_events(tmp_path):
    """SPEC-012 AC-4：按时间阈值清理陈旧事件。"""
    engine = EventEngine(db_path=str(tmp_path / "events.db"), table_name="events")
    engine.insert_event("old", "陈旧", timestamp="2000-01-01T00:00:00")
    engine.insert_event("new", "新鲜", timestamp="2999-01-01T00:00:00")

    assert engine.cleanup_old_events(days_threshold=90) == 1
    assert [row["event_id"] for row in engine.get_events()] == ["new"]


def test_graph_engine_relation_lifecycle(tmp_path):
    """SPEC-012 AC-4：节点/关系增删、强化削弱、衰减与持久化。"""
    graph_vector = FakeGraphVector()
    engine = GraphEngine(
        graph_path=str(tmp_path / "graph.pkl"),
        min_confidence=0.3,
        vector_engine=graph_vector,
    )

    assert engine.add_node("a", "用户") is True
    assert engine.add_node("b", "苹果") is True
    assert engine.add_node("a", "重复") is True
    assert engine.graph.nodes["a"]["name"] == "用户"
    assert graph_vector.inserted == [("a", "用户"), ("b", "苹果")]

    assert engine.add_relation("a", "b", "喜欢", confidence=0.5, source_event_id="evt")
    relation = engine.get_relation("a", "b")
    assert relation["edge_id"] == ids.edge_id_for("a", "b", "喜欢")
    assert relation["relation_meaning"] == "喜欢"
    assert relation["source_event_id"] == "evt"
    assert relation["created_at"]
    assert relation["updated_at"]
    assert engine.add_relation("a", "missing", "喜欢") is False

    assert (
        engine.get_relations_by_node("a", direction="out")[0]["target_node_id"] == "b"
    )
    assert engine.get_relations_by_node("a", direction="in") == []

    assert engine.reinforce_relation("a", "b", "喜欢", increment=0.1) is True
    assert engine.get_relation("a", "b")["confidence"] == pytest.approx(0.6)
    assert engine.weaken_relation("a", "b", "喜欢", decrement=0.5) is True
    assert engine.get_relation("a", "b")["confidence"] == pytest.approx(0.3)
    assert engine.weaken_relation("a", "b", "其他", decrement=0.1) is False

    assert (
        engine.decay_edges(
            [{"source_node_id": "a", "target_node_id": "b", "new_confidence": 0.1}]
        )
        == 1
    )
    assert engine.get_relation("a", "b")["confidence"] == pytest.approx(0.1)
    assert engine.get_relations_by_node("a", direction="out") == []
    assert engine.get_graph_stats() == {"nodes": 2, "edges": 1}

    engine.save_graph()
    loaded = load_graph(str(tmp_path / "graph.pkl"))
    assert loaded.nodes["a"]["name"] == "用户"
    assert loaded["a"]["b"]["confidence"] == pytest.approx(0.1)

    assert engine.delete_relation("a", "b") is True
    assert engine.delete_relation("a", "b") is False


def test_vector_engine_experience_contract(tmp_path):
    """SPEC-012 AC-4：经验 upsert、访问计数、阈值检索与删除。"""
    engine = build_vector_engine(tmp_path)

    assert engine.insert_experience("e1", "先检查网络", timestamp="2026-01-01T00:00:00")
    assert engine.get_experience_by_id("e1")["metadata"]["access_count"] == 1

    assert engine.insert_experience("e1", "先检查网络", timestamp="2026-01-01T00:00:00")
    assert engine.get_experience_by_id("e1")["metadata"]["access_count"] == 2

    assert engine.insert_experience("e2", "再重启服务", timestamp="2026-01-02T00:00:00")
    engine.collection.distances.update({"e1": 0.2, "e2": 0.9})

    hits = engine.search_experiences("网络", top_k=5)
    assert [hit["exp_id"] for hit in hits] == ["e1"]
    assert hits[0]["score"] == pytest.approx(0.8)
    assert engine.search_experiences("") == []

    assert engine.get_collection_stats() == 2
    assert engine.delete_experience("e2") is True
    assert engine.get_experience_by_id("e2") is None


def test_vector_engine_event_and_graph_contract(tmp_path):
    """SPEC-012 AC-4：事件向量相似度与图谱节点加权排序。"""
    engine = build_vector_engine(tmp_path)

    assert engine.insert_event_vector("evt1", "开会", timestamp="2026-01-01T00:00:00")
    engine.events_collection.distances["evt1"] = 0.25
    hits = engine.search_events_vector("开会", top_k=10)
    assert hits[0]["id"] == "evt1"
    assert hits[0]["data"]["timestamp"] == "2026-01-01T00:00:00"
    assert hits[0]["score"] == pytest.approx(0.75)
    assert engine.get_event_by_id("evt1")["content"] == "开会"

    assert engine.insert_graph_node("n1", "苹果")
    assert engine.insert_graph_node("n2", "红富士苹果")
    engine.graph_collection.distances.update({"n1": 0.5, "n2": 0.5})

    nodes = engine.search_graph_nodes("苹果", top_k=2)
    assert [node["node_id"] for node in nodes] == ["n1", "n2"]
    assert nodes[0]["score"] == pytest.approx(2.5)
    assert nodes[1]["score"] == pytest.approx(1.0)
    assert engine.get_graph_collection_stats() == 2
    assert engine.search_graph_nodes("", top_k=2) == []


def test_vector_engine_cleanup_old_experiences(tmp_path):
    """SPEC-012 AC-4：按 last_accessed 与访问次数清理经验。"""
    engine = build_vector_engine(tmp_path)
    engine.insert_experience("old", "旧经验")
    engine.insert_experience("kept", "常看经验")

    collection = engine.collection
    stale = (datetime.now() - timedelta(days=60)).isoformat()
    collection.metadatas[collection.ids.index("old")] = {
        "last_accessed": stale,
        "access_count": 1,
    }
    collection.metadatas[collection.ids.index("kept")] = {
        "last_accessed": stale,
        "access_count": 5,
    }

    assert engine.cleanup_old_experiences(days_threshold=30, min_access_count=2) == 1
    assert [record_id for record_id in collection.ids] == ["kept"]


class FakeEventEngine:
    def __init__(self, events=None, fts=None):
        self.events = events or []
        self.fts = fts or []

    def get_events(self, start_time=None, end_time=None, limit=100):
        return self.events[:limit]

    def search_fts_bm25(self, query, start_time=None, end_time=None, limit=50):
        return self.fts


class FakeSearchVector:
    def __init__(self):
        self.event_results = []
        self.experience_results = []
        self.embedded = []

    def _get_embedding(self, text):
        self.embedded.append(text)
        return [1.0]

    def search_events_vector(self, query, top_k=200, query_embedding=None):
        return self.event_results

    def search_experiences(self, query, top_k=5, filters=None, query_embedding=None):
        return self.experience_results


class FakeGraphEngine:
    def __init__(self):
        self.vector_engine = SimpleNamespace(
            search_graph_nodes=lambda query, top_k=5, query_embedding=None: [
                {"node_id": "n1"}
            ]
        )
        self.graph = nx.DiGraph()
        self.min_confidence = 0.3
        self.relations = []
        self.nodes = {}

    def get_graph_stats(self):
        return {"nodes": len(self.nodes), "edges": len(self.relations)}

    def get_relations_by_node(self, node_id, direction="out"):
        return list(self.relations)

    def get_node(self, node_id):
        return self.nodes.get(node_id)


def test_search_tool_empty_query_formats_events():
    """SPEC-012 AC-5：空查询直接取最近事件并渲染。"""
    tool = RAGSearchTool(
        event_engine=FakeEventEngine(
            events=[{"timestamp": "2026-01-01", "content": "开会"}]
        ),
        vector_engine=FakeSearchVector(),
        graph_engine=FakeGraphEngine(),
        max_workers=2,
    )

    markdown = tool.search_memory_api("")

    assert markdown == "## 历史事件\n- [2026-01-01] 开会\n"


def test_search_tool_query_fuses_and_formats_all_sections():
    """SPEC-012 AC-5：混合检索结果按 RRF 融合后统一渲染。"""
    graph = FakeGraphEngine()
    graph.nodes = {
        "n1": {"node_id": "n1", "name": "用户"},
        "n2": {"node_id": "n2", "name": "苹果"},
    }
    graph.relations = [
        {
            "edge_id": "edge-1",
            "source_node_id": "n1",
            "target_node_id": "n2",
            "relation_meaning": "喜欢",
            "confidence": 0.8,
        }
    ]
    vector = FakeSearchVector()
    vector.event_results = [
        {
            "id": "e1",
            "data": {"timestamp": "2026-01-01", "content": "向量事件"},
            "score": 0.9,
        }
    ]
    vector.experience_results = [{"score": 0.5, "content": "经验"}]
    tool = RAGSearchTool(
        event_engine=FakeEventEngine(
            fts=[
                {
                    "id": "e2",
                    "data": {"timestamp": "2026-01-02", "content": "BM25 事件"},
                    "score": 5.0,
                }
            ]
        ),
        vector_engine=vector,
        graph_engine=graph,
        max_workers=2,
    )

    markdown = tool.search_memory_api("苹果", {"top_k": 3})

    assert vector.embedded == ["苹果"]
    assert "## 历史事件" in markdown
    assert "向量事件" in markdown
    assert "BM25 事件" in markdown
    assert "## 工作经验\n- [0.50] 经验" in markdown
    assert "## 知识图谱\n- 用户 喜欢 苹果 (置信度: 0.80)" in markdown


class FakeClientSearchTool:
    def __init__(self):
        self.graph_engine = SimpleNamespace(graph=None)
        self.vector_engine = None
        self.event_engine = None
        self.calls = []

    def search_memory_api(self, query="", filters=None):
        self.calls.append((query, dict(filters or {})))
        return "markdown"


def test_client_search_fills_top_k_and_date_range():
    """SPEC-012 AC-5：客户端补齐 top_k 并把 date 转为闭区间。"""
    fake = FakeClientSearchTool()
    client = PurrMemoClient(search_tool=fake, auto_start=False)

    client.search("苹果", {"date": "2026-05-15"})
    client.search("香蕉", {"top_k": 2})
    client.search("梨", {"date": "invalid"})

    assert fake.calls[0] == (
        "苹果",
        {
            "top_k": 5,
            "time_range": ("2026-05-15T00:00:00", "2026-05-15T23:59:59.999999"),
        },
    )
    assert fake.calls[1] == ("香蕉", {"top_k": 2})
    assert fake.calls[2] == ("梨", {"top_k": 5})


def test_client_graph_and_recent_views():
    """SPEC-012 AC-5：图谱 payload 与最近经验/事件的返回结构。"""
    fake = FakeClientSearchTool()
    client = PurrMemoClient(search_tool=fake, auto_start=False)

    assert client.get_graph() == {"nodes": [], "edges": []}

    graph = nx.DiGraph()
    graph.add_node("a", name="用户")
    graph.add_node("b")
    graph.add_edge(
        "a", "b", relation_meaning="喜欢", confidence=0.8, updated_at="2026-01-01"
    )
    fake.graph_engine = SimpleNamespace(graph=graph)
    assert client.get_graph() == {
        "nodes": [{"id": "a", "label": "用户"}, {"id": "b", "label": "b"}],
        "edges": [
            {
                "from": "a",
                "to": "b",
                "label": "喜欢",
                "confidence": 0.8,
                "updated_at": "2026-01-01",
            }
        ],
    }

    fake.vector_engine = SimpleNamespace(
        collection=SimpleNamespace(
            get=lambda include=None: {
                "ids": ["e1", "e2"],
                "documents": ["一", "二"],
                "metadatas": [
                    {"timestamp": "2026-01-01"},
                    {"timestamp": "2026-02-01"},
                ],
            }
        )
    )
    assert client.get_recent_experiences(limit=1) == [
        {"exp_id": "e2", "content": "二", "timestamp": "2026-02-01"}
    ]

    class BoomEventEngine:
        def get_events(self, limit=30):
            raise RuntimeError("db down")

    fake.event_engine = BoomEventEngine()
    assert client.get_recent_events() == []


class FakeWorkerEventEngine:
    def __init__(self):
        self.inserted = []

    def insert_event(self, event_id, content, timestamp=None, source=None):
        self.inserted.append(
            {"event_id": event_id, "content": content, "timestamp": timestamp}
        )
        return True


class FakeWorkerVector:
    def __init__(self):
        self.embedding_model = object()
        self.events = []
        self.experiences = []

    def insert_event_vector(self, event_id, content, timestamp=None):
        self.events.append((event_id, content, timestamp))
        return True

    def insert_experience(self, exp_id, content, timestamp=None, source_event_id=None):
        self.experiences.append((exp_id, content, timestamp))
        return True


class FakeWorkerGraph:
    def __init__(self):
        self.saved = 0

    def save_graph(self):
        self.saved += 1


def _worker_dirs(tmp_path, monkeypatch):
    pending = tmp_path / "pending"
    archived = tmp_path / "archived"
    error = tmp_path / "error"
    for directory in (pending, archived, error):
        directory.mkdir()
    monkeypatch.setattr(worker_agent, "MEMORY_PENDING_DIR", str(pending))
    monkeypatch.setattr(worker_agent, "ARCHIVED_DIR", str(archived))
    monkeypatch.setattr(worker_agent, "ERROR_DIR", str(error))
    return pending, archived, error


def test_memory_agent_processes_and_archives_pending_file(tmp_path, monkeypatch):
    """SPEC-012 AC-5：pending 事件写入引擎后归档并记录历史。"""
    pending, archived, _ = _worker_dirs(tmp_path, monkeypatch)
    file_path = pending / "memory_20260101120000_abcd1234.json"
    file_path.write_text(
        json.dumps(
            {
                "timestamp": "20260101120000",
                "events": [{"event": "喝水", "time": "2026-01-01T08:00:00"}],
            }
        ),
        encoding="utf-8",
    )

    event_engine = FakeWorkerEventEngine()
    vector = FakeWorkerVector()
    graph = FakeWorkerGraph()
    agent = worker_agent.MemoryAgent(
        event_engine=event_engine,
        vector_engine=vector,
        graph_engine=graph,
        start_scheduler=False,
    )

    assert agent._process_file(str(file_path)) is True
    expected_id = ids.event_id_for("喝水")
    assert event_engine.inserted == [
        {
            "event_id": expected_id,
            "content": "喝水",
            "timestamp": "2026-01-01T08:00:00",
        }
    ]
    assert vector.events == [(expected_id, "喝水", "2026-01-01T08:00:00")]
    assert not file_path.exists()
    assert (archived / file_path.name).exists()
    assert agent.history[0]["event_id"] == expected_id
    assert agent.history[0]["events_count"] == 1
    assert agent.history[0]["has_graph_materials"] is False


def test_memory_agent_moves_invalid_json_to_error(tmp_path, monkeypatch):
    """SPEC-012 AC-5：损坏文件移入 error 目录并返回 False。"""
    pending, _, error = _worker_dirs(tmp_path, monkeypatch)
    file_path = pending / "memory_bad.json"
    file_path.write_text("{", encoding="utf-8")

    agent = worker_agent.MemoryAgent(
        event_engine=FakeWorkerEventEngine(),
        vector_engine=FakeWorkerVector(),
        graph_engine=FakeWorkerGraph(),
        start_scheduler=False,
    )

    assert agent._process_file(str(file_path)) is False
    assert not file_path.exists()
    assert (error / file_path.name).exists()


def test_memory_agent_keeps_file_when_embedding_not_ready(tmp_path, monkeypatch):
    """SPEC-012 AC-5：嵌入模型未就绪时文件留在 pending 等待重试。"""
    pending, archived, _ = _worker_dirs(tmp_path, monkeypatch)
    file_path = pending / "memory_retry.json"
    file_path.write_text(
        json.dumps({"events": [{"event": "开会", "time": "2026-01-01"}]}),
        encoding="utf-8",
    )

    class NotReadyVector:
        @property
        def embedding_model(self):
            raise RuntimeError("embedding model not ready")

    agent = worker_agent.MemoryAgent(
        event_engine=FakeWorkerEventEngine(),
        vector_engine=NotReadyVector(),
        graph_engine=FakeWorkerGraph(),
        start_scheduler=False,
    )

    assert agent._process_file(str(file_path)) is False
    assert file_path.exists()
    assert not (archived / file_path.name).exists()
