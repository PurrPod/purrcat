# SPEC-021：Server API 大文件的服务层拆分

## 背景

`src/server/api/` 中仍有若干文件把路由声明、远程下载、磁盘落盘、依赖决策与视图序列化堆在一起，纯逻辑无法脱离网络或真实 `~/.purrcat` 单独测试：`tools_market.py`（约 760 行）、`chat.py`（约 540 行）、`evolve.py`（约 520 行）、`plugin_runtime.py` / `webmin.py`（约 410 行）、`task.py`（约 346 行）。

## 行为

- `tools_market.py` 拆为三个同包模块，原文件只做同名再导出：
  - `market_archive.py`：远程 GET/下载、仓库 zip 候选分支、解压目标前缀、SKILL.md 校验、官方 MCP 源码下载；
  - `market_install.py`：配置合并、按名安装、依赖补齐、卸载与热更新编排；
  - `market_state.py`：注册表条目提取、缺失判定、MCP/Skill 依赖计划、核心文件排序、卸载 404 决策。
- `chat.py` 拆出 `chat_views.py`：会话列表归一化、单会话状态裁剪、批量事件缓冲替换、token 进度 payload；`chat.py` 保留同名导入以兼容旧调用。
- `evolve.py` 拆出 `evolve_service.py`：沙盒扫描、文件读写、范式 YAML、评测启动、报告/基准读取、Diff 与回滚编排；路由仅保留 Pydantic 模型与薄委托。
- `plugin_runtime.py` 拆出 `plugin_runtime_support.py`：进程入口定位、venv 环境剥离、package 指纹、依赖就绪判定；`PluginProcessError` 在 `plugin_runtime` 保持同名可导入。
- `webmin.py` 拆出 `webmin_scan.py`：插件清单扫描、多根覆盖、静态资源路径沙箱、后端入口探测；根目录由调用方注入。
- `task.py` 拆出 `task_views.py`：日志分组、checkpoint 定位、节点消息优先级读取与前端记忆合并。
- 所有 HTTP 路由路径、方法、端点函数名、状态码、请求/响应字段与业务语义逐字不变；`system.py` / `terminal.py` 未发现需拆的混合职责，保持原样。

## 验收标准

- [ ] AC-1：仓库 zip 下载候选顺序、skill 解压目标前缀与 SKILL.md 拒绝语义不变。
- [ ] AC-2：MCP/Skill 缺失判定、依赖计划与注册表兼容形态（dict / list）不变。
- [ ] AC-3：卸载 MCP 的 404 语义、配置重写与源码目录清理不变。
- [ ] AC-4：token 状态在「非当前会话 / 当前会话 / 无 Agent」三种分支的 payload 不变。
- [ ] AC-5：会话列表与状态的字段集合、排序与 idle 掩码不变。
- [ ] AC-6：插件清单扫描跳过 `.trash`/坏 JSON，多根优先级与路径穿越拒绝不变。
- [ ] AC-7：依赖指纹与 `deps_ready` 判定（有无运行时依赖、node_modules）不变。
- [ ] AC-8：任务状态 `node_memory` 的 memory.jsonl → live_memory.json → outputs.json 优先级不变。
- [ ] AC-9：`test_api_routes_contract`、`check_api_docs.py` 与全量 L0/L1 全绿。

## 非目标

- 不新增、删除或重命名任何 HTTP 接口，不调整路由注册顺序。
- 不改变远程 URL、超时、落盘路径、错误文案与热更新调用顺序。
- 不重构 `config.py` / `config_services.py` / `common.py`。
- 不引入包内循环导入，不扩大公开导入面。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_api_market_flow.py` | AC-1、AC-2、AC-3 |
| L0 | `tests/l0/test_api_chat_views.py` | AC-4、AC-5 |
| L0 | `tests/l0/test_api_plugin_manifest.py` | AC-6、AC-7 |
| L0 | `tests/l0/test_api_task_views.py` | AC-8 |
| L1 | `tests/l1/test_api_routes_contract.py` | AC-9 |

## 风险与回滚

- 风险：旧调用方仍按原模块导入被移走的函数。原模块保留同名再导出 / 薄委托，并以既有 L1 契约用例锁定。
- 风险：拆解时改动异常文案或分支顺序。以新 L0 characterization 用例逐字段断言，路由层零逻辑迁移。
- 风险：`webmin_scan` 与 `plugin_runtime_support` 从 `webmin`/`plugin_runtime` 反向导入形成环。新模块只依赖 `common` 与标准库。
- 回滚：按文件边界恢复单文件实现，新增 L0 用例可原样复用。
