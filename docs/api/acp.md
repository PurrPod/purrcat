# ACP 网关 `/acp`

> 源码：`src/server/api/acp.py` ｜ 前缀：`/acp` ｜ 端点：4 个

面向外部频道（Zed 转接 sensor / HTTP 版 sensor）的传输入口。词汇分发与翻译的唯一实现是 `src/server/acp/dispatch.py`；stdio 版 sensor 由 `src/sensor/bridge.py` 同进程直调 dispatch，不经本端点。

**约定**

- 前缀为 `/acp`（非 `/api`）。
- 全部端点均需本地鉴权：请求头携带 `X-PurrCat-Token`，取值须等于 `~/.purrcat/acp_token` 的内容，否则返回 `401` 与 `{ "detail": "invalid ACP token" }`。
- 会话标识在 rpc 语境下称 ACP `session`（映射到 purrcat 会话 id）。

---

## POST `/acp/rpc`

JSON-RPC 2.0 单条分发（v1 不做 batch），直接调用 dispatch。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `X-PurrCat-Token` | header | string | 是 | ACP 网关令牌 |
| （JSON-RPC 报文） | body | object | 是 | 标准 JSON-RPC 2.0 对象，含 `jsonrpc`、`id`、`method`、`params` |

**响应**

```json
{ "jsonrpc": "2.0", "result": {}, "id": 1 }
```

响应体由 `handle_rpc` 直接返回，结构随 `method` 而定；不合法调用按 JSON-RPC 规范返回 `error`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/acp/rpc' \
  -H 'X-PurrCat-Token: <token>' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
```

---

## GET `/acp/stream`

按 ACP `session` 订阅对应 purrcat 会话的事件流，将内部事件翻译为 ACP 词汇后推送。每 15 秒无事件时发送一行 `: keepalive` 心跳。支持 `session/load` 前置流场景（编辑器先连流再发 load）：此时映射尚未建立，只要该 id 存在于 purrcat 会话列表即放行订阅。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `X-PurrCat-Token` | header | string | 是 | ACP 网关令牌 |
| session | query | string | 是 | ACP 会话 id（同时也是映射前的 purrcat 会话 id） |

**响应**

`text/event-stream` 流，事件名与载荷如下：

```text
event: update
data: {"method":"session/update","params":{"sessionId":"<session>", ...}}

event: turn_end
data: {"stopReason":"end_turn","promptId":"<promptId>", ...}

event: replay_end
data: {"replayDone":true, ...}

event: phase
data: { ... }
```

`session/update` 载荷回填 ACP `sessionId`；`turn_end` 回填 `promptId`。会话既不在映射表也不在 purrcat 会话列表时返回 `404` 与 `{ "detail": "unknown sessionId: <session>" }`。

**示例**

```bash
curl -N 'http://127.0.0.1:8000/acp/stream?session=<session>' \
  -H 'X-PurrCat-Token: <token>'
```

---

## POST `/acp/file`

multipart 上传文件，落盘到 `agent_vm/sensor/files/acp/`，返回可直接在 prompt 里引用的 sandbox 路径。文件名只保留 basename 并清洗 Windows 非法字符以防路径穿越。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `X-PurrCat-Token` | header | string | 是 | ACP 网关令牌 |
| file | form-data | file | 是 | 上传文件（`multipart/form-data` 字段名 `file`） |
| session | query | string | 否 | ACP 会话 id；须为已登记会话，否则 `404` |

**响应**

```json
{
  "path": "/agent_vm/sensor/files/acp/1712345678901_foo.txt",
  "size": 1024
}
```

`session` 不在会话登记表中时返回 `404` 与 `{ "detail": "unknown sessionId: <session>" }`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/acp/file?session=<session>' \
  -H 'X-PurrCat-Token: <token>' \
  -F 'file=@./foo.txt'
```

---

## GET `/acp/file`

下载 sandbox 文件，仅允许 `/agent_vm` 前缀路径，防止任意路径读取。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `X-PurrCat-Token` | header | string | 是 | ACP 网关令牌 |
| path | query | string | 是 | sandbox 路径，须以 `/agent_vm/` 开头 |

**响应**

直接返回文件流（`FileResponse`），无 JSON 包装。

路径不以 `/agent_vm/` 开头时返回 `400` 与 `{ "detail": "only /agent_vm paths allowed" }`；解析后的宿主机路径未落在 AgentVM 根内或不是普通文件时返回 `404` 与 `{ "detail": "file not found" }`。

**示例**

```bash
curl -OJ 'http://127.0.0.1:8000/acp/file?path=/agent_vm/sensor/files/acp/1712345678901_foo.txt' \
  -H 'X-PurrCat-Token: <token>'
```
