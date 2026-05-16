import os
from typing import Any, Dict

from src.harness.node.agent_node import AgentNode
from src.harness.utils.llm_helper import inject_force_push


class Node(AgentNode):
    """文件输出循环节点：负责调用大模型并严格校验沙盒文件是否生成"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        tools = self.get_all_tools()

        original_file_path = inputs.get("file_path") or self.config.get("file_path")
        if not original_file_path or not original_file_path.startswith("/agent_vm"):
            raise ValueError(f"文件路径必须以'/agent_vm'开头，当前输入: {original_file_path}")

        check_file_path = (
            original_file_path[len("/agent_vm/"):]
            if original_file_path.startswith("/agent_vm/")
            else original_file_path[len("/agent_vm"):]
        )

        sandbox_root = os.path.abspath(os.path.join(os.getcwd(), "agent_vm"))
        check_file_path = os.path.abspath(os.path.join(sandbox_root, check_file_path.lstrip("/")))

        if not check_file_path.startswith(sandbox_root):
            raise ValueError(f"安全警告: 文件路径存在越权访问风险 {original_file_path}")

        if force_push_msgs:
            messages = inject_force_push(messages, force_push_msgs)

        consecutive_file_missing_errors = 0
        MAX_CONSECUTIVE_ERRORS = 3

        while True:
            # 1. 把控制权交给纯净的大模型循环，直到它说 task_done
            loop_result = await self.run_agent_loop(context, messages, tools)
            messages = loop_result["messages"]
            summary = loop_result["summary"]

            # 2. 拿到结果后，在本节点进行严格的业务校验
            if os.path.exists(check_file_path):
                self.log(context, "SYSTEM", f"✅ [文件验证] 目标文件已存在: {original_file_path}")
                final_outputs = {"messages": messages, "summary": summary}
                self.save_checkpoints(context, {"inputs": inputs, "outputs": final_outputs})
                return final_outputs
            else:
                consecutive_file_missing_errors += 1
                if consecutive_file_missing_errors >= MAX_CONSECUTIVE_ERRORS:
                    self.log(context, "SYSTEM", f"🔴 [文件熔断] 连续 {MAX_CONSECUTIVE_ERRORS} 次文件未生成，挂起等待人类介入。")
                    await self._trigger_circuit_breaker(context, messages, "文件生成始终失败，请检查沙盒系统或给出明确指引。")
                    consecutive_file_missing_errors = 0
                    continue

                self.log(context, "WARNING", f"⚠️ [验收打回] 目标文件未生成: {original_file_path} ({consecutive_file_missing_errors}/{MAX_CONSECUTIVE_ERRORS})")

                # 3. 校验不通过，将全量上下文末尾追加错误提示，进入下一轮 while 循环回炉重造！
                err_msg = f"未检测到沙盒文件：{original_file_path}。请检查是否生成在了其他路径，并及时生成目标文件。如果你实在无法完成任务，请使用 yield_to_human 工具直接挂起任务！"
                messages.append({"role": "user", "content": err_msg})
