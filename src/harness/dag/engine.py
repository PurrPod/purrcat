import asyncio
import traceback
import copy
from typing import Dict, Any, List, Type


class DAGNode:
    """DAG 节点基类"""
    def __init__(self, node_id: str, **kwargs):
        self.node_id = node_id
        self.state = "READY"
        self.inputs_map = {}
        self.outputs = {}
        self.config = kwargs
        self._done_event = asyncio.Event()
        self.error_msg = ""

    def bind_input(self, target_port: str, source_node: 'DAGNode', source_port: str = "default"):
        """绑定上游节点输入线"""
        self.inputs_map[target_port] = {"node": source_node, "port": source_port}

    async def _wait_for_inputs(self) -> Dict[str, Any]:
        """等待所有依赖的父节点完成并收集输入数据"""
        input_data = {}
        for target_port, source_info in self.inputs_map.items():
            source_node = source_info["node"]
            await source_node._done_event.wait()
            
            if source_node.state == "ERROR":
                raise RuntimeError(f"上游节点 [{source_node.node_id}] 执行失败，级联中断。")
            
            input_data[target_port] = copy.deepcopy(source_node.outputs.get(source_info["port"]))
        return input_data

    async def run(self, context: Any):
        """节点生命周期控制 (支持断点跳过)"""
        if self.state == "COMPLETED":
            self._done_event.set()
            return

        try:
            input_data = await self._wait_for_inputs()
            self.state = "RUNNING"
            
            if hasattr(context, "log_and_notify"):
                context.log_and_notify("SYSTEM", f"🟢 节点 [{self.__class__.__name__}:{self.node_id}] 开始执行")
            
            self.outputs = await self.execute(input_data, context)
            
            self.state = "COMPLETED"
        except Exception as e:
            self.state = "ERROR"
            self.error_msg = traceback.format_exc()
            if hasattr(context, "log_and_notify"):
                context.log_and_notify("ERROR", f"❌ 节点 [{self.node_id}] 崩溃: {self.error_msg}")
        finally:
            self._done_event.set()

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        """子类必须实现的核心业务逻辑"""
        raise NotImplementedError


class EmptyListNode(DAGNode):
    async def execute(self, inputs, context):
        return {"default": []}


class StrAdapterNode(DAGNode):
    async def execute(self, inputs, context):
        str1 = inputs.get("str1", "")
        str2 = inputs.get("str2", "")
        return {"default": str1 + str2}


class AppenderNode(DAGNode):
    async def execute(self, inputs, context):
        msg_list = inputs.get("list", [])
        item = inputs.get("item")
        if item:
            if isinstance(item, list):
                msg_list.extend(item)
            else:
                msg_list.append(item)
        return {"default": msg_list}


class ToolKitNode(DAGNode):
    async def execute(self, inputs, context):
        return {"default": context.global_tool_kit()}


class LLMChatNode(DAGNode):
    async def execute(self, inputs, context):
        messages = inputs.get("messages", [])
        tools = inputs.get("tools", [])
        response = await asyncio.to_thread(context.run_llm_step, messages, tools)
        return {"default": response}


class ToolExecutorNode(DAGNode):
    async def execute(self, inputs, context):
        response = inputs.get("response")
        tool_messages = await asyncio.to_thread(context.run_tool_calling, response)
        return {"default": tool_messages}


class FileOutputLoopNode(DAGNode):
    """高级节点：封装了思考->调用工具->验收的循环逻辑"""
    async def execute(self, inputs, context):
        messages = inputs.get("messages", [])
        tools = inputs.get("tools", context.global_tool_kit())
        file_path = self.config.get("file_path", f"{context.workplace}/FINISHED.md")
        
        final_messages = await asyncio.to_thread(
            context.file_output_loop, 
            messages=messages, 
            tools=tools, 
            file_path=file_path
        )
        return {"default": final_messages}


class DAGEngine:
    NODE_REGISTRY: Dict[str, Type[DAGNode]] = {
        "EmptyList": EmptyListNode,
        "StrAdapter": StrAdapterNode,
        "Appender": AppenderNode,
        "ToolKit": ToolKitNode,
        "LLMChat": LLMChatNode,
        "ToolExecutor": ToolExecutorNode,
        "FileOutputLoop": FileOutputLoopNode
    }

    def __init__(self, context):
        self.context = context
        self.nodes: Dict[str, DAGNode] = {}

    def load_graph(self, graph_data: dict, saved_state: dict = None):
        """解析前端传入的 JSON 图并恢复断点"""
        saved_state = saved_state or {}
        
        for node_data in graph_data.get("nodes", []):
            node_id = node_data["id"]
            node_type = node_data["type"]
            config = node_data.get("data", {})
            
            NodeClass = self.NODE_REGISTRY.get(node_type)
            if not NodeClass:
                raise ValueError(f"Unknown node type: {node_type}")
                
            node = NodeClass(node_id=node_id, **config)
            
            if node_id in saved_state and saved_state[node_id]["state"] == "COMPLETED":
                node.state = "COMPLETED"
                node.outputs = saved_state[node_id]["outputs"]
                
            self.nodes[node_id] = node

        for edge in graph_data.get("edges", []):
            src_id = edge["source"]
            src_port = edge.get("sourceHandle", "default")
            tgt_id = edge["target"]
            tgt_port = edge.get("targetHandle", "default")
            
            if tgt_id in self.nodes and src_id in self.nodes:
                self.nodes[tgt_id].bind_input(tgt_port, self.nodes[src_id], src_port)

    async def execute_all(self):
        """并发启动图网络"""
        tasks = [node.run(self.context) for node in self.nodes.values()]
        await asyncio.gather(*tasks)
        
        return {
            n_id: {"state": node.state, "outputs": node.outputs}
            for n_id, node in self.nodes.items()
        }
