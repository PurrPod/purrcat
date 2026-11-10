"""DAG 节点的输入组装与输出落盘（信封化、类型校验、大文件剥离）。"""

from __future__ import annotations

import json
import os
from typing import Callable

from . import envelope
from .enums import PortState

# 大内容剥离阈值：声明为 file 的端口，data 超过此长度自动落盘
FILE_STRIP_THRESHOLD = 4096

MIME_EXT = {
    "text/html": ".html",
    "image/svg+xml": ".svg",
    "text/markdown": ".md",
    "text/plain": ".txt",
    "application/pdf": ".pdf",
    "application/json": ".json",
}


def node_dir(checkpoint_dir: str, node_id: str) -> str:
    return os.path.join(checkpoint_dir, "nodes", node_id)


def outputs_path(checkpoint_dir: str, node_id: str) -> str:
    return os.path.join(node_dir(checkpoint_dir, node_id), "outputs.json")


def read_node_outputs(checkpoint_dir: str, node_id: str) -> dict:
    path = outputs_path(checkpoint_dir, node_id)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_node_inputs(
    *,
    checkpoint_dir: str,
    graph: dict,
    output_port_states: dict,
    node_id: str,
    declared_type: Callable[[str, str, str], str | None],
    log: Callable[[str, str, str], None] | None = None,
) -> dict:
    """纯文件指针推导：从上游 outputs.json 组装 input，并做信封类型硬校验。"""
    inputs = {}
    edges = [e for e in graph.get("edges", []) if e["target"] == node_id]
    for edge in edges:
        src_id = edge["source"]
        src_port = edge.get("sourceHandle", "default")
        tgt_port = edge.get("targetHandle", "default")

        if output_port_states.get(src_id, {}).get(src_port) != PortState.HAS_DATA:
            continue

        try:
            src_data = read_node_outputs(checkpoint_dir, src_id)
            if src_port not in src_data:
                continue

            # 裸值（旧 checkpoint）惰性包装为信封
            declared = declared_type(node_id, "inputs", tgt_port)
            env = envelope.coerce(src_data[src_port], declared)
            # 引擎硬校验：any 万能，union 支持交集
            ok, err = envelope.check(env, declared)
            if not ok:
                raise ValueError(f"端口 [{tgt_port}] {err}")
            inputs[tgt_port] = env
        except ValueError:
            raise
        except Exception as e:
            if log:
                log("ERROR", f"读取上游 {src_id} 数据失败: {e}", node_id)
    return inputs


def save_node_outputs(
    *,
    checkpoint_dir: str,
    node_id: str,
    result: dict,
    declared_type: Callable[[str], str | None],
    log: Callable[[str, str, str], None] | None = None,
    strip_threshold: int = FILE_STRIP_THRESHOLD,
) -> None:
    """节点输出按端口 schema 包装为信封落盘；file 端口大内容自动剥离为文件。"""
    if not result:
        return

    out_dir = node_dir(checkpoint_dir, node_id)
    os.makedirs(out_dir, exist_ok=True)

    packed = {}
    for port, raw in result.items():
        declared = declared_type(port)
        env = envelope.coerce(raw, declared)
        # 声明为 file 且 data 是超大内联字符串 → 剥离到节点 files/ 目录
        if (
            declared == "file"
            and env.get("type") not in ("file",)
            and isinstance(env.get("data"), str)
            and len(env["data"]) > strip_threshold
        ):
            mime = env.get("mime", "text/plain")
            ext = MIME_EXT.get(mime, ".txt")
            files_dir = os.path.join(out_dir, "files")
            os.makedirs(files_dir, exist_ok=True)
            fname = f"{port}{ext}"
            with open(os.path.join(files_dir, fname), "w", encoding="utf-8") as f:
                f.write(env["data"])
            uri = envelope.to_task_uri(checkpoint_dir, node_id, fname)
            env = envelope.make("file", uri, mime, {"bytes": len(env["data"])})
        packed[port] = env

    try:
        with open(outputs_path(checkpoint_dir, node_id), "w", encoding="utf-8") as f:
            json.dump(packed, f, ensure_ascii=False)
    except Exception as e:
        if log:
            log("ERROR", f"节点结果落盘失败: {e}", node_id)
