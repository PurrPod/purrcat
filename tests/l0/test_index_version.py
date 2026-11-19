"""向量库模型版本检测与标记。"""

from __future__ import annotations

import chromadb
from chromadb.config import Settings

from src.memory.purrmemo.core import index_version
from src.utils.embedding_manifest import MODEL_TAG


def _client(path):
    return chromadb.PersistentClient(
        path=str(path), settings=Settings(anonymized_telemetry=False)
    )


def _collection(client, name, model=None):
    metadata = {"hnsw:space": "cosine"}
    if model:
        metadata[index_version.INDEX_MODEL_KEY] = model
    return client.get_or_create_collection(name=name, metadata=metadata)


def test_missing_chroma_dir_is_not_a_rebuild_signal(tmp_path):
    info = index_version.read_index_version(str(tmp_path / "chromadb"))

    assert info["status"] == index_version.MISSING
    assert info["needs_rebuild"] is False


def test_empty_collections_are_not_stale(tmp_path):
    client = _client(tmp_path)
    for name in ("events", "experiences", "graph_nodes"):
        _collection(client, name, "old-model")
    client = None

    info = index_version.read_index_version(str(tmp_path))

    assert info["status"] == index_version.EMPTY
    assert info["needs_rebuild"] is False


def test_untagged_vectors_are_stale(tmp_path):
    client = _client(tmp_path)
    events = _collection(client, "events")
    events.upsert(ids=["e1"], embeddings=[[1.0, 0.0]], documents=["a"])
    del client

    info = index_version.read_index_version(str(tmp_path))

    assert info["vectors"] == 1
    assert info["models"] == []
    assert info["status"] == index_version.STALE
    assert info["needs_rebuild"] is True


def test_current_tag_is_healthy(tmp_path):
    client = _client(tmp_path)
    events = _collection(client, "events", MODEL_TAG)
    events.upsert(ids=["e1"], embeddings=[[1.0, 0.0]], documents=["a"])
    del client

    info = index_version.read_index_version(str(tmp_path))

    assert info["status"] == index_version.CURRENT
    assert info["needs_rebuild"] is False


class _FakeCollection:
    def __init__(self, name, metadata=None):
        self.name = name
        self.metadata = metadata or {}

    def modify(self, metadata):
        self.metadata = metadata


class _FakeVectorEngine:
    def __init__(self):
        self.collection = _FakeCollection("experiences", {"hnsw:space": "cosine"})
        self.events_collection = _FakeCollection("events")
        self.graph_collection = _FakeCollection("graph_nodes")


def test_mark_index_model_drops_index_config():
    engine = _FakeVectorEngine()

    marked = index_version.mark_index_model(engine)

    assert marked == ["experiences", "events", "graph_nodes"]
    # hnsw:* 创建后不可修改，写标记时必须剔除
    assert engine.collection.metadata == {
        index_version.INDEX_MODEL_KEY: MODEL_TAG,
    }
    assert engine.events_collection.metadata[index_version.INDEX_MODEL_KEY] == MODEL_TAG
