# MCP Apps `/api/mcp/apps`

> 源码：`src/server/api/mcp_apps.py` ｜ 前缀：`/api/mcp/apps` ｜ 端点：3 个

MCP 工具声明 `_meta.ui.resourceUri` 时，调用结果会按 `tool_call_id` 落盘为一份 MCP App（HTML + 调用载荷），
聊天历史接口给对应 tool 消息附上 `mcp_app` 标记（见 [chat.md](chat.md)）。本组接口供前端 iframe 取回资源、
以及代理由 App 发起的 `tools/call`。id 只接受 `[A-Za-z0-9_-]{1,128}`。

---

## GET `/api/mcp/apps/{app_id}/html`

返回 App 的单文件 HTML，供 iframe 直接加载（响应 `Cache-Control: no-store`）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `app_id` | path | string | 是 | 即 `tool_call_id`，来自历史消息的 `mcp_app.id` |

**响应**

`text/html`。id 非法返回 400，App 不存在或已被清理返回 404。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/mcp/apps/call_xxx/html'
```

---

## GET `/api/mcp/apps/{app_id}/payload`

返回 App 初始化所需的数据：工具入参与调用结果。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `app_id` | path | string | 是 | App id |

**响应**

```json
{
  "id": "call_xxx",
  "server": "cesium-map",
  "tool": "show-map",
  "uri": "ui://cesium-map/mcp-app.html",
  "arguments": { "west": 2.2, "south": 48.8, "east": 2.4, "north": 48.9 },
  "result": { "content": [{ "type": "text", "text": "..." }], "structuredContent": null, "_meta": null }
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/mcp/apps/call_xxx/payload'
```

---

## POST `/api/mcp/apps/{app_id}/call`

代理 App 发起的 `tools/call`：只允许调用该 App 所属 MCP Server 的工具。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `app_id` | path | string | 是 | App id |
| `tool` | body | string | 是 | 工具名 |
| `arguments` | body | object | 否 | 工具入参，默认 `{}` |

**响应**

```json
{
  "content": [{ "type": "text", "text": "..." }],
  "isError": false
}
```

服务器未配置或调用失败返回 502。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/mcp/apps/call_xxx/call' \
  -H 'Content-Type: application/json' \
  -d '{"tool":"geocode","arguments":{"query":"Paris"}}'
```
