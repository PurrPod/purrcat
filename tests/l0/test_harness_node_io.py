"""节点输入组装与输出落盘（SPEC-008）。"""

from __future__ import annotations

import json

import pytest

from src.harness.enums import PortState
from src.harness.node_io import (
    build_node_inputs,
    read_node_outputs,
    save_node_outputs,
)


def _graph():
    return {
        "edges": [
            {
                "source": "up",
                "target": "down",
                "sourceHandle": "out",
                "targetHandle": "in",
            }
        ]
    }


def _write_upstream(checkpoint_dir, payload):
    node_dir = checkpoint_dir / "nodes" / "up"
    node_dir.mkdir(parents=True)
    (node_dir / "outputs.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_build_node_inputs_reads_has_data_upstream(tmp_path):
    _write_upstream(tmp_path, {"out": {"type": "string", "data": "hi"}})

    inputs = build_node_inputs(
        checkpoint_dir=str(tmp_path),
        graph=_graph(),
        output_port_states={"up": {"out": PortState.HAS_DATA}},
        node_id="down",
        declared_type=lambda node, direction, port: "string",
    )

    assert inputs == {"in": {"type": "string", "data": "hi"}}


def test_build_node_inputs_skips_pending_and_missing_ports(tmp_path):
    _write_upstream(tmp_path, {"other": {"type": "string", "data": "hi"}})

    inputs = build_node_inputs(
        checkpoint_dir=str(tmp_path),
        graph=_graph(),
        output_port_states={"up": {"out": PortState.PENDING}},
        node_id="down",
        declared_type=lambda node, direction, port: "string",
    )

    assert inputs == {}


def test_build_node_inputs_raises_on_type_mismatch(tmp_path):
    _write_upstream(tmp_path, {"out": {"type": "number", "data": 1}})

    with pytest.raises(ValueError, match="类型不兼容"):
        build_node_inputs(
            checkpoint_dir=str(tmp_path),
            graph=_graph(),
            output_port_states={"up": {"out": PortState.HAS_DATA}},
            node_id="down",
            declared_type=lambda node, direction, port: "string",
        )


def test_build_node_inputs_propagates_corrupt_upstream_json(tmp_path):
    upstream = tmp_path / "nodes" / "up"
    upstream.mkdir(parents=True)
    (upstream / "outputs.json").write_text("{broken", encoding="utf-8")

    # JSONDecodeError 是 ValueError 子类，按原逻辑应向上抛出
    with pytest.raises(ValueError):
        build_node_inputs(
            checkpoint_dir=str(tmp_path),
            graph=_graph(),
            output_port_states={"up": {"out": PortState.HAS_DATA}},
            node_id="down",
            declared_type=lambda node, direction, port: "string",
        )


def test_build_node_inputs_logs_non_value_errors_and_continues(tmp_path):
    upstream = tmp_path / "nodes" / "up" / "outputs.json"
    upstream.mkdir(parents=True)
    logs = []

    inputs = build_node_inputs(
        checkpoint_dir=str(tmp_path),
        graph=_graph(),
        output_port_states={"up": {"out": PortState.HAS_DATA}},
        node_id="down",
        declared_type=lambda node, direction, port: "string",
        log=lambda *args: logs.append(args),
    )

    assert inputs == {}
    assert logs and "读取上游 up 数据失败" in logs[0][1]


def test_save_node_outputs_wraps_envelopes(tmp_path):
    save_node_outputs(
        checkpoint_dir=str(tmp_path),
        node_id="n1",
        result={"out": "hello"},
        declared_type=lambda port: "string",
    )

    assert read_node_outputs(str(tmp_path), "n1") == {
        "out": {"type": "string", "data": "hello"}
    }


def test_save_node_outputs_strips_large_file_port(tmp_path):
    save_node_outputs(
        checkpoint_dir=str(tmp_path),
        node_id="n1",
        result={"out": {"type": "string", "data": "x" * 20}},
        declared_type=lambda port: "file",
        strip_threshold=10,
    )

    saved = read_node_outputs(str(tmp_path), "n1")["out"]
    assert saved["type"] == "file"
    assert saved["data"] == "purrcat://task/node/n1/files/out.txt"
    stored = tmp_path / "nodes" / "n1" / "files" / "out.txt"
    assert stored.read_text(encoding="utf-8") == "x" * 20


def test_save_node_outputs_ignores_empty_result(tmp_path):
    save_node_outputs(
        checkpoint_dir=str(tmp_path),
        node_id="n1",
        result={},
        declared_type=lambda port: "string",
    )

    assert read_node_outputs(str(tmp_path), "n1") == {}
