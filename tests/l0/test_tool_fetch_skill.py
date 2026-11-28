"""Fetch 技能加载的目录重建（skill_fetch）。"""

from __future__ import annotations

from src.tool.fetch import skill_fetch


def test_force_rmtree_onexc_callback_accepts_three_args(tmp_path, monkeypatch):
    """rmtree 的 onexc 回调必须接收 (func, path, exc)，否则删除失败时会抛 TypeError。"""
    target = tmp_path / "skill_dir"
    target.mkdir()
    retried = []

    def fake_rmtree(path, onexc=None, **_kwargs):
        # 模拟删除时遇到只读/占用文件：rmtree 会以三元组调用 onexc
        onexc(lambda p: retried.append(p), str(target), PermissionError("locked"))

    monkeypatch.setattr(skill_fetch.shutil, "rmtree", fake_rmtree)

    skill_fetch._force_rmtree(str(target))

    assert retried == [str(target)]
