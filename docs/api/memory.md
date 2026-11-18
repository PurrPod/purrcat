# 记忆 `/api/memory`

> 源码：`src/server/api/memory.py` ｜ 前缀：`/api/memory` ｜ 端点：9 个

记忆系统接口：事件（SQLite + FTS5）、工作经验（SQLite 事实源 + Chroma 向量索引）、记忆图谱（GraphEngine）的读取与删除，以及 `MEMORY.md` 的读写。

---

## GET `/api/memory/events`

获取最近事件列表（SQLite + FTS5），固定取最近 30 条；读取异常时返回空数组。

**请求**

无请求参数。

**响应**

```json
[
  { "id": "evt_a1b2c3", "content": "示例事件内容", "timestamp": "2026-10-14T10:00:00" }
]
```

事件字段结构由事件引擎决定，此处为示意；无数据时为 `[]`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/events'
```

---

## GET `/api/memory/experiences`

获取最近工作经验列表（SQLite 事实源），固定取最近 30 条；`confidence` 为按衰减锚点惰性计算出的有效置信度；读取异常时返回空数组。

**请求**

无请求参数。

**响应**

```json
[
  {
    "exp_id": "exp_x9y8z7",
    "content": "……",
    "confidence": 0.6,
    "timestamp": "2026-10-14T10:00:00"
  }
]
```

无数据时为 `[]`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/experiences'
```

---

## GET `/api/memory/graph`

获取记忆图谱，返回节点与边；读取异常时返回 `{"nodes": [], "edges": []}`。

**请求**

无请求参数。

**响应**

```json
{
  "nodes": [ { "id": "n1", "label": "示例节点" } ],
  "edges": [ { "source": "n1", "target": "n2" } ]
}
```

节点/边字段结构由图谱引擎决定，此处为示意。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/graph'
```

---

## GET `/api/memory/search`

按关键词搜索记忆。`q` 为空时直接返回空结果；搜索异常时以文本形式返回失败原因。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| q | query | string | 否 | 搜索关键词；为空时返回 `{"result": ""}` |

**响应**

```json
{ "result": "命中的记忆文本……" }
```

搜索失败时 `result` 为 `搜索失败: <原因>`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/search?q=项目配置'
```

---

## DELETE `/api/memory/experiences/{exp_id}`

删除一条工作经验：SQLite 硬删除并写入可恢复快照，同时登记向量删除，由索引器异步清理 Chroma。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| exp_id | path | string | 是 | 工作经验 ID |

**响应**

```json
{ "status": "success", "message": "经验已删除" }
```

经验不存在返回 404，其它异常返回 500。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/memory/experiences/exp_x9y8z7'
```

---

## DELETE `/api/memory/events/{event_id}`

删除一条事件（SQLite + FTS5）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| event_id | path | string | 是 | 事件 ID |

**响应**

```json
{ "status": "success", "message": "事件已删除" }
```

事件不存在返回 404，其它异常返回 500。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/memory/events/evt_a1b2c3'
```

---

## DELETE `/api/memory/graph/relation`

物理删除图谱关系边（由源节点与目标节点标识）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| source_node_id | query | string | 是 | 源节点 ID |
| target_node_id | query | string | 是 | 目标节点 ID |

**响应**

```json
{ "status": "success", "message": "关系边已删除" }
```

未找到该关系边返回 404，其它异常返回 500。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/memory/graph/relation?source_node_id=n1&target_node_id=n2'
```

---

## GET / PUT `/api/memory/markdown`

读取或覆盖写入 `.purrcat/core/MEMORY.md` 文件内容（基于 `AGENT_CORE_DIR`）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| content | body | string | 否 | PUT 时的写入内容，默认空字符串 |

GET 无参数；PUT 请求体为 `{ "content": "<Markdown 文本>" }`。

**响应**

GET 返回文件内容：

```json
{ "content": "# 记忆\n……" }
```

文件不存在时 `content` 为空字符串。PUT 返回保存结果：

```json
{ "status": "success", "message": "MEMORY.md 已成功落盘保存" }
```

读写失败均返回 500（`detail` 携带具体原因）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/markdown'

curl -X PUT 'http://127.0.0.1:8000/api/memory/markdown' \
  -H 'Content-Type: application/json' \
  -d '{"content": "# 记忆\n新的内容"}'
```
