"""
MCP 指南生成器模块 (evolve/mcp/guide_generator.py)
"""


def generate_mcp_create_guide(mcp_name: str) -> str:
    return f"""# {mcp_name} MCP Server 模块化开发指南

系统已为你生成了结构化的工程目录。基于官方 FastMCP SDK 规范，请严格遵循以下开发范式：

## 1. 项目架构说明 (防循环导入)
* `app.py`: **全局实例**。只负责一行代码：`mcp = FastMCP("{mcp_name}")`。
* `server.py`: **主入口**。从 `app` 导入 `mcp`，并导入所有 tools。
* `tools/`: **核心工作区**。所有具体的 Tool 函数写在这里，必须从 `app` 导入 `mcp` 实例。

## 2. 添加新的 Tool (两步法则)

**步骤一：在 `tools/` 创建文件 (如 `weather.py`)**
```python
from app import mcp
import logging

@mcp.tool()
async def get_weather(city: str) -> str:
    return f"Weather in {{city}} is Sunny"

```

**步骤二：在 `server.py` 中激活**

```python
from app import mcp
import tools.weather  # 必须导入才能激活注册

```

## 3. 🔴 绝对红线：STDIO 日志污染

**绝对禁止使用 `print()` 输出到 stdout！**
底层使用 STDIO 通信，输出非 JSON-RPC 会导致崩溃。请使用 `logging.info(...)`。

## 4. 返回值与错误处理

FastMCP 会自动处理协议封装。声明了 `-> str`，就直接 return 字符串，**绝对不要**返回 `isError` 字典。遇到异常直接 `raise Exception(...)`。

## 5. 客户端配置 (已自动化 🎉)

你不需要手动指导人类或者通过终端修改 `.purrcat/mcp_config.json`。
当你调用工具进行 `merge_mcp` 时，系统底层会自动计算绝对路径并注入到配置文件中！
"""


def generate_mcp_test_guide(mcp_name: str) -> str:
    return f"""# {mcp_name} 测试与优化指南

## 1. 编写 Trigger 测试用例

在 `evals.json` 的 `triggers` 数组中，提供至少 10 个测试用例。测试你的 description 是否精准。

## 2. 编写 Execution 测试用例

在 `evals.json` 的 `executions` 数组中，编写覆盖所有边界场景的入参，测试 inputSchema。

## 3. 测试流水线与报告 (两步执行法)

**第一步：沙盒内自行执行评测 (极度重要！)**
编写完代码后，必须使用终端 (Bash) 执行评测脚本排错：

```bash
source .venv/bin/activate
python scripts/evaluation.py

```

**第二步：呼叫宿主机进行语义评测**
第一步无报错后，调用 `KernelUpgrade` 工具指定 `action="test_mcp"`。宿主机会模拟大模型唤醒，并在后台生成最终的 `test_report.md`。
"""
