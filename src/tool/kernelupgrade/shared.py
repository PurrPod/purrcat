"""KernelUpgrade 各 action 模块共享的常量与工具函数"""

# action × type 全矩阵：create/upgrade 建沙盒，merge/test 由本工具代发 Request
# （Agent 不再直接向 Request 传 test/merge）。
ACTIONS = ("create", "upgrade", "merge", "test")
TYPES = ("skill", "mcp", "sensor", "graph", "agentloop", "ui-plugin")

# 合并请求类型映射（ui-plugin 无合并概念：直接写盘即生效）
MERGE_REQUEST_TYPES = {
    "skill": "skill_merge",
    "mcp": "mcp_merge",
    "sensor": "sensor_merge",
    "agentloop": "agentloop_merge",
    "graph": "graph_merge",
}


def data_root() -> str:
    from src.utils.config import DATA_ROOT

    return DATA_ROOT


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
