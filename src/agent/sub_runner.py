import asyncio
import os
import time
import uuid
import copy
import threading
from typing import List

from src.model import AgentModel
from src.tool.utils.route import dispatch_tool
from src.harness.utils.tool_helper import extract_tool_calling
from src.tool import AGENT_TOOL_SCHEMA
from src.utils.config import AGENT_VM_DIR

ACTIVE_SUB_TASKS = {}
SUB_TASK_LOCK = threading.Lock()

class SubAgentRunner:
    def __init__(self, main_session_id: str, internal_branch_id: str, display_branch_id: str, action: str, deliverable: str, initial_history: list):
        self.main_session_id = main_session_id
        self.internal_branch_id = internal_branch_id
        self.display_branch_id = display_branch_id
        self.action = action
        self.deliverable_path = deliverable.replace("/agent_vm", AGENT_VM_DIR, 1) if deliverable.startswith("/agent_vm") else deliverable
        
        self.messages = copy.deepcopy(initial_history)
        self.model = AgentModel(task_id=f"{main_session_id}_sub_{internal_branch_id}")
        
    def _notify_main(self, content: str):
        from src.agent.manager import AgentManager
        AgentManager().agent_force_push(content, type="system")

    async def run(self):
        system_inject = (
            f"【系统：当前已进入后台分支 {self.display_branch_id}】\n"
            f"本分支核心任务：{self.action}\n"
            f"你必须生成的交付物文件位置：{self.deliverable_path}\n"
            f"请专注于本分支的交付物生成。完成后停止调用工具，不要做任何与本分支无关的事情。"
        )
        self.messages.append({"role": "system", "content": system_inject})
        
        turn_count = 0
        start_time = time.time()
        warning_sent = False
        tool_call_after_generated_turns = 0
        
        while True:
            elapsed_time = time.time() - start_time
            if not warning_sent and (turn_count >= 15 or elapsed_time > 600):
                self._notify_main(
                    f"⚠️ [监控提示] 后台分支 `{self.display_branch_id}` 已默默运行了 {turn_count} 轮 / {int(elapsed_time)} 秒。\n"
                    f"若确认其陷入死循环，你随时可以使用 BrainStorm(action='cancel', target_branch_id='{self.display_branch_id}') 将其强杀。"
                )
                warning_sent = True

            response = await asyncio.to_thread(self.model.chat, messages=self.messages, tools=AGENT_TOOL_SCHEMA)
            msg_resp = response.choices[0].message
            
            assist_msg = {"role": "assistant", "content": msg_resp.content or ""}
            if msg_resp.tool_calls:
                assist_msg["tool_calls"] = [
                    {"id": t.id, "type": t.type, "function": {"name": t.function.name, "arguments": t.function.arguments}}
                    for t in msg_resp.tool_calls
                ]
            self.messages.append(assist_msg)

            tool_calls = extract_tool_calling(response)
            file_exists = os.path.exists(self.deliverable_path)
            turn_count += 1
            
            if not tool_calls:
                if file_exists:
                    self._notify_main(f"✅ [后台捷报] 子分支 `{self.display_branch_id}` 任务完满结束！交付物已成功在本地落盘。")
                    break
                else:
                    self.messages.append({"role": "user", "content": f"系统未检测到预期的交付物文件 {self.deliverable_path}。如果你认为任务已完结，请先调用对应工具生成文件！"})
                    continue
            
            if file_exists:
                tool_call_after_generated_turns += 1
                if tool_call_after_generated_turns > 5:
                    self.messages.append({
                        "role": "user", 
                        "content": f"提醒：系统检测到你已成功生成目标交付物。请立即停止派生其他无关代码，收尾并结束当前分支任务。"
                    })
            else:
                tool_call_after_generated_turns = 0

            for tc in tool_calls:
                import json
                tool_name = tc.function.name
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                
                # 🚫 核心注入：向调度器声明这是子分支在调用工具
                args["_is_sub_branch"] = True  
                
                if tool_name == "Bash":
                    args["session_id"] = f"{self.main_session_id}_{self.internal_branch_id}"
                
                result = await asyncio.to_thread(dispatch_tool, tool_name, args)
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "name": tool_name, "content": result})

async def run_dag_graph(sub_branches: list, main_session_id: str, main_history: list):
    plan_batch_id = uuid.uuid4().hex[:6]
    
    internal_id_map = {b["branch_id"]: f"{plan_batch_id}_{b['branch_id']}" for b in sub_branches}
    events = {internal_id_map[b["branch_id"]]: asyncio.Event() for b in sub_branches}
    
    async def run_single_branch(b_info):
        display_id = b_info["branch_id"]
        internal_id = internal_id_map[display_id]
        
        for dep in b_info.get("depends_on", []):
            if dep in internal_id_map:
                await events[internal_id_map[dep]].wait()
                
        runner = SubAgentRunner(
            main_session_id=main_session_id,
            internal_branch_id=internal_id,
            display_branch_id=display_id,
            action=b_info["action"],
            deliverable=b_info["deliverable"],
            initial_history=main_history
        )
        
        loop_task = asyncio.create_task(runner.run())
        
        with SUB_TASK_LOCK:
            ACTIVE_SUB_TASKS[display_id] = loop_task
        
        try:
            await loop_task
        except asyncio.CancelledError:
            runner._notify_main(f"🛑 后台分支 `{display_id}` 已被主分支发送 cancel 信号强制终止。")
        finally:
            with SUB_TASK_LOCK:
                ACTIVE_SUB_TASKS.pop(display_id, None)
            events[internal_id].set()

    await asyncio.gather(*(run_single_branch(b) for b in sub_branches))