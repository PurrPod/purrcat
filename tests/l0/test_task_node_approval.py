"""人工审核节点批准记录的落盘与读取（SPEC-028）。"""

from __future__ import annotations

from pathlib import Path

from src.harness.task_persistence import (
    approval_path,
    clear_node_approval,
    mark_node_approved,
    read_node_approvals,
)


def test_mark_and_read_approval(tmp_path):
    assert mark_node_approved(str(tmp_path), "review_1") is True

    path = Path(approval_path(str(tmp_path), "review_1"))
    assert path.is_file()
    assert path.name == "approval.json"

    approvals = read_node_approvals(str(tmp_path))
    assert approvals["review_1"]


def test_mark_is_idempotent(tmp_path):
    mark_node_approved(str(tmp_path), "review_1")
    first = read_node_approvals(str(tmp_path))

    assert mark_node_approved(str(tmp_path), "review_1") is False
    assert read_node_approvals(str(tmp_path)) == first


def test_read_returns_empty_without_nodes_dir(tmp_path):
    assert read_node_approvals(str(tmp_path)) == {}


def test_clear_removes_only_target_approval(tmp_path):
    mark_node_approved(str(tmp_path), "review_1")
    mark_node_approved(str(tmp_path), "review_2")

    clear_node_approval(str(tmp_path), "review_1")

    approvals = read_node_approvals(str(tmp_path))
    assert "review_1" not in approvals
    assert "review_2" in approvals


def test_read_skips_broken_approval_file(tmp_path):
    broken = Path(approval_path(str(tmp_path), "review_1"))
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("not json", encoding="utf-8")

    assert read_node_approvals(str(tmp_path)) == {}
