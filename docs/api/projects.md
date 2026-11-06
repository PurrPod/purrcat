# 项目（会话分类器）

> 源码：`src/server/api/projects.py`、`src/agent/project_store.py` ｜ 前缀：`/api` ｜ 端点：4 个

项目是会话的归类容器：命名后把若干会话收进同一个「文件夹」，便于在极简 UI 侧栏按项目分组浏览。
每个项目带一份 `MEMORY.md` 项目记忆文件（新建项目时自动生成，内容只写明它自己的位置）。**只有在该项目内新建会话时**，才会把这份记忆文件的路径与维护约定追加进系统提示，由 Agent 在任务结束后按需手动编辑；把已有会话拖进项目不会改动其系统提示。

存储位置（`data_root` 默认 `~/.purrcat`）：

```
projects/index.json                 项目索引（id / name / created_at / updated_at）
projects/<project_id>/MEMORY.md     项目记忆文件（由 Agent 按需维护）
```

旧项目若只有 `PROJECT.md`，读取时会自动改名为 `MEMORY.md`。

会话归属写在会话自身 `meta.json` 与全局会话索引的 `project_id` 字段；缺省表示「未分类」。

---

## GET `/api/projects`

返回全部项目（按创建时间升序），附带会话数量与记忆文件路径。

**响应**

```json
[
  {
    "id": "project_xxx",
    "name": "网站改版",
    "created_at": "2026-11-06 10:00:00",
    "updated_at": "2026-11-06 10:05:00",
    "session_count": 3,
    "memory_path": "/home/me/.purrcat/projects/project_xxx/MEMORY.md"
  }
]
```

`memory_path` 为该项目的 `MEMORY.md` 绝对路径（前端只展示位置，不读取正文）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/projects'
```

---

## POST `/api/projects`

新建项目：创建项目文件夹与 `MEMORY.md`（写入自身路径，无需用户编辑），写入索引。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | 项目名称（去空白后不能为空） |

**响应**

```json
{
  "id": "project_xxx",
  "name": "网站改版",
  "created_at": "2026-11-06 10:00:00",
  "updated_at": "2026-11-06 10:00:00",
  "session_count": 0
}
```

名称为空时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/projects' -H 'Content-Type: application/json' -d '{"name":"网站改版"}'
```

---

## PUT `/api/projects/{project_id}`

更新项目名称。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `project_id` | path | string | 是 | 项目 id |
| `name` | body | string | 否 | 新项目名称（不能为空） |

**响应**

```json
{
  "id": "project_xxx",
  "name": "网站改版",
  "created_at": "2026-11-06 10:00:00",
  "updated_at": "2026-11-06 10:06:00",
  "session_count": 3,
  "memory_path": "/home/me/.purrcat/projects/project_xxx/MEMORY.md"
}
```

项目不存在返回 `404`；名称为空返回 `400`。

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/projects/project_xxx' -H 'Content-Type: application/json' -d '{"name":"网站改版"}'
```

---

## DELETE `/api/projects/{project_id}`

删除项目。删除时由调用方选择如何处理项目内会话：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `project_id` | path | string | 是 | 项目 id |
| `delete_sessions` | query | boolean | 否 | 默认 `false` |

- `delete_sessions=false`：会话保留，仅解除归属（回到「未分类」），`deleted_sessions` 为 `0`。
- `delete_sessions=true`：连同项目内全部会话一起删除。若其中包含 Agent 当前活跃会话，返回 `400`，需先切换到其它会话；个别会话删除失败时返回 `500` 且项目保留（可重试）。

**响应**

```json
{ "status": "ok", "deleted_sessions": 3 }
```

项目不存在返回 `404`。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/projects/project_xxx'
curl -X DELETE 'http://127.0.0.1:8000/api/projects/project_xxx?delete_sessions=true'
```
