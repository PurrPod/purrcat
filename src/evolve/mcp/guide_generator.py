"""
MCP 指南生成器模块 (evolve/mcp/guide_generator.py)
单文件指南：覆盖开发、测试与提交全流程。
"""


def generate_mcp_guide(mcp_name: str, goal: str = "", agent_vm_dir: str = "") -> str:
    goal_section = f"\n> 🎯 **本次构建目标**：{goal}\n\n" if goal else ""
    path_section = (
        f"\n> 🗺️ **路径映射**：MCP 服务在**宿主机**上运行，所有相关路径必须按宿主机环境定义；"
        f"沙盒 `/agent_vm` 对应宿主机 `{agent_vm_dir}`。\n\n"
        if agent_vm_dir
        else ""
    )
    return f"""# {mcp_name} MCP 工厂指南 (GUIDE)

{goal_section}{path_section}## 1. 架构（防循环导入）
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
* 🔴 **每次改动代码或工具描述后**，建议重新执行 `python scripts/evaluation.py` 刷新快照，避免报告用旧描述渲染。宿主机只读快照、**不会自动重跑**；若 schema_dump 比源码旧，`test_mcp` 会在返回中给出"快照可能已过期"提醒（不拦截，可自行判断是否忽略）。

## 4. 测试用例（evals.json）
* `triggers`：至少 10 个正反例，检验 description 的语义竞争力；反例 `expected_tool` 设为 `null`。
* `executions`：**最好不要超过 10 个用例，工具过多的话可以适当增加**（真实链路并发，过多会显著拉长盲测耗时）。覆盖所有边界场景的入参，检验 inputSchema 健壮性。每个执行用例按实际数据特性选一档断言：
  * **稳定不变量**（标记/字段名/错误信息/布尔）→ `expected_output`：校验返回值包含该子串。
  * **易变实时数据**（价格/排名/数量等会漂移）→ `not_empty: true`：只断言"返回非空"，不对具体值下判断，避免值漂移误红。
  * **预期报错**（参数校验、越界）→ `"expect_error": true`：必须抛错才 PASS，否则负例会误判为失败；可用 `error_contains` 再校验异常关键字。
  * 三种都不写 = 只证明"没抛异常"，证明不了结果，属于弱覆盖。

## 5. 路径与宿主机环境 🚨 必读
MCP 合并后将在**宿主机**上运行（宿主机读取 mcp_config.json 并以子进程启动你的 server），
而非当前沙盒！因此配置与代码中的所有相关路径（`--directory`、文件读写路径等）
都必须按**宿主机环境**定义：
* 当前沙盒根目录与宿主机的映射关系：`/agent_vm` → `{agent_vm_dir}`
* 示例：沙盒内路径 `/agent_vm/mcp_workplace/xxx` 在宿主机上是 `{agent_vm_dir}/mcp_workplace/xxx`
* 🔴 严禁在配置或代码中硬编码沙盒路径（`/agent_vm/...`）：合并后在宿主机上运行时路径不存在，启动即失败。
  优先使用相对路径（如 `--directory "."`，系统合并时自动定位到正式目录）；
  确需绝对路径时，必须通过上述映射换算为宿主机真实路径。

## 6. 配置文件（mcp_server_config.json）🚨 必读
系统已在沙盒根目录为你生成标准配置文件 `mcp_server_config.json`。
开发完成后你**必须**根据实际情况修改它，合并时系统将**完全依赖该文件**注册你的 MCP！
1. **启动命令**：入口文件不是 `server.py`，或通过 `uvx` 等指令启动时，务必修改 `command` 和 `args`
   （`uv run` 的 `--directory` 可写相对路径 `.`，合并时系统会自动定位到正式目录）。
2. **环境变量 (env)**：依赖外部 API Key 或参数时，**必须**在 `env` 字典中显式声明。
   * 示例：`"env": {{"OPENAI_API_KEY": "", "CUSTOM_PORT": "8080"}}`
   * 敏感密钥的值请留空字符串 `""`，框架合并后用户会在主配置中填写真实密钥。
   * 🔴 代码侧读取范式：合并后 `env` 会注入 MCP 子进程的环境变量，工具代码中必须用
     `os.getenv("OPENAI_API_KEY")` 读取（**不要硬编码密钥**），并处理缺失场景：
     ```python
     key = os.getenv("OPENAI_API_KEY")
     if not key:
         raise ValueError("缺少 OPENAI_API_KEY，请用户在 mcp_config.json 中补填后重试")
     ```
3. 该文件必须是格式合法的 JSON 且**不得重命名**，否则合并将直接报错失败！

## 7. 流水线
① 编写 `tools/`、`core/` → ② `bash setup.sh` 建环境 → ③ `scripts/` 真实链路自测 →
④ `python scripts/evaluation.py` 生成 schema_dump 与执行产物 →
⑤ `KernelUpgrade(action="test_mcp")` 呼叫宿主机盲测 →
⑥ 检查并修正 `mcp_server_config.json` →
⑦ 测试全绿后通过 `Request(request_type="mcp_merge")` 申请合并。
"""
