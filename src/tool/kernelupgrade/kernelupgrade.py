"""KernelUpgrade 工具主入口 - 实时执行无需审批"""

import traceback
from src.tool.utils.format import error_response, text_response
from src.evolve import skill_improve_init, run_skill_eval_background, mcp_improve_init, run_mcp_eval_background

def KernelUpgrade(action: str, target: str, **kwargs) -> dict:
    """
    Agent 的自我进化内核升级工具。
    - action="create_skill": 生成全新的 Skill 骨架
    - action="upgrade_skill": 拷贝现存的 Skill 进行修改
    - action="test_skill": 在后台运行 Skill 沙盒盲测
    - action="create_mcp": 生成全新的 MCP Server 骨架
    - action="test_mcp": 在后台运行 MCP 并发测试
    """
    try:
        if action == "create_skill":
            sys_note = skill_improve_init(target, is_upgrade=False)
            return text_response(
                f"✅ 全新技能沙盒构建完成！\n\n{sys_note}", 
                f"🎉 {target} 骨架已创建"
            )

        elif action == "upgrade_skill":
            sys_note = skill_improve_init(target, is_upgrade=True)
            return text_response(
                f"✅ 现存技能已拷贝至进化沙盒，准备好进行升级！\n\n{sys_note}", 
                f"📦 {target} 沙盒已就绪"
            )

        elif action == "test_skill":
            parts = target.split("/")
            if len(parts) != 2:
                return error_response(
                    f"执行失败：target 格式不正确，应为 'uuid/skill_name'。当前输入为: '{target}'", 
                    "❌ 路径格式错误"
                )
            
            workplace_id, skill_name = parts
            
            from src.agent.manager import manager
            main_session_id = manager.get_active_session_id()
            
            run_skill_eval_background(workplace_id, skill_name, main_session_id)
            
            msg = (
                f"🚀 技能 '{skill_name}' 的自动化盲测流水线已在后台启动！\n"
                f"测试通常需要 30 秒至几分钟。完成后将自动通过系统级通知向你汇报测试结果报告和行为轨迹(trace.md)。\n"
                f"⚠️ 提示：在等待测试期间，你可以挂起本任务，或者继续进行代码思考与其他不冲突的工作。禁止频繁轮询测试结果！"
            )
            return text_response(msg, f"⏳ {skill_name} 盲测运行中")

        elif action == "create_mcp":
            sys_note = mcp_improve_init(target)
            return text_response(
                f"✅ 全新 MCP Server 沙盒构建完成！\n\n{sys_note}", 
                f"🔌 {target} MCP已创建"
            )

        elif action == "test_mcp":
            parts = target.split("/")
            if len(parts) != 2:
                return error_response(
                    f"执行失败：target 格式不正确，应为 'uuid/mcp_name'。当前输入为: '{target}'", 
                    "❌ 路径格式错误"
                )
            
            workplace_id, mcp_name = parts
            from src.agent.manager import manager
            main_session_id = manager.get_active_session_id()
            
            # 启动 MCP 后台测试流水线
            run_mcp_eval_background(workplace_id, mcp_name, main_session_id)
            
            msg = (
                f"🚀 MCP '{mcp_name}' 的并发测试流水线已在后台启动！\n"
                f"测试极快，完成后将向你汇报 `schema_dump.json` 的位置与执行报告。\n"
            )
            return text_response(msg, f"⏳ {mcp_name} 并发测试中")

        else:
            return error_response(
                f"不支持的 action: {action}。当前系统暂未实装该模块的进化能力，请检查拼写或等待后续版本升级。",
                "❌ 参数/不支持的操作"
            )

    except Exception as e:
        traceback.print_exc()
        return error_response(f"KernelUpgrade 执行异常: {str(e)}", "❌ 执行失败")