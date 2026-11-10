"""工具市场下载/解压/依赖决策/卸载回滚的 L0 用例（SPEC-021）。"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import HTTPException

from src.server.api import market_archive, market_install, market_state


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ── 下载候选 ──


def test_fetch_repo_zip_probes_default_branch_then_fallback(monkeypatch):
    """SPEC-021：裸仓库链接先试探测到的默认分支，失败再按候选兜底。"""
    calls = []
    monkeypatch.setattr(
        market_archive,
        "http_get_json",
        lambda url, timeout=15: {"default_branch": "trunk"},
    )

    def fake_download(url, timeout=15):
        calls.append(url)
        if len(calls) == 1:
            raise OSError("boom")
        return b"ZIP"

    monkeypatch.setattr(market_archive, "http_download", fake_download)

    assert market_archive.fetch_repo_zip("o", "r", "") == b"ZIP"
    assert calls[0].endswith("/refs/heads/trunk.zip")
    assert calls[1].endswith("/refs/heads/main.zip")


def test_fetch_repo_zip_uses_explicit_branch_only(monkeypatch):
    """SPEC-021：显式分支只尝试该分支，不触发默认分支探测。"""
    calls = []
    monkeypatch.setattr(
        market_archive,
        "http_get_json",
        lambda *a, **k: pytest.fail("显式分支不应探测默认分支"),
    )
    monkeypatch.setattr(
        market_archive,
        "http_download",
        lambda url, timeout=15: calls.append(url) or b"ZIP",
    )

    assert market_archive.fetch_repo_zip("o", "r", "dev") == b"ZIP"
    assert len(calls) == 1
    assert calls[0].endswith("/refs/heads/dev.zip")


# ── 解压目标 ──


def test_skill_archive_path_helpers():
    """SPEC-021：skill 名与前缀计算固定，根目录即仓库时用仓库名。"""
    assert market_archive.skill_name_from_path("repo", "") == "repo"
    assert market_archive.skill_name_from_path("repo", "skills/demo") == "demo"
    assert market_archive.skill_archive_prefix("repo-main", "") == "repo-main/"
    assert market_archive.skill_archive_prefix("repo-main", "a/b/") == "repo-main/a/b/"


def test_extract_skill_writes_only_target_subdir(tmp_path, monkeypatch):
    """SPEC-021：只解压目标子目录，覆盖式重装并保留相对路径。"""
    monkeypatch.setattr(market_archive, "SKILL_DIR", str(tmp_path))
    stale = tmp_path / "demo" / "stale.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("old", encoding="utf-8")

    data = _zip_bytes(
        {
            "repo-main/skills/demo/SKILL.md": b"# demo",
            "repo-main/skills/demo/sub/a.txt": b"a",
            "repo-main/other.txt": b"x",
        }
    )

    assert market_archive.extract_skill_from_zip(data, "repo", "skills/demo") == "demo"
    assert (tmp_path / "demo" / "SKILL.md").read_text(encoding="utf-8") == "# demo"
    assert (tmp_path / "demo" / "sub" / "a.txt").read_text(encoding="utf-8") == "a"
    assert not (tmp_path / "demo" / "other.txt").exists()
    assert not stale.exists()


def test_extract_skill_rejects_missing_skill_md(tmp_path, monkeypatch):
    """SPEC-021：目标目录缺少 SKILL.md 时按原语义返回 400。"""
    monkeypatch.setattr(market_archive, "SKILL_DIR", str(tmp_path))
    data = _zip_bytes({"repo-main/skills/demo/readme.md": b"x"})

    with pytest.raises(HTTPException) as exc:
        market_archive.extract_skill_from_zip(data, "repo", "skills/demo")

    assert exc.value.status_code == 400
    assert "SKILL.md" in exc.value.detail


# ── 依赖补齐决策 ──


def test_missing_names_respects_case_mode():
    """SPEC-021：MCP 配置键大小写敏感，Skill 目录名按小写比较。"""
    assert market_state.missing_names(["a", "B", "a", ""], {"a"}) == ["B"]
    assert market_state.missing_names(["A", "b", "c"], {"a"}, ignore_case=True) == [
        "b",
        "c",
    ]


def test_registry_entry_extraction_accepts_dict_and_list():
    """SPEC-021：MCP 注册表兼容 dict 与裸数组；Skill 仅识别 skills 字典。"""
    assert market_state.mcp_registry_entries({"mcps": {"a": {"name": "a"}}}) == [
        {"name": "a"}
    ]
    assert market_state.mcp_registry_entries([{"name": "a"}]) == [{"name": "a"}]
    assert market_state.skill_registry_items({"skills": {"a": {"name": "a"}}}) == [
        ("a", {"name": "a"})
    ]
    assert market_state.skill_registry_items([{"name": "a"}]) == []


def test_resolve_mcp_dependencies_merges_and_skips_missing():
    """SPEC-021：命中市场条目则合并 servers 并记录 repo，缺失项只留说明。"""
    entries = [
        {
            "name": "alpha",
            "mcpServers": {"alpha": {"command": "x"}},
            "repo": "https://github.com/PurrPod/mcps",
        },
        {"name": "beta", "mcpServers": {}},
    ]

    merged, pairs, notes = market_state.resolve_mcp_dependencies(
        entries, ["alpha", "missing", "beta"]
    )

    assert merged == {"alpha": {"command": "x"}}
    assert pairs == [("https://github.com/PurrPod/mcps", ["alpha"])]
    assert notes == [
        "MCP 'missing' 本地与市场均缺失，已跳过",
        "MCP 'beta' 本地与市场均缺失，已跳过",
    ]


def test_resolve_skill_install_plan_keeps_links_and_missing_notes():
    """SPEC-021：Skill 有下载链接才进计划，市场缺失只记录跳过说明。"""
    items = [
        ("alpha", {"name": "alpha", "skill-single-link": "https://github.com/o/r"}),
        ("beta", {"name": "beta"}),
    ]

    plan, notes = market_state.resolve_skill_install_plan(
        items, ["alpha", "beta", "gamma"]
    )

    assert plan == [("alpha", "https://github.com/o/r")]
    assert notes == [
        "Skill 'beta' 本地与市场均缺失，已跳过",
        "Skill 'gamma' 本地与市场均缺失，已跳过",
    ]


def test_required_files_puts_core_manifest_first():
    """SPEC-021：注册表文件清单去空值，核心描述文件固定排首位。"""
    assert market_state.required_files(None, "graph.json") == ["graph.json"]
    assert market_state.required_files(["a", "graph.json", " "], "graph.json") == [
        "a",
        "graph.json",
    ]
    assert market_state.required_files(["a"], "graph.json") == ["graph.json", "a"]


# ── 卸载回滚 ──


def test_drop_mcp_server_removes_entry_or_raises_404():
    """SPEC-021：卸载只删指定 Server；未配置时按原语义返回 404。"""
    config = {"mcpServers": {"a": {"command": "x"}, "b": {}}}

    assert market_state.drop_mcp_server(config, "a") == {"mcpServers": {"b": {}}}
    with pytest.raises(HTTPException) as exc:
        market_state.drop_mcp_server(config, "missing")
    assert exc.value.status_code == 404


def test_uninstall_mcp_rewrites_config_and_cleans_source(tmp_path, monkeypatch):
    """SPEC-021：卸载回滚会重写 mcp_config.json 并删除官方源码目录。"""
    config_path = tmp_path / "mcp_config.json"
    source_root = tmp_path / "mcps"
    (source_root / "demo").mkdir(parents=True)

    monkeypatch.setattr(
        market_install, "get_mcp_config", lambda: {"mcpServers": {"demo": {"c": 1}}}
    )
    monkeypatch.setattr(market_install, "MCP_CONFIG_PATH", str(config_path))
    monkeypatch.setattr(market_install, "MCP_SOURCE_DIR", str(source_root))
    monkeypatch.setattr(market_install, "refresh_schemas", lambda: [])
    monkeypatch.setattr(
        market_install,
        "MCPSearcher",
        lambda: type("_S", (), {"reload_index": lambda s: None})(),
    )
    monkeypatch.setattr(market_install, "rebuild_vectors_async", lambda: None)

    market_install.uninstall_mcp("demo")

    assert json.loads(config_path.read_text(encoding="utf-8")) == {"mcpServers": {}}
    assert not (source_root / "demo").exists()
