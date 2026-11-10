# SPEC-014：Server API 包的职责拆分

## 背景

`src/server/api/` 是 HTTP 边界层，但 `tools.py`（1664 行）同时承载路由声明、市场注册表解析、请求校验、远程下载、zip 解包、依赖补齐与响应组装；`webmin.py`、`chat.py`、`config.py` 也存在可复用的 JSON 读写、路径安全与 payload 组装样板。任何一处调整都要在长文件里定位，纯逻辑也无法脱离网络/磁盘直接测试。

## 行为

- 所有既有 HTTP 路由的路径、方法、请求/响应字段、状态码与业务语义逐字不变。
- 工具市场相关职责拆为：
  - `tools_registry.py`：注册表发布地址、条目提取、依赖归一化、本地已安装扫描等纯逻辑；
  - `tools_validation.py`：GitHub URL 解析、名称白名单、相对路径防御、MCP 配置 JSON 解析；
  - `tools_serialization.py`：注册表响应、安装结果、心跳与 Sensor 合并等 payload 组装；
  - `tools_market.py`：远程下载、zip 解包、依赖补齐与按名安装编排；
  - `tools.py`：仅保留路由声明与薄委托，并保留 kernelupgrade 依赖的历史入口名。
- `common.py` 提供 JSON 落盘/读取、未预期异常→HTTPException 映射、路径越界判断、注册表条目与依赖归一化。
- `webmin.py` 的清单归一化移入 `webmin_manifest.py`；`chat.py`、`system.py`、`task.py`、`projects.py`、`filesystem.py`、`config.py` 的可测纯逻辑改为模块级函数。

## 验收标准

- [x] AC-1：15 个 API router 的路由表（路径 + 方法 + 端点名）与重构前完全一致。
- [x] AC-2：工具市场注册表提取、依赖白名单、名称校验、URL 解析有 L0 用例。
- [x] AC-3：请求解析/响应组装/路径校验/清单归一化等纯函数有 L0 用例。
- [x] AC-4：若干 GET 路由经 TestClient 验证路径与响应字段，不联网、不启动真实 Agent。
- [x] AC-5：`uv run pytest -q tests/l0 tests/l1` 与 `uv run ruff check src/server tests/l0 tests/l1` 通过。

## 非目标

- 不新增、删除或重命名任何 HTTP 接口。
- 不改动 `plugin_runtime.py` 的进程治理模型与通信协议。
- 不为简单路由新增抽象，不改变 `docs/api` 已描述的行为。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_api_tools_registry.py` | AC-2 |
| L0 | `tests/l0/test_api_payloads.py` | AC-3 |
| L1 | `tests/l1/test_api_routes_contract.py` | AC-1、AC-4 |

## 风险与回滚

- 风险：拆分时遗漏历史入口名，导致 `src/tool/kernelupgrade` 懒加载失败；`tools.py` 以原名重导出并纳入 `__all__`。
- 风险：响应字段顺序或异常消息漂移；以路由契约与纯函数用例锁定。
- 回滚：按模块边界恢复单文件实现，测试可直接复用。
