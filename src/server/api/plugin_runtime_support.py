"""插件后端子进程运行时的纯辅助：进程定位、依赖指纹与就绪判定。

不做进程启动，便于用 tmp_path 直接单测。
"""

from __future__ import annotations

import hashlib
import json
import os

# 允许出现的 backend 启动器类型
NODE = "node"

# 继承父进程环境时剥离的 venv 变量，避免 uv/pyenv 干扰子进程解释器定位
_VENV_ENV_PREFIXES = (
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
)


class PluginProcessError(Exception):
    """插件进程层错误（找不到解释器/启动失败/超时/未就绪等）。"""


def strip_venv_env(env: dict) -> dict:
    """复制环境变量并去掉 venv 相关项。"""
    return {k: v for k, v in env.items() if not k.startswith(_VENV_ENV_PREFIXES)}


def locate_plugin_entry(plugin_dir: str) -> tuple[str, str, str]:
    """根据插件目录定位 backend -> (cwd, entry_abs, runner)。"""
    plugin_dir = os.path.abspath(plugin_dir)
    backend_file = os.path.join(plugin_dir, "server", "server.js")
    if os.path.isfile(backend_file):
        return plugin_dir, backend_file, NODE
    raise PluginProcessError(
        f"插件 {os.path.basename(plugin_dir)} 无后端（缺少 server/server.js）"
    )


def hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deps_fingerprint(server_dir: str) -> str:
    """package.json 与 lockfile 的内容指纹；任一变化即视为需要重装。"""
    parts = []
    for name in ("package.json", "package-lock.json", "npm-shrinkwrap.json"):
        path = os.path.join(server_dir, name)
        if os.path.isfile(path):
            parts.append(f"{name}:{hash_file(path)}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def has_runtime_deps(server_dir: str) -> bool:
    """package.json 是否声明了运行时依赖（devDependencies 已在安装时排除）。"""
    try:
        with open(os.path.join(server_dir, "package.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
        deps = data.get("dependencies") if isinstance(data, dict) else None
        return bool(isinstance(deps, dict) and deps)
    except Exception:
        return False


def deps_ready(server_dir: str, fingerprint: str, state: dict) -> bool:
    if state.get("fingerprint") != fingerprint:
        return False
    if os.path.isdir(os.path.join(server_dir, "node_modules")):
        return True
    # 没有依赖时 npm 不会生成 node_modules，指纹一致即视为就绪。
    return not has_runtime_deps(server_dir)
