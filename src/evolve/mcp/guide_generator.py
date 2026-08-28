"""
MCP 指南生成器模块 (evolve/mcp/guide_generator.py)
单文件指南：覆盖开发、测试与提交全流程。
"""


def generate_mcp_guide(mcp_name: str, goal: str = "") -> str:
    goal_section = f"\n> 🎯 **本次构建目标**：{goal}\n\n" if goal else ""
    return f"""# {mcp_name} MCP 工厂指南 (GUIDE)

{goal_section}## 1. 架构（防循环导入）
* `app.py`：全局实例，只有一行 `mcp = FastMCP("{mcp_name}")`。
* `server.py`：主入口，导入 app 与所有 tools（合并后系统以它为唯一启动入口）。
* `tools/`：所有 Tool 函数写这里，从 app 导入 mcp 实例（⚠️ 工具函数名勿与 import 的业务函数同名，防递归）。
* `core/`：底层数据层/业务逻辑。

## 2. Tool 编写规范
* Docstring 第一行 = 工具功能描述，直接决定意图路由测试能否通过。
* `Args:` 块解释每个参数的含义与格式，帮助大模型正确提取实体。
* 必须有 Type Hint（`str`/`int`/`list[str]`...）；有默认值 = 可选参数。
* 在 `server.py` 中 `import tools.xxx` 才会被 FastMCP 扫描注册。
* 🔴 红线：禁止 `print()` 到 stdout（污染 STDIO 协议会崩溃），统一用 `logging.info()`。
* 异常信息必须包含「错在哪 + 正确格式 + 示例」，让大模型能自我修正。

## 3. 真实可用性测试
* 禁用 CallMCP（沙盒未合并，宿主机感知不到）；禁用 Mock 数据，必须真实链路可用。
* 在 `scripts/` 下自行编写测试脚本验证逻辑；发现报错严禁放弃，必须修复核心代码使其健壮。
* 🔴 严禁修改 `scripts/evaluation.py`（工厂标准产物生成器，破坏后 test_mcp 永远无法通过）。

## 4. 测试用例（evals.json）
* `triggers`：至少 10 个正反例，检验 description 的语义竞争力。
* `executions`：覆盖所有边界场景的入参，检验 inputSchema 健壮性。

## 5. 配置文件（mcp_server_config.json）🚨 必读
系统已在沙盒根目录为你生成标准配置文件 `mcp_server_config.json`。
开发完成后你**必须**根据实际情况修改它，合并时系统将**完全依赖该文件**注册你的 MCP！
1. **启动命令**：入口文件不是 `server.py`，或通过 `uvx` 等指令启动时，务必修改 `command` 和 `args`
   （`uv run` 的 `--directory` 可写相对路径 `.`，合并时系统会自动定位到正式目录）。
2. **环境变量 (env)**：依赖外部 API Key 或参数时，**必须**在 `env` 字典中显式声明。
   * 示例：`"env": {{"OPENAI_API_KEY": "", "CUSTOM_PORT": "8080"}}`
   * 敏感密钥的值请留空字符串 `""`，框架合并后老板会在主配置中填写真实密钥。
   * 🔴 代码侧读取范式：合并后 `env` 会注入 MCP 子进程的环境变量，工具代码中必须用
     `os.getenv("OPENAI_API_KEY")` 读取（**不要硬编码密钥**），并处理缺失场景：
     ```python
     key = os.getenv("OPENAI_API_KEY")
     if not key:
         raise ValueError("缺少 OPENAI_API_KEY，请老板在 mcp_config.json 中补填后重试")
     ```
3. 该文件必须是格式合法的 JSON 且**不得重命名**，否则合并将直接报错失败！

## 6. 流水线
① 编写 `tools/`、`core/` → ② `bash setup.sh` 建环境 → ③ `scripts/` 真实链路自测 →
④ `python scripts/evaluation.py` 生成 schema_dump 与执行产物 →
⑤ `KernelUpgrade(action="test_mcp")` 呼叫宿主机盲测 →
⑥ 检查并修正 `mcp_server_config.json` →
⑦ 测试全绿后通过 `Request(request_type="mcp_merge")` 申请合并。
"""
