"""
MCP 指南生成器模块 (evolve/mcp/guide_generator.py)
"""

def generate_mcp_create_guide(mcp_name: str) -> str:
    return f"""# {mcp_name} MCP Server 模块化开发指南

系统已为你生成了结构化的工程目录。请严格遵循以下开发范式：

## 1. 项目架构说明
* `server.py`: 主入口。实例化 `mcp` 对象，并负责运行服务。
* `core/config.py`: 存放全局配置、常量、以及防污染的日志配置。
* `tools/`: **你的核心工作区**。所有具体的 Tool 函数都应该写在这里。

## 2. 如何添加新的 Tool？(两步法则)
为了保持代码整洁，请不要把函数写在 `server.py` 里。

**步骤一：在 `tools/` 目录下创建新的 Python 文件 (如 `weather.py`)**
你需要从 `server` 模块导入 `mcp` 实例来使用装饰器：
```python
from server import mcp
import logging

@mcp.tool()
async def get_weather(city: str) -> str:
    \"\"\"描述语句，大模型据此调用\"\"\"
    return "Sunny"
```

**步骤二：在 `server.py` 中注册它 (极度重要！)**
如果你只写了文件但没有在入口导入它，装饰器将不会执行！你必须在 `server.py` 的指定位置追加导入：

```python
# 3. 导入 Tools
import tools.sample
import tools.weather  # <--- 新增这行，激活 tool
```

## 3. 🔴 绝对红线：STDIO 日志污染 (CRITICAL)

**绝对禁止使用标准的 `print()` 将内容输出到 stdout！**
因为底层走的是 STDIO 上的 JSON-RPC 通信，往 stdout 打印任何非 JSON-RPC 格式的内容都会导致服务端和客户端通信崩溃。

* **正确做法**：使用 `print("your log", file=sys.stderr)`，或者直接使用预置好的 `logging` 模块。

## 4. 业务容错处理

如果执行过程中出现业务逻辑错误（如参数格式不对、API 返回失败），不要直接抛出 Python Exception，而是利用 `isError` 告知大模型，让大模型能自行重试：

```python
return {{
    "content": [{{"type": "text", "text": "你提供的日期格式不合法，请使用 YYYY-MM-DD"}}],
    "isError": True
}}

```

## 5. 测试与验证准备
代码编写完成后，你必须进行自动化测试。系统已为你生成了 `02_GUIDE_TEST.md`、`evals/evals.json` 和 `scripts/evaluation.py`。请在申请合并前，先阅读测试指南并完善测试用例！

"""


def generate_mcp_test_guide(mcp_name: str) -> str:
    return f"""# {mcp_name} 测试与优化指南 (How to Test MCP)

MCP 工具的可用性由两部分决定：大模型是否知道什么时候调用它（Trigger），以及调用时传参是否正确（Execution）。
系统已经在沙盒中为你生成了 `evals/evals.json`。在调用 `KernelUpgrade` 工具的 `test_mcp` 操作前，你必须完善它。

## 1. 编写 Trigger 测试用例 (激发测试)
在 `evals.json` 的 `triggers` 数组中，**请务必提供至少 10 个测试用例**。
* **目的**：测试你写的 `docstring` (即 description) 是否足够精准，大模型能否根据用户的自然语言正确选中对应的 Tool。
* **要求**：包含正例（应该调用的场景）、口语化表述、甚至是一些容易混淆的反例（不该调用你的场景，expected_tool 填 null）。

## 2. 编写 Execution 测试用例 (执行与 InputSchema 测试)
在 `evals.json` 的 `executions` 数组中，编写覆盖所有边界场景的入参。
* **目的**：并发执行这些参数，验证你的 inputSchema 定义是否正确，以及底层业务逻辑是否会崩溃。
* **要求**：尝试传入正常参数、极值、甚至是故意填错的格式（验证你的 isError 处理机制）。

## 3. 测试流水线与报告 (两步执行法)
为了避免跨系统环境冲突，MCP 的测试严格分为两步，**你必须按照顺序执行**：

**第一步：沙盒内自行执行评测 (极度重要！)**
编写完代码和 `evals.json` 后，你必须使用你的终端执行工具 (Bash)，在当前 MCP 项目根目录下激活环境并运行评测脚本：
```bash
source .venv/bin/activate
python scripts/evaluation.py
```

这会在 `evals/outputs/` 目录下生成基础的执行结果和 Schema 产物。如果这一步发生代码报错，请直接通过 Bash 的输出日志进行修复。

**第二步：呼叫宿主机进行语义评测与聚合报告**
只有在第一步**无报错执行完毕**后，你才可以调用 `KernelUpgrade` 工具，指定 `action="test_mcp"`。
宿主机会读取你第一步的产物，执行复杂的**语义 Trigger 测试**（模拟大模型是否能准确唤醒你的 Tool），并在后台生成最终的 `test_report.md`。收到通知后去阅读该报告进行调优。
"""
