# 任务 `/api/tasks`

> 源码：`src/server/api/task.py` ｜ 前缀：`/api/tasks` ｜ 端点：10 个

任务的创建、状态查询、指令注入、节点重置与产物读取。状态与记忆同时覆盖内存中的活跃任务与磁盘上的休眠任务。

---

## GET `/api/tasks`

获取任务列表：合并磁盘上的历史（休眠）任务与内存中的活跃任务，按创建时间降序返回。

程序启动时不加载任务实例，列表只读取任务目录摘要（`meta.json` + `state.json`，旧格式为 `checkpoint.json`），并按目录结构缓存；任务图谱、会话与日志在真正查看或操作时再按需读取。

进程重启后不可能还有任务在运行：磁盘上残留的 `running` / `starting` 统一按中断处理，列表与详情展示为 `interrupted`，残留的 `running` 节点回落到 `ready`。启动后台对账会同步修正新格式 `state.json` 中的错误状态；旧格式 `checkpoint.json` 体积较大，只在读取时归一化。

**请求**

无请求参数。

**响应**

```json
[
  {
    "id": "tsk_ab12cd34",
    "name": "示例任务",
    "graph_name": "default",
    "state": "running",
    "step": 3,
    "expert_type": "Task",
    "create_time": "2026-10-14 10:00:00",
    "token_usage": 1234,
    "checkpoint_dir": "data/checkpoints/task/demo_tsk_ab12cd34"
  }
]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tasks'
```

---

## POST `/api/tasks/run`

创建并启动新任务：接收工作流（Graph）名称与初始输入参数，抛入后台异步执行后立即返回受理信息。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_name | body | string | 是 | 任务名称 |
| graph_name | body | string | 是 | 工作流（Graph）名称 |
| inputs | body | object | 否 | 初始输入参数，默认 `{}` |

**响应**

```json
{
  "status": "success",
  "task_id": "tsk_ab12cd34",
  "message": "Task started in background."
}
```

任务初始化失败时返回 400（`detail` 为初始化错误信息），其它异常返回 500。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tasks/run' \
  -H 'Content-Type: application/json' \
  -d '{"task_name": "示例任务", "graph_name": "default", "inputs": {}}'
```

---

## GET `/api/tasks/{task_id}/state`

获取统一状态，并拼装前端气泡所需的 memory（活跃任务读内存、休眠任务扫磁盘 checkpoint）。响应头带 `Cache-Control: no-store`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |

**响应**

```json
{
  "task_id": "tsk_ab12cd34",
  "state": "running",
  "graph": "default",
  "node_states": { "node_1": "running" },
  "outputs": {},
  "node_memory": { "node_1": { "messages": [] } },
  "node_approvals": { "review_1": "2026-11-16 10:00:00" }
}
```

`node_states`、`outputs` 与 `node_memory` 的具体结构由任务运行时数据决定，此处为示意。`node_approvals` 为人工审核节点的批准记录（按 checkpoint 落盘，刷新后仍可回显）；任务不存在返回 404。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/state'
```

---

## POST `/api/tasks/{task_id}/submit`

注入人工指令。任务须处于活跃状态，否则先按需从磁盘 checkpoint 加载回内存（找不到返回 404）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |
| node_id | body | string | 是 | 目标节点 ID（仅 Agent 类型节点可注入） |
| content | body | string | 是 | 注入的指令内容 |

**响应**

```json
{ "status": "success", "message": "指令已注入，下游链路状态已重置！" }
```

注入失败（如节点不存在或非 Agent 节点）返回 400。任务原本未运行时，返回后会自动重启后台引擎。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/submit' \
  -H 'Content-Type: application/json' \
  -d '{"node_id": "node_1", "content": "请补充说明"}'
```

---

## POST `/api/tasks/{task_id}/push`

精确注入：只向指定 Agent 节点注入消息。任务必须已在内存中活跃，否则返回 404。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |
| message | body | string | 是 | 注入的消息内容 |
| node_id | body | string | 是 | 目标节点 ID；为空时返回 400（已废弃全局广播注入） |

**响应**

```json
{ "status": "success", "message": "指令已精确注入" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/push' \
  -H 'Content-Type: application/json' \
  -d '{"node_id": "node_1", "message": "继续下一步"}'
```

---

## GET `/api/tasks/{task_id}/log`

统一日志读取：直接读纯文本盘，按节点分组，不唤醒休眠引擎。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |

**响应**

```json
{
  "task_id": "tsk_ab12cd34",
  "grouped_logs": {
    "node_1": [ { "node_id": "node_1", "level": "INFO", "message": "..." } ],
    "system": [ { "node_id": "system", "level": "ERROR", "message": "..." } ]
  }
}
```

无日志时 `grouped_logs` 为空对象 `{}`。日志条目结构由任务日志格式决定，此处为示意。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/log'
```

---

## GET `/api/tasks/{task_id}/artifact`

按 `purrcat://` URI（或绝对路径兜底）返回任务产物文件，供前端 preview 渲染。URI 非法或文件不存在返回 404。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |
| uri | query | string | 是 | 产物 `purrcat://` URI（解析失败时按绝对路径兜底） |
| mime | query | string | 否 | 返回文件的 MIME 类型 |

**响应**

返回文件字节流（`FileResponse`），响应头带 `Content-Security-Policy: sandbox allow-scripts`（HTML 类产物强制沙箱）与 `Cache-Control: no-store`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/artifact?uri=purrcat://output/result.html&mime=text/html'
```

---

## DELETE `/api/tasks/{task_id}`

物理删除任务，同时支持清理休眠与活跃任务。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |

**响应**

```json
{ "status": "ok", "message": "Task destroyed." }
```

任务不存在或删除失败返回 404。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34'
```

---

## POST `/api/tasks/{task_id}/nodes/{node_id}/approve`

批准人工审核节点：向该节点注入放行指令，并把批准记录写入 checkpoint 的 `nodes/{node_id}/approval.json`，刷新任务页后仍显示为已批准。仅 `human_intervention` 类型且处于 `waiting` 的节点可批准。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |
| node_id | path | string | 是 | 人工审核节点 ID |

**响应**

```json
{ "status": "success", "approved": true }
```

已批准过则返回 `{"status": "success", "approved": true, "already_approved": true}`。节点类型不符或不在等待审核时返回 400，任务不存在返回 404。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/nodes/review_1/approve'
```

---

## POST `/api/tasks/{task_id}/nodes/{node_id}/reset`

重置节点：触发级联清理并重启引擎。任务可能已结束或程序重启后不在内存，先按需从 checkpoint 激活。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |
| node_id | path | string | 是 | 要重置的节点 ID |

**响应**

```json
{ "status": "success", "message": "节点及其下游已彻底重置！" }
```

节点不存在等错误返回 400，任务无法激活返回 404。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/nodes/node_1/reset'
```

---

## POST `/api/tasks/{task_id}/stop`

优雅终止运行中的任务：与 DELETE 不同，只杀死进程、保留 checkpoint 供后续查看。终止立即落盘为 `killed`，并取消正在执行的节点协程，把这些节点标记为 `killed`（再次注入或重置后回到 `ready` 可继续跑）。只要还有 `killed` 节点未重新执行，任务恢复运行时保持 `interrupted`，不会被误判为 `completed`。已处于终态（完成/出错/已中止）的任务返回 404。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 | 任务 ID |

**响应**

```json
{ "status": "success", "message": "Task killed gracefully." }
```

任务不在活跃状态或不存在返回 404。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tasks/tsk_ab12cd34/stop'
```
