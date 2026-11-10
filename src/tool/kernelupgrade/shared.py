"""KernelUpgrade 各 action 模块共享的常量与工具函数"""

import os

# action × type 全矩阵：create/upgrade 建沙盒，install 从市场/URL 落正式区，
# merge/test 由本工具代发 Request（Agent 不再直接向 Request 传 test/merge）。
ACTIONS = ("create", "upgrade", "install", "merge", "test")
TYPES = ("skill", "mcp", "sensor", "graph", "agentloop", "ui-plugin")

# 合并请求类型映射（ui-plugin 无合并概念：直接写盘即生效）
MERGE_REQUEST_TYPES = {
    "skill": "skill_merge",
    "mcp": "mcp_merge",
    "sensor": "sensor_merge",
    "agentloop": "agentloop_merge",
    "graph": "graph_merge",
}


def market():
    """懒加载插件市场的落地实现（复用 src/server/api/tools.py 已有的下载/安装能力）"""
    from src.server.api import tools

    return tools


def data_root() -> str:
    from src.utils.config import DATA_ROOT

    return DATA_ROOT


def normalize_target(target: str) -> str:
    """剥掉 Agent 常给 URL/配置串加的反引号或引号。"""
    return (target or "").strip().strip("`\"'").strip()


def is_url(target: str) -> bool:
    return target.startswith(("http://", "https://"))


def resolve_agent_vm_path(path: str) -> str:
    """兼容沙盒视角的 /agent_vm 前缀路径。"""
    from src.utils.config import AGENT_VM_DIR

    p = path.replace("\\", "/")
    if p.startswith("/agent_vm/"):
        return os.path.join(AGENT_VM_DIR, p[len("/agent_vm/") :])
    return path


def parse_workplace_target(
    target: str, *, strip: bool = False
) -> tuple[str, str] | None:
    """解析 `uuid/名字`；strip=True 时逐段去空白，兼容手写空格。"""
    parts = [p.strip() for p in target.split("/")] if strip else target.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return parts[0], parts[1]


def record_trace_meta(workplace_id: str):
    """trace2skill：记录来源会话的 Token 快照，供后续盲测报告对比"省下多少 token" """
    if not workplace_id:
        return
    try:
        from src.agent.manager import manager
        from src.evolve import record_trace_meta as _record

        _record(workplace_id, manager.get_active_session_id())
    except Exception:
        pass
