from typing import Any, Dict

from src.harness.node.agent_node import AgentNode
from src.harness.utils.llm_helper import inject_force_push


class Node(AgentNode):
    """总结输出循环节点：封装思考->调用工具->总结的完整循环逻辑"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        messages = inputs.get("messages", [])
        
        # 🌟 1. 修复失忆Bug：从存档接盘历史 messages
        backup = self.load_checkpoints(context)
        backup_outputs = backup.get("outputs", {})
        if backup_outputs and "messages" in backup_outputs:
            messages = backup_outputs["messages"]
            self.log(context, "SYSTEM", "📦 [读取存档] 成功加载历史对话记忆。")

        tools = self.get_all_tools()

        if force_push_msgs:
            self.log(context, "SYSTEM", f"⚠️ [指令注入] 将人类指令追加到当前上下文中...")
            messages = inject_force_push(messages, force_push_msgs)

        # 🌟 2. 补充日志：循环起步提示
        self.log(context, "SYSTEM", f"🚀 [总结循环] 引擎启动，当前上下文包含 {len(messages)} 条消息...")

        # 没有特殊校验，大模型说 task_done 就算结束
        final_outputs = await self.run_agent_loop(context, messages, tools)

        # 🌟 3. 补充日志：循环完结提示，打印一点 summary 的预览
        summary_preview = str(final_outputs.get("summary", ""))[:50]
        self.log(context, "SYSTEM", f"🏁 [总结循环] 任务圆满完结！产出总结: {summary_preview}...")

        self.save_checkpoints(context, {"inputs": inputs, "outputs": final_outputs})
        return final_outputs
