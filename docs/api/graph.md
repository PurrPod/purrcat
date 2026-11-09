# 图谱 `/api/graphs`

> 源码：`src/server/api/graph.py` ｜ 前缀：`/api/graphs` ｜ 端点：5 个

DAG 图谱（工作流）管理接口。每个 Graph 以 `{GRAPHS_DIR}/{name}/` 文件夹为单位，核心文件为 `graph.json`，另有 `asset/` 目录存放素材。

**约定**

- 路径参数 `{name}` 为 Graph 名称（即文件夹名），不含 `.json` 后缀。
- 节点类型清单可由 `GET /api/graphs/nodes` 返回（读取 `src/harness/node/extensions/*/*.json` 的节点定义）。
- Graph 中的 `global_schema` 驱动前端表单：`GET /api/graphs/{name}/schema` 单独暴露该字段，前端据此动态生成工作流全局输入参数填写表单。

---

## GET `/api/graphs/nodes`

获取所有可用的节点类型定义。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |

**响应**

```json
[
  {
    "type": "llm",
    "name": "LLM",
    "description": "调用大模型",
    "inputs": {},
    "outputs": {}
  }
]
```

返回一个数组，元素为节点定义 JSON（来自 `src/harness/node/extensions/*/*.json`，仅保留含 `type` 字段的定义）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/graphs/nodes'
```

---

## GET `/api/graphs`

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |

**响应**

```json
[
  {
    "name": "trading",
    "path": "/abs/path/graphs/trading/graph.json"
  }
]
```

返回数组，元素为 `{ name, path }`；仅包含目录下存在 `graph.json` 的 Graph。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/graphs'
```

---

## GET `/api/graphs/{name}`

读取某个 Graph 的完整定义。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 | Graph 名称（文件夹名） |

**响应**

```json
{
  "nodes": [],
  "edges": [],
  "global_schema": {}
}
```

返回 `graph.json` 解析后的对象。若 Graph 不存在或解析失败，返回 `404` 与 `{ "detail": "Graph not found" }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/graphs/trading'
```

---

## GET `/api/graphs/{name}/schema`

获取工作流的全局输入参数 Schema。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 | Graph 名称（文件夹名） |

**响应**

```json
{
  "graph_name": "trading",
  "global_schema": {
    "symbol": { "required": true, "description": "交易标的" }
  }
}
```

`global_schema` 取自 `graph.json` 的 `global_schema` 字段（缺失时为空对象 `{}`）。若 Graph 不存在，返回 `404` 与 `{ "detail": "Graph not found" }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/graphs/trading/schema'
```

---

## POST `/api/graphs/{name}`

保存（新建或覆盖）某个 Graph。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 | Graph 名称（文件夹名） |
| graph_data | body | object | 是 | Graph 完整定义的 JSON 对象（原样写入 `graph.json`） |

**响应**

```json
{
  "status": "ok",
  "name": "trading"
}
```

写出时会创建 `{name}/` 目录与 `{name}/asset/` 子目录，并以缩进 JSON 覆盖写入 `graph.json`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/graphs/trading' \
  -H 'Content-Type: application/json' \
  -d '{"nodes": [], "edges": [], "global_schema": {}}'
```
