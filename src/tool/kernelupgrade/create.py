"""KernelUpgrade(action='create')：在隔离沙盒中搭建全新骨架"""

from src.tool.utils.format import error_response, text_response
from src.evolve import (
    skill_improve_init,
    mcp_improve_init,
    sensor_factory_init,
    ui_plugin_init,
    agentloop_factory_init,
    graph_factory_init,
)
from .shared import record_trace_meta


def create_module(t: str, target: str) -> dict:
    if t == "skill":
        sys_note, workplace_id = skill_improve_init(target, is_upgrade=False)
        record_trace_meta(workplace_id)
        if not workplace_id:
            return error_response(sys_note, "Skill 创建失败")
        return text_response(f"{sys_note}", f"{target} 进化沙盒已就绪")

    if t == "mcp":
        sys_note, workplace_id = mcp_improve_init(target)
        if not workplace_id:
            return error_response(sys_note, "MCP 创建失败")
        return text_response(
            f"全新 MCP Server 沙盒构建完成！\n\n{sys_note}",
            f"{target} MCP已创建",
        )

    if t == "sensor":
        sys_note, workplace_id = sensor_factory_init(target, is_upgrade=False)
        if not workplace_id:
            return error_response(sys_note, "Sensor 创建失败")
        return text_response(
            f"全新 Sensor 沙盒构建完成！\n\n{sys_note}",
            f"{target} Sensor已创建",
        )

    if t == "agentloop":
        sys_note, workplace_id = agentloop_factory_init(target, is_upgrade=False)
        if not workplace_id:
            return error_response(sys_note, "AgentLoop 创建失败")
        return text_response(
            f"全新 AgentLoop 沙盒构建完成！\n\n{sys_note}",
            f"{target} AgentLoop已创建",
        )

    if t == "graph":
        sys_note, workplace_id = graph_factory_init(target, is_upgrade=False)
        if not workplace_id:
            return error_response(sys_note, "Graph 创建失败")
        return text_response(
            f"全新 Graph 沙盒构建完成！\n\n{sys_note}",
            f"{target} Graph已创建",
        )

    # ui-plugin：宿主直接把 agent_vm/ui-plugin/ 当插件根扫描，无 UUID 沙盒
    sys_note, plugin_dir = ui_plugin_init(target)
    if not plugin_dir:
        return error_response(sys_note, "UI 插件框架创建失败")
    return text_response(
        f"UI 插件沙盒已就绪：{plugin_dir}\n"
        f"（宿主已把 agent_vm/ui-plugin/ 作为插件根目录扫描，写完让用户按 Ctrl+R 刷新即可看到）\n\n"
        f"{sys_note}",
        f"{target} UI插件已创建",
    )
