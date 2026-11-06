# 会话与对话

> 源码：`src/server/api/chat.py` ｜ 前缀：`/api` ｜ 端点：18 个

涵盖会话管理（`/api/sessions*`）、对话受理（`/api/chat*`）与 Agent Token 用量（`/api/agent/token`）。
其中发送消息、批量发送、记忆压缩、记忆打断等为**后台异步**接口，立即返回受理态，实际进度走 `/api/sessions/{session_id}/status` 轮询。
会话支持主体 + 子分支结构：`main` 为主干，其它 `branch_id` 为隔离子分支，历史读取与删除均按分支区分。

---

## GET `/api/sessions`

返回全部会话列表，按 `updated_at` 倒序排列。

**响应**

```json
[
  {
    "id": "session_xxx",
    "alias": "New Session",
    "messages_count": 12,
    "updated_at": "2026-10-14T10:00:00",
    "project_id": ""
  }
]
```

`project_id` 为所属项目 id；空串表示未归入任何项目（「未分类」）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/sessions'
```

---

## POST `/api/sessions/new`

新建一个会话，可选指定别名、Agent Loop（paradigm）与所属项目。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `alias` | body | string | 否 | 会话别名，默认 `New Session` |
| `paradigm` | body | string | 否 | `paradigms/` 下的文件名（不带 `.yaml`）；为空则用默认 `PARADIGM.yaml` |
| `project_id` | body | string | 否 | 项目 id；非空时把该项目 `MEMORY.md` 的路径与维护约定注入系统提示，并写入会话归属 |

> 项目记忆**只在新建时**注入一次（只给 `MEMORY.md` 的路径与维护约定，不注入正文）。把已有会话移入项目（见下方 `PUT /api/sessions/{session_id}/project`）不会改写其系统提示。

**响应**

```json
{ "id": "session_xxx", "alias": "New Session" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/sessions/new' -H 'Content-Type: application/json' -d '{"alias":"我的会话"}'
```

---

## GET `/api/sessions/{session_id}`

读取指定会话某分支的聊天历史（过滤掉 `system` 角色消息）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id |
| `branch_id` | query | string | 否 | 分支 id，默认 `main` |

**响应**

返回消息对象数组（`role` / `content` 等字段）。当 `branch_id` 为 `main` 且为 Agent 当前活跃会话时，取内存最新历史；否则按 `branch_id` 从磁盘加载对应隔离子分支历史。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/sessions/session_xxx?branch_id=main'
```

---

## GET `/api/sessions/{session_id}/branches`

返回该会话下全部活跃或已完成的子分支元数据。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id |

**响应**

```json
{ "main": { "status": "active" } }
```

分支 id 为键、元数据（含 `status`）为值；会话不存在或读取异常时回退为 `{"main": {"status": "active"}}`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/sessions/session_xxx/branches'
```

---

## GET `/api/sessions/{session_id}/status`

轻量级轮询接口：检查该会话的后台 Agent 是否仍活跃运行。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id |

**响应**

```json
{
  "is_thinking": true,
  "state": "running",
  "compressing": false,
  "live_reasoning": "",
  "phase": "thinking"
}
```

`phase` 取值：`thinking`（模型推理中）/ `processing`（工具执行中）/ `aborting`（打断等待收尾）/ `idle`（空闲）。当查询的会话不是 Agent 当前挂载会话时，`is_thinking` 为 `false`、`state` 为 `idle`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/sessions/session_xxx/status'
```

---

## PUT `/api/sessions/{session_id}/rename`

重命名会话，同步更新会话索引与元数据中的 `alias`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id |
| `alias` | body | string | 是 | 新的会话别名 |

**响应**

```json
{ "status": "ok" }
```

失败时返回 `500` 与 `{ "detail": "<reason>" }`。

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/sessions/session_xxx/rename' -H 'Content-Type: application/json' -d '{"alias":"新名字"}'
```

---

## PUT `/api/sessions/{session_id}/project`

把会话归入某个项目，或移回「未分类」。仅改归属，不改写会话既有系统提示。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id（须以 `session_` 开头） |
| `project_id` | body | string | 否 | 目标项目 id；空串表示移回「未分类」 |

**响应**

```json
{ "status": "ok", "project_id": "project_xxx" }
```

会话不存在或项目不存在时返回 `404`；`session_id` 非法时返回 `400`。

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/sessions/session_xxx/project' -H 'Content-Type: application/json' -d '{"project_id":"project_xxx"}'
```

---

## POST `/api/sessions/{session_id}/checkout`

检出/切换到指定会话。`session_id` 必须以 `session_` 开头，否则返回 `400`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id（须以 `session_` 开头） |

**响应**

```json
{ "status": "ok" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/sessions/session_xxx/checkout'
```

---

## POST `/api/sessions/{session_id}/branch`

以指定会话为起点新建一个子分支。

新建的分支会话会继承源会话所属项目（写入 `meta.json` 与 `index.json` 的 `project_id`），因此会直接归档在源会话所在的项目下。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 源会话 id |
| `alias` | body | string | 否 | 子分支别名，默认 `Branch Session` |

**响应**

```json
{ "id": "session_xxx", "alias": "Branch Session" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/sessions/session_xxx/branch' -H 'Content-Type: application/json' -d '{"alias":"试验分支"}'
```

---

## GET `/api/sessions/{session_id}/paradigm`

读取某会话当前绑定的 Agent Loop（paradigm）；空串表示使用默认 `PARADIGM.yaml`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id（含 `/`、`\`、`..` 时返回 `400`） |

**响应**

```json
{ "paradigm": "" }
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/sessions/session_xxx/paradigm'
```

---

## POST `/api/sessions/{session_id}/paradigm`

会话暂停时热切换 Agent Loop：只更换循环逻辑，不动系统提示词，保留 KV Cache。paradigm 非法时返回 `400`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id |
| `paradigm` | body | string | 否 | 目标 paradigm 名；为空表示恢复默认 `PARADIGM.yaml` |

**响应**

```json
{ "ok": true, "paradigm": null, "paradigm_path": "..." }
```

`paradigm` 为切换后的目标名（为空时返回 `null`），`paradigm_path` 为对应 YAML 的落盘路径。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/sessions/session_xxx/paradigm' -H 'Content-Type: application/json' -d '{"paradigm":"MY_LOOP"}'
```

---

## DELETE `/api/sessions/{session_id}`

删除指定会话。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id |

**响应**

```json
{ "status": "ok" }
```

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/sessions/session_xxx'
```

---

## DELETE `/api/sessions/{session_id}/branches/{branch_id}`

删除指定子分支。先斩断后台任务并等待收敛，再删除分支文件（避免运行中协程再次落盘复活分支）；主干分支禁止删除。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | path | string | 是 | 会话 id |
| `branch_id` | path | string | 是 | 分支 id（`main` 等主干禁止删除） |

**响应**

```json
{ "status": "ok" }
```

分支不存在或禁止删除时返回 `400`。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/sessions/session_xxx/branches/session_yyy'
```

---

## POST `/api/chat`

向指定会话推送一条用户消息，交由后台 Agent 异步处理。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | body | string | 是 | 目标会话 id |
| `message` | body | string | 是 | 用户消息正文 |

**响应**

```json
{ "status": "processing", "message": "Message pushed to agent" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/chat' -H 'Content-Type: application/json' -d '{"session_id":"session_xxx","message":"你好"}'
```

---

## POST `/api/chat/batch`

批量推送多条事件到指定会话。`session_id` 为空时自动路由到当前活跃会话（供 ChatPage 之外的页面触发）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | body | string | 否 | 目标会话 id；为空时路由到当前活跃会话 |
| `events` | body | array | 是 | 事件对象数组（含 `type`、`content` 等字段） |

**响应**

```json
{
  "status": "processing",
  "processed_events": [
    { "type": "user", "content": "你好" }
  ]
}
```

`processed_events` 为做过超长输入缓冲替换（与 `force_push_batch` 保持一致）后的事件副本。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/chat/batch' -H 'Content-Type: application/json' -d '{"session_id":"session_xxx","events":[{"type":"user","content":"你好"}]}'
```

---

## POST `/api/chat/interrupt`

人类强制打断：物理掐断 Agent 正在执行的工具（子进程 terminate），隔离旧响应并注入打断提示，Agent 立即回到 `idle`。

**响应**

```json
{ "status": "ok", "interrupted": true }
```

`status` 为 `ok`（成功打断）或 `no_agent`（无 Agent 实例）；`interrupted` 为布尔结果。异常时返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/chat/interrupt'
```

---

## POST `/api/chat/compress-memory`

手动触发 Agent 记忆压缩：全局大总结并截断历史上下文。内部需调用 LLM 生成摘要，耗时较长，故放后台任务避免 HTTP 超时。

**响应**

```json
{ "status": "processing" }
```

异常时返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/chat/compress-memory'
```

---

## GET `/api/agent/token`

获取上下文 Token 使用进度与本会话累计消耗。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | query | string | 否 | 前端“正在查看”的会话 id；传入且非 Agent 当前挂载会话时返回落盘用量 |

**响应**

```json
{
  "window_token": 12345,
  "max_token": 500000,
  "consumed_main": 0,
  "consumed_sub": 0,
  "consumed_total": 0
}
```

`window_token` 为上下文窗口长度，`max_token` 为当前模型上限；`consumed_*` 为本会话累计消耗（含子代理）：活跃会话主干取内存实时值，子代理取落盘聚合值，非活跃会话整体取落盘聚合值。异常时回退为 `window_token: 0`、`max_token: 1000000`、其余为 `0`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/agent/token?session_id=session_xxx'
```
