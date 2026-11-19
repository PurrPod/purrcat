"""按当前嵌入模型重建向量库的编排逻辑。"""

from __future__ import annotations

from src.memory.reindex import rebuild_vector_index


class _FakeEventEngine:
    def list_events(self):
        return [
            {"event_id": "e1", "content": "事件一", "timestamp": "2026-01-01T00:00:00"},
            {"event_id": "e2", "content": "事件二", "timestamp": "2026-01-02T00:00:00"},
        ]


class _FakeExperienceEngine:
    def list_all(self):
        return [
            {"exp_id": "x1", "content": "经验一", "timestamp": "2026-01-01T00:00:00"}
        ]


class _FakeGraphEngine:
    def list_nodes(self):
        return [{"node_id": "n1", "name": "节点一"}]


class _FakeVectorEngine:
    def __init__(self):
        self.calls = []
        self.rebuilt = {}
        self._embedding_model = object()

    @property
    def embedding_model(self):
        self.calls.append("load_model")
        return self._embedding_model

    def reset_collections(self):
        self.calls.append("reset")

    def rebuild_event_vectors(self, items):
        self.calls.append(("events", len(items)))
        self.rebuilt["events"] = list(items)
        return len(items)

    def rebuild_experience_vectors(self, items):
        self.calls.append(("experiences", len(items)))
        return len(items)

    def rebuild_graph_vectors(self, items):
        self.calls.append(("graph_nodes", len(items)))
        return len(items)

    def mark_index_model(self):
        self.calls.append("mark")
        return ["events", "experiences", "graph_nodes"]


def test_rebuild_uses_fact_sources_and_marks_model():
    vector = _FakeVectorEngine()

    report = rebuild_vector_index(
        vector_engine=vector,
        event_engine=_FakeEventEngine(),
        experience_engine=_FakeExperienceEngine(),
        graph_engine=_FakeGraphEngine(),
        log=lambda message: None,
    )

    assert report["counts"] == {"events": 2, "experiences": 1, "graph_nodes": 1}
    # 事件行使用 event_id，重建方法要求统一的 id 字段
    assert [item["id"] for item in vector.rebuilt["events"]] == ["e1", "e2"]
    # 先确认编码器可用再清空，避免模型缺失时丢掉现有向量
    assert vector.calls[0] == "load_model"
    assert vector.calls[1] == "reset"
    assert vector.calls[-1] == "mark"
