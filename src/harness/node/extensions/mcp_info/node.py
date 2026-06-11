from typing import Any, Dict
from src.harness.node.base import BaseNode
from src.tool.callmcp.schema_manager import load_cached_schemas


class Node(BaseNode):
    """MCP Info 节点：输出指定的 MCP 服务器下所有可用工具及描述提示词"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🔌 [MCP Info] 正在获取 MCP 工具信息...")

        # 获取面板中配置的 MCP 服务器名称列表
        servers_config = self.config.get("mcp_servers", [])
        requested_servers = [
            item.get("name")
            for item in servers_config
            if isinstance(item, dict) and item.get("name")
        ]

        if not requested_servers:
            self.log(
                context, "WARNING", "⚠️ [MCP Info] 未配置任何 MCP 服务器名称，输出为空"
            )
            return {"mcp_kit_string": ""}

        # 调用底层接口读取内存缓存中的所有 MCP Schema
        schemas = load_cached_schemas()

        result_lines = [
            "[MCP Kit: These are the recommended MCP servers and tools, You can fetch tools parameters to finish the task more efficiently]"
        ]

        found_tools = 0
        for s in schemas:
            srv_name = s.get("server", "unknown")
            if srv_name in requested_servers:
                func = s.get("function", {})
                tool_name = func.get("name", "unknown_tool")
                desc = func.get("description", "No description available.")

                # 拼接服务器名与工具名，例如 tradingview.market_snapshot
                result_lines.append(f"- {srv_name}.{tool_name}: {desc}")
                found_tools += 1

        mcp_kit_str = "\n".join(result_lines)

        self.log(
            context,
            "SYSTEM",
            f"✅ [MCP Info] 成功打包 {found_tools} 个 MCP 工具的提示词。",
        )

        return {"mcp_kit_string": mcp_kit_str}
