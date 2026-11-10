"""工具市场薄入口：保留历史导入名，实现分散在三个同包模块。

- market_archive：远程下载、zip 解包、SKILL.md 与解压目标校验；
- market_install：配置合并、按名安装、依赖补齐与卸载编排；
- market_state：注册表查询、缺失判定与卸载决策。

路由层（tools.py）只从这里取入口，避免依赖具体实现文件。
"""

from __future__ import annotations

from src.server.api.market_archive import (
    download_official_mcp_source,
    download_skill_from_github,
    extract_skill_from_zip,
    fetch_repo_zip,
    http_download,
    http_get_json,
)
from src.server.api.market_install import (
    ensure_graph_mcp_deps,
    ensure_graph_skill_deps,
    ensure_market_dep,
    install_agentloop_by_name,
    install_graph,
    install_graph_by_name,
    install_mcp_config,
    install_sensor,
    install_sensor_by_name,
    install_skills_batch,
    install_ui_plugin_by_name,
    install_ui_plugin_entry,
    uninstall_mcp,
)

__all__ = [
    "download_official_mcp_source",
    "download_skill_from_github",
    "ensure_graph_mcp_deps",
    "ensure_graph_skill_deps",
    "ensure_market_dep",
    "extract_skill_from_zip",
    "fetch_repo_zip",
    "http_download",
    "http_get_json",
    "install_agentloop_by_name",
    "install_graph",
    "install_graph_by_name",
    "install_mcp_config",
    "install_sensor",
    "install_sensor_by_name",
    "install_skills_batch",
    "install_ui_plugin_by_name",
    "install_ui_plugin_entry",
    "uninstall_mcp",
]
