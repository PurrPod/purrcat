"""嵌入模型完整性判定与配置读取（SPEC-015）。"""

from __future__ import annotations

import json

import numpy as np

from src.utils import embedding_manifest, local_embedding


def test_model_dir_complete_requires_tokenizer_and_onnx(tmp_path):
    assert embedding_manifest.is_model_dir_complete(str(tmp_path)) is False

    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    assert embedding_manifest.is_model_dir_complete(str(tmp_path)) is False

    onnx_dir = tmp_path / "onnx"
    onnx_dir.mkdir()
    (onnx_dir / "model.onnx").write_bytes(b"model")

    assert embedding_manifest.is_model_dir_complete(str(tmp_path)) is True


def test_expected_files_merges_profile_and_shared():
    files = embedding_manifest.expected_files({"onnx/model.onnx": "abc"})

    assert files["onnx/model.onnx"] == "abc"
    assert "tokenizer.json" in files
    assert files["config.json"].startswith("6300193")


def test_resolve_sources_prefers_endpoint_then_env_then_defaults():
    assert embedding_manifest.resolve_sources("https://mirror", "https://env") == [
        "https://mirror"
    ]
    assert embedding_manifest.resolve_sources(None, "https://env") == [
        "https://env",
        "https://hf-mirror.com",
        "https://huggingface.co",
    ]


def test_read_max_seq_length_falls_back_on_invalid_value(tmp_path):
    (tmp_path / "sentence_bert_config.json").write_text(
        json.dumps({"max_seq_length": "oops"}), encoding="utf-8"
    )
    assert embedding_manifest.read_max_seq_length(str(tmp_path), 512) == 512

    (tmp_path / "sentence_bert_config.json").write_text(
        json.dumps({"max_seq_length": 128}), encoding="utf-8"
    )
    assert embedding_manifest.read_max_seq_length(str(tmp_path), 512) == 128


def test_mean_pool_ignores_padding():
    outputs = np.array([[[1.0, 2.0], [3.0, 4.0], [99.0, 99.0]]], dtype=np.float32)
    mask = np.array([[1, 1, 0]], dtype=np.int64)

    pooled = local_embedding.mean_pool(outputs, mask)

    assert pooled.shape == (1, 2)
    assert np.allclose(pooled, [[2.0, 3.0]])


def test_choose_output_name_prefers_last_hidden_state():
    assert local_embedding.choose_output_name(["token_embeddings"]) == (
        "token_embeddings"
    )
    assert (
        local_embedding.choose_output_name(["last_hidden_state", "other"])
        == "last_hidden_state"
    )
