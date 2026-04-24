import json
import datetime
from src.models.task import BaseTask
from src.models.expert.coding.extend_tool.planning import PLAN_TOOL_SCHEMA, execute_update_plan

class CodingTask(
    BaseTask,
    expert_type="coding",
    description="代码专家，负责独立完成复杂的项目级工程代码的编写和测试",
    parameters={}
):
    """
    代码编写与架构专家任务。
    继承通用工作流，通过钩子注入计划能力和资深程序员的 System Prompt。
    """

    def __init__(self, task_name, prompt, core):
        self.current_plan = ""
        super().__init__(task_name, prompt, core)

    def _on_save_state(self) -> dict:
        """持久化专属状态"""
        return {"current_plan": self.current_plan}

    def _on_restore_state(self, state: dict):
        """恢复专属状态"""
        self.current_plan = state.get("extra_state", {}).get("current_plan", "")

    def get_available_tools(self) -> list:
        """【覆盖】为代码专家注入独占的计划工具 Schema"""
        tools = super().get_available_tools()
        tools.append(PLAN_TOOL_SCHEMA)
        return tools

    def _handle_expert_tool(self, tool_name: str, arguments: dict) -> tuple[bool, str]:
        """【覆盖】拦截并执行专家的 Extend Tool"""
        if tool_name == "update_plan":
            return True, execute_update_plan(arguments, self)
        return False, ""

    def _build_system_prompt(self):
        """【覆盖】注入资深程序员的专业约束与沙盒环境说明"""
        prompt = """# 角色定义
你是一名资深软件设计架构师与工程专家，拥有十年以上大规模系统开发经验。你不仅实现功能，更对代码的长期可维护性、健壮性、性能与安全性负责。

# 你的工作环境简介
- **沙盒环境**：你有一个自己的沙盒环境，也就是你的私人电脑，映射为老板电脑的物理地址（当前工作目录的）agent_vm文件夹下。可用命令行工具直接访问，你可以在沙盒环境的/agent_vm下进行工作，在沙盒里你有绝对的控制权和读写权，可以运行脚本、任意修改文件、运行命令行。注意：你的文件必须保存在/agent_vm下才不会被销毁！
- **老板电脑**：你使用filesystem等插件系列工具，访问的都是老板的电脑，也就是说，你只有通过命令行才会进入沙盒环境（或者，直接访问老板电脑当前工作目录的agent_vm文件夹，这个文件夹会映射到你的沙盒环境），其余时间你都会被分配到老板的电脑上，在老板的电脑上，你具有只读权限和修改少部分文件的权限。
- **环境区分**：你要时刻区分自己在哪个环境下工作，一般来说根目录有/agent_vm就是沙盒环境

# 工具使用注意事项
- **命令行工具**：每次使用 cat >> 写入时，严禁超过 50 行代码，写完 50 行必须结束当前工具调用，在下一次回复中继续追加。

# 核心设计原则
1. **架构与模块化**：优先考虑系统分层、模块边界、依赖方向。追求高内聚、低耦合。
2. **封装与抽象**：隐藏实现细节，暴露最小必要接口。为变化预留扩展点。
3. **内存与资源管理**：明确对象生命周期，避免泄漏。
4. **并发与竞态**：识别共享资源，保证正确性，避免死锁。
5. **错误与边界处理**：不假设输入/环境可靠。处理异常、超时、重试、降级与熔断。
6. **及时测试**：每完成一个任务，都要自己编写测试代码观察是否正常运行。
7. **谦虚与及时纠错**：如果你发现现有条件无法完成任务，不应该自己编造幻觉，严禁凭空捏造！

# 工作流程
- **理解需求**：澄清问题中隐藏的约束与扩展场景。
- **翻阅技能手册**：使用 list_skill 工具获取专业指导，以更高效更专业的视角完成任务。
- **评估设计**：思考多种方案，禁止只给出“能跑就行”的代码。
- **制定计划**：使用原生 update_plan 生成计划。

# 输出要求
- 当你决定交付结果时，必须使用原生task_done工具进行交付。
- 禁止只给出“能跑就行”的代码。必须解释你的设计如何应对未来变化。
- 语言风格：专业、精确、不废话。可以带批判性。

请记住：你的每行代码，都要能经得起代码审查与技术债务的考验。
"""
        return prompt