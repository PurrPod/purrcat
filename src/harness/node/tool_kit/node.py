from typing import Dict, Any
from harness.node.base import BaseNode
from harness.tools.base_tool import BaseToolDispatcher


class Node(BaseNode):
    """工具包节点：根据配置下发专属工具列表，核心工具始终强制注入"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        # 1. 获取核心工具（task_done、yield_to_human），始终强制注入
        core_schemas = BaseToolDispatcher.get_core_tool_schemas()
        
        # 2. 获取业务工具
        business_schemas = BaseToolDispatcher.get_all_tool_schemas()
        
        # 3. 读取当前节点配置的"白名单"
        allowed_tools = self.config.get("allowed_tools", [])
        
        # 4. 如果没有配置白名单，返回全量业务工具 + 核心工具
        if not allowed_tools:
            return {"default": business_schemas + core_schemas}
        
        # 5. 按需过滤业务工具，核心工具始终保留（不参与用户配置）
        filtered_business = [
            schema for schema in business_schemas
            if schema["function"]["name"] in allowed_tools
        ]
        
        return {"default": filtered_business + core_schemas}