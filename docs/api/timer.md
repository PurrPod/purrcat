# 定时任务 `/api/timer`

> 源码：`src/server/api/timer.py` ｜ 前缀：`/api/timer` ｜ 端点：6 个

通用定时任务中心：任意组件按「来源 `source` / 去向 `target` / 效果 `effect`」派发事件，服务在事件库变更时计算下次唤醒时间并精确 sleep，空闲时不轮询。事件持久化在 `~/.purrcat/data/schedule/timer_events.json`。

- `target`：`main`（主 Agent）、`agent`、`graph:<名称>`、`ui:<名称>`。
- `effect`：任意的效果描述；`target=main` 时 sink 读取 `effect.signal == "heartbeat"` 或 `effect.payload.content`。
- `repeat`：`{"interval": 秒}` 或 `{"daily": "HH:MM"}`；缺省为一次性事件。
- `catch_up`：进程重启后对已过期事件的处理，`skip`（默认）或 `once`。
- `dedupe_key`：同一 `source + dedupe_key` 的新事件会取消旧的 pending 事件。
- `result`：接收方最近一次回执，`{"action", "data", "at", "attempt"}`；随事件落盘，并随 SSE 广播回传给 source。

## POST `/api/timer/events`

新增单个定时事件。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `source` | body | string | 是 | 事件来源，如 `note:2026-11-17`、`heartbeat` |
| `target` | body | string | 是 | 去向，见上文取值 |
| `at` | body | number | 是 | 首次触发时间（Unix 秒） |
| `effect` | body | object | 否 | 效果描述 |
| `repeat` | body | object \| null | 否 | 重复规则；缺省为一次性 |
| `catch_up` | body | string | 否 | `skip`（默认）/ `once` |
| `dedupe_key` | body | string | 否 | 同来源内的去重键 |
| `id` | body | string \| null | 否 | 指定事件 ID；缺省自动生成 |

**响应**

```json
{
  "id": "note:2026-11-17:0",
  "source": "note:2026-11-17",
  "target": "main",
  "at": 1763341200.0,
  "effect": { "signal": "note_item", "payload": { "title": "喝水" } },
  "repeat": null,
  "catch_up": "skip",
  "dedupe_key": "540|喝水",
  "status": "pending",
  "result": null
}
```

缺少 `source` 或字段非法时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/timer/events' -H 'Content-Type: application/json' \
  -d '{"source":"note:2026-11-17","target":"main","at":1763341200,"effect":{"signal":"note_item"}}'
```

---

## PUT `/api/timer/sources/{source}`

声明式替换某个来源的全部 pending 事件（reconcile）：未出现在本次列表中的旧事件会被取消，`source` 以路径参数为准。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `source` | path | string | 是 | 事件来源 |
| `events` | body | array | 是 | 该来源期望保留的事件列表，元素字段同 `POST /events`（`source` 被忽略） |

**响应**

返回替换后该来源的事件数组（结构同 `POST /events`）。

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/timer/sources/note:2026-11-17' -H 'Content-Type: application/json' \
  -d '{"events":[{"target":"main","at":1763341200,"effect":{"signal":"note_item"}}]}'
```

---

## GET `/api/timer/events`

列出事件，默认只返回 `pending`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `source` | query | string | 否 | 只返回该来源的事件 |
| `include_finished` | query | boolean | 否 | `true` 时包含 `done` / `cancelled` 等终态事件 |

**响应**

事件对象数组，结构同 `POST /events`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/timer/events?source=heartbeat'
```

---

## DELETE `/api/timer/events/{event_id}`

取消指定事件。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `event_id` | path | string | 是 | 事件 ID |

**响应**

```json
{ "status": "success", "id": "heartbeat" }
```

事件不存在时返回 `404`。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/timer/events/heartbeat'
```

---

## 回执与任务跟踪

接收方返回的 `Signal.data` 会写入事件的 `result`，并在 SSE 中同时以 `result` 字段广播。source 按 `event.source` 过滤即可拿到反馈：

1. 插件用 `source=plugin:demo` 创建事件，`target=graph:daily`；
2. Timer 到点后启动 DAG，graph sink 立即返回 `{"graph": "daily", "task_id": "..."}`；
3. Timer 广播 `fired`，`result.action` 为 `done`，`result.data` 含 `task_id`；
4. 插件按 `event.source === "plugin:demo"` 过滤，拿到 `task_id` 后查询 `/api/tasks` 跟踪进度；
5. 插件离线错过的回执，可用 `GET /api/timer/events?source=plugin:demo&include_finished=true` 补读。

`defer` 会先广播一次 `rescheduled`，之后还会再广播 `fired`，source 需按 `event.id` 允许多次回执。

---

## GET `/api/timer/state`

读取定时器运行状态。

**请求**

无参数。

**响应**

```json
{
  "pending": 2,
  "counts": { "pending": 2, "done": 5, "cancelled": 0 },
  "next_at": 1763341200.0,
  "running": true,
  "events": []
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/timer/state'
```

---

## GET `/api/timer/stream`

SSE 事件流：事件触发后推送 `event: timer`，`data` 为触发事件对象；无事件时每 15 秒发送一次 keepalive。

**请求**

无参数。

**响应**

```text
event: timer
data: {"type":"fired","signal":"done","event":{"id":"heartbeat","source":"heartbeat","target":"main","status":"done","result":{"action":"done","data":{},"at":1763341200.0,"attempt":1}},"result":{"action":"done","data":{},"at":1763341200.0,"attempt":1}}
```

**示例**

```bash
curl -N 'http://127.0.0.1:8000/api/timer/stream'
```
