from typing import Dict, Any
from src.harness.node.base import BaseNode
from src.harness.tools.base_tool import BaseToolDispatcher
from src.tool import BASE_TASK_TOOL_SCHEMA


class Node(BaseNode):
    """工具包节点：根据配置下发专属工具列表，核心工具和基础任务工具始终强制注入"""

    async def execute(self, inputs: Dict[str, Any], force_push_msgs: list, context: Any) -> Dict[str, Any]:
        # 1. 获取核心工具（task_done、yield_to_human），始终强制注入
        core_schemas = BaseToolDispatcher.get_core_tool_schemas()
        core_tool_names = {schema["function"]["name"] for schema in core_schemas}

        # 2. 获取基础任务工具（bash、filesystem、search、mcp），作为保底工具始终注入
        base_task_schemas = BASE_TASK_TOOL_SCHEMA
        base_task_names = {schema["function"]["name"] for schema in base_task_schemas}

        # 3. 获取业务工具
        business_schemas = BaseToolDispatcher.get_all_tool_schemas()

        # 4. 收集所有已有名字，用于全局去重
        all_existing_names = core_tool_names | base_task_names

        # 5. 读取当前节点配置的"白名单"
        allowed_tools = self.config.get("allowed_tools", [])

        # 6. 如果没有配置白名单，返回去重后的全量业务工具 + 基础任务工具 + 核心工具
        if not allowed_tools:
            filtered_business = [
                schema for schema in business_schemas
                if schema["function"]["name"] not in all_existing_names
            ]
            all_schemas = filtered_business + base_task_schemas + core_schemas
            seen = set()
            deduped = []
            for schema in all_schemas:
                name = schema["function"]["name"]
                if name not in seen:
                    seen.add(name)
                    deduped.append(schema)
            return {"default": deduped}

        # 7. 按需过滤业务工具，同时排除基础任务工具和核心工具（避免重复），基础任务工具和核心工具始终保留
        filtered_business = [
            schema for schema in business_schemas
            if schema["function"]["name"] in allowed_tools
            and schema["function"]["name"] not in all_existing_names
        ]

        all_schemas = filtered_business + base_task_schemas + core_schemas
        seen = set()
        deduped = []
        for schema in all_schemas:
            name = schema["function"]["name"]
            if name not in seen:
                seen.add(name)
                deduped.append(schema)
        return {"default": deduped}