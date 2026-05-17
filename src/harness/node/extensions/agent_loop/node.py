import os
import asyncio
from typing import Any, Dict
from src.harness.node.agent_node import AgentNode

class Node(AgentNode):
    """全能 Agent 循环：支持纯文本总结，也支持多文件强制验收"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        my_memory = context.node_memory.setdefault(self.node_id, {})
        
        messages = my_memory.get("messages", inputs.get("messages", []))
        
        pending_push = my_memory.pop("force_push", [])
        if pending_push:
            for msg in pending_push:
                messages.append({"role": "user", "content": f"[人工指令] {msg}"})

        target_files_raw = inputs.get("target_files") or self.config.get("target_files", [])
        if isinstance(target_files_raw, str):
            target_files = [f.strip() for f in target_files_raw.split(",") if f.strip()]
        else:
            target_files = target_files_raw

        check_paths = []
        for fpath in target_files:
            if not fpath.startswith("/agent_vm"):
                raise ValueError(f"文件路径必须以 '/agent_vm' 开头: {fpath}")
            check_paths.append(fpath.replace("/agent_vm", os.path.abspath(os.path.join(os.getcwd(), "agent_vm")), 1))

        tools = self.get_all_tools()
        MAX_ERRORS = 3
        error_count = 0

        try:
            while True:
                loop_result = await self.run_agent_loop(context, messages, tools)
                messages = loop_result["messages"]
                summary = loop_result["summary"]

                if not check_paths:
                    self.log(context, "SYSTEM", f"✅ [任务完结] 无文件校验需求，输出总结。")
                    my_memory["messages"] = messages
                    return {"messages": messages, "summary": summary}

                missing_files = [f for i, f in enumerate(target_files) if not os.path.exists(check_paths[i])]
                if not missing_files:
                    self.log(context, "SYSTEM", f"✅ [验收通过] 所有目标文件均已生成！")
                    my_memory["messages"] = messages
                    return {"messages": messages, "summary": summary}
                
                error_count += 1
                if error_count >= MAX_ERRORS:
                    my_memory["messages"] = messages
                    context.node_state[self.node_id] = NodeState.WAITING
                    raise asyncio.CancelledError(f"连续失败，以下文件未生成: {missing_files}")

                self.log(context, "WARNING", f"⚠️ [验收打回] 缺失文件: {missing_files}")
                messages.append({"role": "user", "content": f"系统未检测到以下文件：{missing_files}。请确保使用工具将内容写入这些文件中！"})
        
        except asyncio.CancelledError:
            my_memory["messages"] = messages
            raise
