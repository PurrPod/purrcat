import os
import asyncio
from typing import Any, Dict
from src.harness.node.agent_node import AgentNode
from src.harness.utils.llm_helper import inject_force_push

class Node(AgentNode):
    """全能 Agent 循环：支持纯文本总结，也支持多文件强制验收"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        # 目标文件列表，兼容字符串或列表格式
        target_files_raw = inputs.get("target_files") or self.config.get("target_files", [])
        if isinstance(target_files_raw, str):
            target_files = [f.strip() for f in target_files_raw.split(",") if f.strip()]
        else:
            target_files = target_files_raw

        # 校验文件路径合法性
        check_paths = []
        for fpath in target_files:
            if not fpath.startswith("/agent_vm"):
                raise ValueError(f"文件路径必须以 '/agent_vm' 开头: {fpath}")
            check_paths.append(fpath.replace("/agent_vm", os.path.abspath(os.path.join(os.getcwd(), "agent_vm")), 1))

        # 恢复记忆与指令注入
        backup = self.load_checkpoints(context)
        if backup.get("outputs", {}).get("messages"):
            messages = backup["outputs"]["messages"]
            self.log(context, "SYSTEM", "📦 [读取存档] 成功加载历史对话记忆。")

        if force_push_msgs:
            messages = inject_force_push(messages, force_push_msgs)

        tools = self.get_all_tools()
        MAX_ERRORS = 3
        error_count = 0

        while True:
            # 运行核心思考循环
            loop_result = await self.run_agent_loop(context, messages, tools)
            messages = loop_result["messages"]
            summary = loop_result["summary"]

            # 如果没有文件校验需求，直接成功返回
            if not check_paths:
                self.log(context, "SYSTEM", f"✅ [任务完结] 无文件校验需求，输出总结。")
                final_outputs = {"messages": messages, "summary": summary}
                self.save_checkpoints(context, {"inputs": inputs, "outputs": final_outputs})
                return final_outputs

            # 文件校验逻辑
            missing_files = [f for i, f in enumerate(target_files) if not os.path.exists(check_paths[i])]
            if not missing_files:
                self.log(context, "SYSTEM", f"✅ [验收通过] 所有目标文件均已生成！")
                final_outputs = {"messages": messages, "summary": summary}
                self.save_checkpoints(context, {"inputs": inputs, "outputs": final_outputs})
                return final_outputs
            
            # 打回逻辑
            error_count += 1
            if error_count >= MAX_ERRORS:
                await self._trigger_circuit_breaker(context, messages, f"连续失败，以下文件未生成: {missing_files}")
                error_count = 0
                continue

            self.log(context, "WARNING", f"⚠️ [验收打回] 缺失文件: {missing_files}")
            messages.append({"role": "user", "content": f"系统未检测到以下文件：{missing_files}。请确保使用工具将内容写入这些文件中！"})