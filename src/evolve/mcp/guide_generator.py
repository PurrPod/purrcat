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

## 2. 添加新的 Tool (三步法则)

**步骤一：在 `tools/` 下创建文件 (如 `weather.py`)**

```python
from app import mcp

@mcp.tool()
async def get_weather(city: str, days: int = 3) -> str:
    \"\"\"获取指定城市的天气预报（⚠️ 第一行必须是工具的功能描述，大模型据此判断何时调用！）

    Args:
        city: 城市名称，如 "北京"、"Shanghai" （⚠️ 参数描述大模型据此提取实体）
        days: 预报天数，默认 3 天
    \"\"\"
    return f"{{city}}未来{{days}}天天气晴"
```

**关键规范：**
* 必须写 Docstring：第一行是工具的 description，直接决定意图路由测试能否通过。
* 必须写 Args 块：解释每个参数的含义和格式，帮助大模型正确提取。
* 必须有 Type Hint：如 `str`, `int`, `float`, `bool`, `list[str]`。
* 默认值决定是否必填：有默认值的参数是可选的，无默认值的参数是必填的。

**步骤二：在 `server.py` 中激活**

```python
from app import mcp
import tools.weather  # 必须导入才能被 FastMCP 扫描注册到
```

## 3. 🔴 绝对红线：STDIO 日志污染

**绝对禁止使用 `print()` 输出到 stdout！**
底层使用 STDIO 通信，输出非 JSON-RPC 会导致崩溃。请使用 `logging.info(...)`。

## 4. 返回值与错误处理

FastMCP 会自动处理协议封装。声明了 `-> str`，就直接 return 字符串。遇到异常直接 `raise Exception(...)`。

**⚠️ 异常信息必须告诉大模型"错在哪 + 正确格式 + 示例"**，否则大模型无法自我修正：

```python
# ✅ 好：告诉大模型错在哪 + 正确格式 + 示例
raise Exception(f"获取股票 '{{symbol}}' 失败。正确格式：symbol 应为6位股票代码，"
                f"如 \\\"600519\\\"（贵州茅台），无需带 sh/sz 前缀")

# ❌ 差：只报错不给指引
raise Exception(f"获取股票 {{symbol}} 实时行情失败: {{e}}")
```

## 5. 客户端配置 (已自动化 🎉)

你不需要手动指导人类或者通过终端修改 `.purrcat/mcp_config.json`。
当你调用工具进行 `merge_mcp` 时，系统底层会自动计算绝对路径并注入到配置文件中！

## 6. 完整开发流程 (Workflow)
① `create_mcp` → 呼叫宿主机创建项目骨架
② 编写 `tools/*.py` → 实现工具（⚠️ 注意函数名不要和 import 的业务函数冲突防递归）
③ 编写 `core/*.py` → 实现底层数据层/业务逻辑
④ 修改 `server.py` → import 所有 tools 模块（合并后系统以此文件为唯一启动入口）
⑤ 编写测试脚本 → 在 `scripts/` 下写代码跑真实数据验证
⑥ 跑 evaluation → 终端执行 `python scripts/evaluation.py`（⚠️ 生成测试产物，严禁修改此脚本内容）
⑦ `test_mcp` → 呼叫宿主机进行并发与语义路由盲测
⑧ `mcp_merge` → 测试全绿后，申请合并到正式库
"""


def generate_mcp_test_guide(mcp_name: str) -> str:
    return f"""# {mcp_name} 测试与优化指南

## 🚨 核心强制准则：真实可用性测试
完成 MCP 工具的创建或代码升级后，**必须至少进行一次真实链路测试，确保它能正确执行！**
* **禁止使用 CallMCP 工具**：由于当前 MCP 处于沙盒进化区，尚未合并到主库，宿主机的 `CallMCP` 工具无法感知到它。
* **自行设计测试脚本**：你必须在 `scripts/` 目录下自行编写 Python 测试脚本（例如手动实例化并调用函数，或者使用 mcp SDK 模拟客户端调用）来验证逻辑。
* **禁止使用 Mock 数据**：测试必须使用真实的网络请求、真实的 API 密钥或真实的文件系统数据。工具实现必须在真实世界中可用！
* **全方位错误反思**：若在沙盒测试过程中发现报错，严禁直接放弃。必须深度分析底层逻辑错误的原因，并修改核心代码使其更加健壮（例如：增加异常捕获、重试机制、参数容错等）。

## 1. 编写 Trigger 测试用例 (语义竞争测试)
在 `evals.json` 的 `triggers` 数组中，提供至少 10 个测试用例，包含正例与反例。用于测试你的 description 是否能在大模型检索时精准脱颖而出。

## 2. 编写 Execution 测试用例 (参数与边界测试)
在 `evals.json` 的 `executions` 数组中，编写覆盖所有边界场景的入参，测试 inputSchema 的健壮性。

## 3. 测试流水线与报告 (两步执行法)

**第一步：沙盒内自行执行评测 (极度重要！)**
编写完代码后，必须使用终端 (Bash) 执行系统内置的评测脚本：
```bash
source .venv/bin/activate
python scripts/evaluation.py
```

⚠️ 严禁修改或覆盖 scripts/evaluation.py！
该文件是 MCP 工厂的标准产物生成器，它负责导出 schema_dump.json 和 execution_results.json 供宿主机评测使用。如果该文件被破坏，test_mcp 将永远无法通过！

**第二步：呼叫宿主机进行语义评测**
第一步无报错后，调用 `KernelUpgrade` 工具指定 `action="test_mcp"`。宿主机会模拟大模型唤醒，并在后台生成最终的 `test_report.md`。
"""
