# SPEC-025：MCP Apps 对接与聊天内渲染

## 背景

PurrCat 的 MCP 网关只支持 stdio 传输，且丢弃 `tools/list` 返回的 `_meta`，因此无法发现、读取、渲染 MCP Apps（`ui://` 资源）。
用户需要先在本地 CesiumJS Map Server（`http://127.0.0.1:3001/mcp`）上看到三维地球直接渲染在聊天里。

## 行为

- MCP Server 配置里带 `url` 时走 Streamable HTTP 传输，且访问本地地址不受系统代理影响。
- 工具声明了 `_meta.ui.resourceUri` 时，调用成功后 Host 读取该 UI 资源，保存为按 `tool_call_id` 定位的旁路文件（HTML 与元数据分离）。
- 历史接口对 tool 消息附加 `mcp_app` 字段（仅有可渲染资源时），模型可见的消息结构不变。
- 前端聊天历史把该 tool 消息渲染为 iframe 卡片，完成 `ui/initialize` / `initialized` / `tool-input` / `tool-result` / `size-changed` / `tools/call` 的最小桥接。

## 验收标准

- [ ] AC-1：`config_fingerprint` 对 `url`、`headers` 变化敏感，未配置 `url` 的旧配置指纹不变。
- [ ] AC-2：`ui_resource_uri` 能从工具 `_meta` 提取资源地址，缺失时返回 None。
- [ ] AC-3：非法 app id（路径穿越、空串、超长）被拒绝，不会读写到旁路目录之外。
- [ ] AC-4：`attach_history_apps` 不修改入参，只给存在旁路文件的 tool 消息附加 `mcp_app`。
- [ ] AC-5：`GET /api/mcp/apps/{id}/html` 与 `/payload` 能取回保存的 HTML 与调用参数/结果；未知 id 返回 404，非法 id 返回 400。
- [ ] AC-6：`POST /api/mcp/apps/{id}/call` 只允许调用该 App 所属 server 的工具。
- [ ] AC-7：`GET /api/config/mcp/tools` 按 server 分组返回 schema 缓存中的工具，跳过缺 server/工具名的条目。
- [ ] AC-8：设置中心 MCP 标签可直接新增 stdio / http 服务器，并在卡片上展示该服务器暴露的工具。

## 非目标

- 不做 MCP Apps 的完整规范（资源订阅、host 端 UI 权限提示、多 App 通信）。
- 不改模型可见的 tool 消息结构，不改 `CallMCP` 的既有返回格式（仅允许追加一行提示）。
- 不支持 OAuth 认证的远程 MCP。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_mcp_apps.py` | AC-1 ~ AC-6 的纯函数部分 |
| L0 | `tests/l0/test_api_config_mcp_tools.py` | AC-7 |
| L1 | 端到端手测（本地 map server） | AC-5、AC-6 的真实 HTTP 行为 |

## 风险与回滚

- 旁路文件体积较大（单 App HTML 可达数 MB），写在 `BUFFER_DIR/mcp_apps/`，不进入会话与模型上下文。
- 历史接口每轮轮询只做一次文件存在性判断，不读取 HTML。
- 回滚：移除 `_meta` 缓存与路由注册即可恢复原行为，旁路文件可整体删除。
