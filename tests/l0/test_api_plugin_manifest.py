"""插件清单扫描、路径校验与依赖就绪判定的 L0 用例（SPEC-021）。"""

from __future__ import annotations

import json

import pytest

from src.server.api import plugin_runtime_support, webmin_scan


def _write_plugin(root, name: str, plugin_id: str, extra: dict | None = None):
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    data = {"id": plugin_id, "name": plugin_id}
    data.update(extra or {})
    (plugin_dir / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    return plugin_dir


# ── 清单解析 ──


def test_scan_plugins_skips_trash_and_invalid_descriptors(tmp_path):
    """SPEC-021：只收录含合法 plugin.json 的目录，.trash 与坏 JSON 跳过。"""
    root = tmp_path / "plugins"
    valid = _write_plugin(root, "valid", "p1", {"name": "Valid"})
    _write_plugin(root, "removed.trash", "p2")
    bad = root / "bad"
    bad.mkdir()
    (bad / "plugin.json").write_text("{not-json", encoding="utf-8")
    (root / "loose.txt").write_text("x", encoding="utf-8")

    out = webmin_scan.scan_plugins(str(root))

    assert list(out) == ["p1"]
    assert out["p1"]["name"] == "Valid"
    assert out["p1"]["dir"] == str(valid)


def test_scan_plugin_roots_merges_user_over_sandbox_over_builtin(tmp_path):
    """SPEC-021：多根扫描按低到高优先级覆盖同名插件。"""
    builtin = tmp_path / "builtin"
    sandbox = tmp_path / "sandbox"
    user = tmp_path / "user"
    _write_plugin(builtin, "p", "p", {"name": "builtin"})
    _write_plugin(sandbox, "p", "p", {"name": "sandbox"})
    _write_plugin(user, "p", "p", {"name": "user"})
    _write_plugin(builtin, "only", "only", {"name": "only"})

    out = webmin_scan.scan_plugin_roots((str(builtin), str(sandbox), str(user)))

    assert out["p"]["name"] == "user"
    assert out["only"]["name"] == "only"


# ── 静态资源路径校验 ──


def test_resolve_plugin_file_is_sandboxed_to_plugin_dir(tmp_path):
    """SPEC-021：插件文件定位禁止 ../ 穿越，未命中返回 None。"""
    root = tmp_path / "plugins"
    plugin_dir = _write_plugin(root, "p1", "p1")
    (plugin_dir / "assets").mkdir()
    (plugin_dir / "assets" / "a.js").write_text("x", encoding="utf-8")
    (tmp_path / "escape.txt").write_text("x", encoding="utf-8")

    roots = (str(root),)

    assert webmin_scan.resolve_plugin_file("p1", "assets/a.js", roots) == str(
        plugin_dir / "assets" / "a.js"
    )
    assert webmin_scan.resolve_plugin_file("p1", "../escape.txt", roots) is None
    assert webmin_scan.resolve_plugin_file("p1", "missing.js", roots) is None
    assert webmin_scan.resolve_plugin_file("../p1", "plugin.json", roots) is None


def test_resolve_plugin_subdir_and_dir_priority(tmp_path):
    """SPEC-021：目录定位同样沙箱化，插件目录按根顺序优先。"""
    user = tmp_path / "user"
    builtin = tmp_path / "builtin"
    user_plugin = _write_plugin(user, "p1", "p1")
    _write_plugin(builtin, "p1", "p1")
    (user_plugin / "data").mkdir()

    roots = (str(user), str(builtin))

    assert webmin_scan.resolve_plugin_subdir("p1", "data", roots) == str(
        user_plugin / "data"
    )
    assert webmin_scan.resolve_plugin_subdir("p1", "../", roots) is None
    assert webmin_scan.resolve_plugin_dir("p1", roots) == str(user_plugin)
    assert webmin_scan.resolve_plugin_dir("missing", roots) is None


def test_plugin_backend_info_detects_server_entry(tmp_path):
    """SPEC-021：只有 server/server.js 存在才报告 npm 后端。"""
    plugin_dir = tmp_path / "p1"
    (plugin_dir / "server").mkdir(parents=True)
    assert webmin_scan.plugin_backend_info(str(plugin_dir)) is None

    (plugin_dir / "server" / "server.js").write_text("// x", encoding="utf-8")
    assert webmin_scan.plugin_backend_info(str(plugin_dir)) == {"kind": "npm"}


# ── 后端进程与依赖就绪 ──


def test_locate_plugin_entry_requires_server_js(tmp_path):
    """SPEC-021：后端定位只认 server/server.js，缺失时抛进程层错误。"""
    plugin_dir = tmp_path / "p1"
    plugin_dir.mkdir()

    with pytest.raises(plugin_runtime_support.PluginProcessError) as exc:
        plugin_runtime_support.locate_plugin_entry(str(plugin_dir))
    assert "server/server.js" in str(exc.value)

    backend = plugin_dir / "server" / "server.js"
    backend.parent.mkdir()
    backend.write_text("// x", encoding="utf-8")
    cwd, entry, runner = plugin_runtime_support.locate_plugin_entry(str(plugin_dir))

    assert cwd == str(plugin_dir.resolve())
    assert entry == str(backend.resolve())
    assert runner == "node"


def test_deps_ready_requires_matching_fingerprint_and_node_modules(tmp_path):
    """SPEC-021：指纹不符一律未就绪；有运行时依赖时必须存在 node_modules。"""
    server = tmp_path / "server"
    server.mkdir()
    (server / "package.json").write_text(
        json.dumps({"dependencies": {"left-pad": "1.0.0"}}), encoding="utf-8"
    )
    fingerprint = plugin_runtime_support.deps_fingerprint(str(server))

    assert not plugin_runtime_support.deps_ready(
        str(server), fingerprint, {"fingerprint": "other"}
    )
    assert not plugin_runtime_support.deps_ready(
        str(server), fingerprint, {"fingerprint": fingerprint}
    )

    (server / "node_modules").mkdir()
    assert plugin_runtime_support.deps_ready(
        str(server), fingerprint, {"fingerprint": fingerprint}
    )


def test_deps_ready_allows_dependency_free_plugin(tmp_path):
    """SPEC-021：无运行时依赖时 npm 不生成 node_modules，指纹一致即可就绪。"""
    server = tmp_path / "server"
    server.mkdir()
    (server / "package.json").write_text(
        json.dumps({"devDependencies": {"vite": "1.0.0"}}), encoding="utf-8"
    )
    fingerprint = plugin_runtime_support.deps_fingerprint(str(server))

    assert plugin_runtime_support.deps_ready(
        str(server), fingerprint, {"fingerprint": fingerprint}
    )


def test_deps_fingerprint_tracks_package_and_lockfile(tmp_path):
    """SPEC-021：package.json 或 lockfile 任一变化都会改变指纹。"""
    server = tmp_path / "server"
    server.mkdir()
    package = server / "package.json"
    package.write_text(json.dumps({"dependencies": {"a": "1"}}), encoding="utf-8")
    first = plugin_runtime_support.deps_fingerprint(str(server))

    package.write_text(json.dumps({"dependencies": {"a": "2"}}), encoding="utf-8")
    second = plugin_runtime_support.deps_fingerprint(str(server))
    assert second != first

    (server / "package-lock.json").write_text("{}", encoding="utf-8")
    assert plugin_runtime_support.deps_fingerprint(str(server)) != second


def test_strip_venv_env_removes_python_and_venv_vars():
    """SPEC-021：子进程环境保留 PATH，但剥离 venv/PYTHON 相关变量。"""
    env = {
        "PATH": "/bin",
        "VIRTUAL_ENV": "/venv",
        "PYTHONPATH": "/x",
        "PYTHONHOME": "/h",
        "HOME": "/home",
    }

    assert plugin_runtime_support.strip_venv_env(env) == {
        "PATH": "/bin",
        "HOME": "/home",
    }
