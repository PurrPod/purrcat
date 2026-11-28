"""KernelUpgrade(action='upgrade')：把正式区的对象（含配置）搬进沙盒"""

import os
import shutil

from src.tool.utils.format import error_response, text_response
from src.evolve import (
    skill_improve_init,
    mcp_upgrade_init,
    sensor_factory_init,
    agentloop_factory_init,
    graph_factory_init,
)
from .shared import data_root, record_trace_meta


def upgrade_module(t: str, target: str) -> dict:
    if t == "skill":
        sys_note, workplace_id = skill_improve_init(target, is_upgrade=True)
        record_trace_meta(workplace_id)
        if not workplace_id:
            return error_response(sys_note, "Skill 升级失败")
        return text_response(
            f"{target} 技能沙盒已就绪！\n\n{sys_note}",
            f"{target} 技能沙盒已就绪",
        )

    if t == "mcp":
        # 只有落在受管目录（~/.purrcat/mcps）里的 MCP 才有源码可拷；
        # 外部下载型 MCP（仅注册在 mcp_config.json，源码不在受管目录）无法升级。
        managed_dir = os.path.join(data_root(), "mcps", target)
        if not os.path.isdir(managed_dir):
            return error_response(
                f"无法升级 MCP '{target}'：受管源码目录 {managed_dir} 不存在。\n\n"
                "只有源码由本系统落地到受管 mcps 目录（官方市场安装或经 KernelUpgrade 合并过）"
                "的 MCP 才支持沙盒升级；从外部自行下载/仅配置在 mcp_config.json 里的 MCP 没有受管源码，"
                "无法搬入沙盒。若需改动它，请改为新建一个受管 MCP。",
                "无可升级的受管 MCP 源码",
            )
        sys_note, workplace_id = mcp_upgrade_init(target)
        if not workplace_id:
            return error_response(sys_note, "MCP 升级失败")
        return text_response(
            f"{target} MCP沙盒已就绪！\n\n{sys_note}",
            f"{target} MCP沙盒已就绪",
        )

    if t == "sensor":
        sys_note, workplace_id = sensor_factory_init(target, is_upgrade=True)
        if not workplace_id:
            return error_response(sys_note, "Sensor 升级失败")
        return text_response(
            f"{target} Sensor沙盒已就绪！\n\n{sys_note}",
            f"{target} Sensor沙盒已就绪",
        )

    if t == "agentloop":
        sys_note, workplace_id = agentloop_factory_init(target, is_upgrade=True)
        if not workplace_id:
            return error_response(sys_note, "AgentLoop 升级失败")
        return text_response(
            f"{target} AgentLoop沙盒已就绪！\n\n{sys_note}",
            f"{target} AgentLoop沙盒已就绪",
        )

    if t == "graph":
        sys_note, workplace_id = graph_factory_init(target, is_upgrade=True)
        if not workplace_id:
            return error_response(sys_note, "Graph 升级失败")
        return text_response(
            f"{target} Graph沙盒已就绪！\n\n{sys_note}",
            f"{target} Graph沙盒已就绪",
        )

    return _upgrade_ui_plugin(target)


def _upgrade_ui_plugin(target: str) -> dict:
    """UI 插件升级：把已安装的插件搬进宿主可写的沙盒插件根（agent_vm/ui-plugin）"""
    from src.server.api.webmin import (
        BUILTIN_PLUGIN_ROOT,
        SANDBOX_PLUGIN_ROOT,
        USER_PLUGIN_ROOT,
    )

    plugin_id = (target or "").strip()
    if not plugin_id or any(c in plugin_id for c in ("/", "\\", "..")):
        return error_response(f"插件 id 非法：{target!r}", "参数错误")

    source = None
    for root in (USER_PLUGIN_ROOT, SANDBOX_PLUGIN_ROOT, BUILTIN_PLUGIN_ROOT):
        cand = os.path.join(root, plugin_id)
        if os.path.isdir(cand):
            source = cand
            break
    if source is None:
        return error_response(
            f"无法升级 UI 插件 '{plugin_id}'：未找到已安装的插件目录。",
            "未安装",
        )

    if os.path.abspath(source) == os.path.abspath(
        os.path.join(SANDBOX_PLUGIN_ROOT, plugin_id)
    ):
        return text_response(
            f"UI 插件 '{plugin_id}' 已在可编辑的沙盒根目录：{source}\n直接编辑它即可。",
            f"{plugin_id} 已可编辑",
        )

    dest = os.path.join(SANDBOX_PLUGIN_ROOT, plugin_id)
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(SANDBOX_PLUGIN_ROOT, exist_ok=True)
    shutil.copytree(source, dest)
    return text_response(
        f"已把 UI 插件 '{plugin_id}' 从 {source} 拷贝至沙盒根目录：{dest}\n"
        f"（改完让用户按 Ctrl+R 刷新即可看到）",
        f"{plugin_id} UI插件沙盒已就绪",
    )
