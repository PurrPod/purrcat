"""信封协议：类型推断、兼容转换、URI 解析与路径穿越防护。"""

from __future__ import annotations

import os

import pytest

import src.utils.config  # noqa: F401  # 先完成 config 初始化，避免 harness 包导入触发循环依赖
from src.harness import envelope


@pytest.mark.parametrize("bad_type", ["", "text", "unknown", None])
def test_make_falls_back_to_any_when_type_unknown(bad_type):
    env = envelope.make(bad_type, "x")
    assert env == {"type": "any", "data": "x"}


def test_make_keeps_mime_and_meta_only_when_present():
    assert envelope.make("string", "x") == {"type": "string", "data": "x"}
    assert envelope.make("file", "purrcat://a", mime="text/html", meta={"k": 1}) == {
        "type": "file",
        "data": "purrcat://a",
        "mime": "text/html",
        "meta": {"k": 1},
    }


def test_is_envelope_requires_known_type_and_data():
    assert envelope.is_envelope({"type": "string", "data": "x"})
    assert not envelope.is_envelope("string")
    assert not envelope.is_envelope({"type": "unknown", "data": "x"})
    assert not envelope.is_envelope({"type": "string"})
    assert not envelope.is_envelope({"data": "x"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, "boolean"),  # bool 是 int 子类，必须先于 number 判断
        (False, "boolean"),
        (1, "number"),
        (1.5, "number"),
        ("x", "string"),
        ([1], "list"),
        ({"a": 1}, "any"),
        (None, "any"),
    ],
)
def test_infer_type(raw, expected):
    assert envelope.infer_type(raw) == expected


def test_coerce_passes_envelope_through():
    env = {"type": "file", "data": "purrcat://a"}
    assert envelope.coerce(env) is env


def test_coerce_prefers_single_declared_port_type():
    assert envelope.coerce(1, "number") == {"type": "number", "data": 1}
    assert envelope.coerce(1, ["number"]) == {"type": "number", "data": 1}


def test_coerce_falls_back_to_inference_for_unions_and_any():
    assert envelope.coerce("x", ["string", "file"])["type"] == "string"
    assert envelope.coerce("x", "any")["type"] == "string"
    assert envelope.coerce({"a": 1})["type"] == "any"


@pytest.mark.parametrize(
    ("allowed", "expected"),
    [
        (None, ["any"]),
        ("string", ["string"]),
        (["string", "file"], ["string", "file"]),
        ([], ["any"]),
        ([1, 2], ["1", "2"]),
    ],
)
def test_normalize_allowed(allowed, expected):
    assert envelope.normalize_allowed(allowed) == expected


def test_check_allows_any_port_and_exact_type():
    assert envelope.check({"type": "file", "data": "purrcat://a"}, None) == (True, "")
    assert envelope.check({"type": "string", "data": "x"}, "string") == (True, "")


def test_check_keeps_bidirectional_compatibility_rules():
    # list 与 MessageList、string 与 jsonstring 互为兼容子类型
    assert envelope.check({"type": "MessageList", "data": []}, "list")[0]
    assert envelope.check({"type": "list", "data": []}, "MessageList")[0]
    assert envelope.check({"type": "jsonstring", "data": "{}"}, "string")[0]
    assert envelope.check({"type": "string", "data": "{}"}, "jsonstring")[0]


def test_check_reports_incompatibility_with_port_and_actual_type():
    ok, reason = envelope.check({"type": "file", "data": "u"}, ["string"])
    assert not ok
    assert "['string']" in reason
    assert "file" in reason


def test_check_infers_bare_value_type():
    ok, reason = envelope.check("x", ["number"])
    assert not ok
    assert "string" in reason


def test_to_task_uri_format():
    assert (
        envelope.to_task_uri("/tmp/ckpt", "n1", "a.txt")
        == "purrcat://task/node/n1/files/a.txt"
    )


@pytest.fixture
def graphs_dir(tmp_path, monkeypatch):
    target = tmp_path / "graphs"
    target.mkdir()
    monkeypatch.setattr("src.utils.config.GRAPHS_DIR", str(target))
    return target


def test_parse_graph_asset_uri(graphs_dir):
    path = envelope.parse_uri("purrcat://graph/demo/asset/a.txt")
    assert path == (graphs_dir / "demo" / "asset" / "a.txt").resolve()


def test_parse_graph_uri_blocks_path_traversal(graphs_dir):
    assert envelope.parse_uri("purrcat://graph/demo/../../etc/passwd") is None


def test_parse_task_uri_requires_checkpoint_dir(tmp_path):
    uri = "purrcat://task/node/n1/files/a.txt"
    assert envelope.parse_uri(uri) is None
    assert (
        envelope.parse_uri(uri, checkpoint_dir=str(tmp_path))
        == (tmp_path / "nodes" / "n1" / "files" / "a.txt").resolve()
    )


def test_parse_task_uri_supports_legacy_shape(tmp_path):
    path = envelope.parse_uri(
        "purrcat://task/t1/node/n2/files/b.txt", checkpoint_dir=str(tmp_path)
    )
    assert path == (tmp_path / "nodes" / "n2" / "files" / "b.txt").resolve()


def test_parse_uri_handles_plain_paths_and_invalid_input(tmp_path):
    absolute = tmp_path / "a.txt"
    assert envelope.parse_uri(str(absolute)) == absolute
    assert envelope.parse_uri("relative/a.txt") is None
    assert envelope.parse_uri("") is None
    assert envelope.parse_uri(None) is None
    assert envelope.parse_uri(123) is None
    assert envelope.parse_uri("purrcat://unknown/x") is None


def test_parse_uri_absolute_path_keeps_user_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert envelope.parse_uri("~/a.txt") == tmp_path / "a.txt"
    assert os.path.isabs(envelope.parse_uri(str(tmp_path / "b.txt")))
