import os
from typing import Any, Dict

from src.harness.node.agent_node import AgentNode
from src.harness.utils.llm_helper import inject_force_push


class Node(AgentNode):
    """文件输出循环节点：负责调用大模型并严格校验沙盒文件是否生成"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        original_file_path = inputs.get("file_path") or self.config.get("file_path")
        if not original_file_path or not original_file_path.startswith("/agent_vm"):
            raise ValueError(f"文件路径必须以'/agent_vm'开头，当前输入: {original_file_path}")

        check_file_path = original_file_path.replace(
            "/agent_vm", os.path.abspath(os.path.join(os.getcwd(), "agent_vm")), 1
        )

        messages = inputs.get("messages", [])
        backup = self.load_checkpoints(context)
        is_history_loaded = False

        backup_outputs = backup.get("outputs", {})
        if backup_outputs and "messages" in backup_outputs:
            messages = backup_outputs["messages"]
            is_history_loaded = True
            self.log(context, "SYSTEM", "📦 [读取存档] 成功加载历史对话记忆。")

        if force_push_msgs:
            self.log(context, "SYSTEM", f"⚠️ [指令注入] 将人类指令追加到当前上下文中...")
            messages = inject_force_push(messages, force_push_msgs)

        elif is_history_loaded:
            if os.path.exists(check_file_path):
                self.log(context, "SYSTEM", f"⚡ [缓存命中] 目标文件 {original_file_path} 依然存在，直接跳过繁重对话！")
                return backup["outputs"]
            else:
                self.log(context, "WARNING", f"⚠️ 发现备份记录，但目标文件已被物理删除，需要重新生成。")

        tools = self.get_all_tools()
        consecutive_file_missing_errors = 0
        MAX_CONSECUTIVE_ERRORS = 3

        while True:
            loop_result = await self.run_agent_loop(context, messages, tools)
            messages = loop_result["messages"]
            summary = loop_result["summary"]

            if os.path.exists(check_file_path):
                self.log(context, "SYSTEM", f"✅ [文件验证] 目标文件已成功生成: {original_file_path}")
                final_outputs = {"messages": messages, "summary": summary}
                self.save_checkpoints(context, {"inputs": inputs, "outputs": final_outputs})
                return final_outputs
            else:
                consecutive_file_missing_errors += 1
                if consecutive_file_missing_errors >= MAX_CONSECUTIVE_ERRORS:
                    self.log(context, "SYSTEM", f"🔴 [文件熔断] 连续多次未生成文件，任务挂起求助人类。")
                    await self._trigger_circuit_breaker(context, messages, "文件生成始终失败，请检查或给出明确指引。")
                    consecutive_file_missing_errors = 0
                    continue

                self.log(context, "WARNING", f"⚠️ [验收打回] 目标文件未生成: {original_file_path}")
                err_msg = f"未检测到沙盒文件：{original_file_path}。请检查并生成。"
                messages.append({"role": "user", "content": err_msg})