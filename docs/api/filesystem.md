# 文件系统

> 源码：`src/server/api/filesystem.py` ｜ 前缀：`/api/filesystem` ｜ 端点：12 个

面向 IDE Panel / 前端 UI 的文件直连操作（浏览器端降级用）。路径以 `/agent_vm` 沙盒路径为主，服务端会通过 `convert_sandbox_path` 自动映射为宿主真实绝对路径，并含沙盒层缺失时的回退查找。
文件改动以备份快照（`backup_id`）+ 未确认变更（diff）为核心：`undo` 回滚、`ack`/`ack_all` 确认清理备份。

---

## GET `/api/filesystem/list`

列出目录内容，跳过以 `.` 开头的隐藏项。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 目标目录路径（可为沙盒路径） |

**响应**

```json
[
  { "name": "src", "isDir": true, "path": "/agent_vm/src" },
  { "name": "main.py", "isDir": false, "path": "/agent_vm/main.py" }
]
```

按“目录优先、名称不区分大小写”排序。异常时返回 `400`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/list?path=/agent_vm'
```

---

## GET `/api/filesystem/read`

读取文件文本内容（`/agent_vm` 沙盒路径自动转换，含 agent_vm 层缺失回退）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 目标文件路径 |

**响应**

```json
{ "content": "文件文本内容" }
```

异常时返回 `400`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/read?path=/agent_vm/README.md'
```

---

## GET `/api/filesystem/stat`

返回文件元信息（大小）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 目标文件路径 |

**响应**

```json
{ "size": 2048 }
```

异常时返回 `400`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/stat?path=/agent_vm/main.py'
```

---

## POST `/api/filesystem/write`

写入文件文本内容（自动创建父目录，`/agent_vm` 沙盒路径自动转换）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | body | string | 是 | 目标文件路径 |
| `content` | body | string | 是 | 要写入的文本内容 |

**响应**

```json
{ "status": "success" }
```

异常时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/filesystem/write' -H 'Content-Type: application/json' -d '{"path":"/agent_vm/notes.txt","content":"hello"}'
```

---

## GET `/api/filesystem/history_list`

直接读取 `.agent_history` 目录，返回真实存在的备份文件列表（跳过 `.empty` 占位文件）。

**响应**

```json
[
  {
    "id": "safe_path@backup_id",
    "path": "/sandbox/path",
    "backup_id": "backup_id",
    "time": ""
  }
]
```

`id` 为完整文件名（`safe_path@backup_id`），`path` 由安全路径还原为 `/` 前缀的沙盒路径；`time` 当前为空串，需前端自行转换。目录不存在时返回空数组。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/history_list'
```

---

## GET `/api/filesystem/backups`

校验哪些快照仍在硬盘上存活。

**响应**

```json
{ "status": "success", "valid_ids": ["backup_id_1", "backup_id_2"] }
```

读取异常时返回 `{ "status": "error", "valid_ids": [] }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/backups'
```

---

## POST `/api/filesystem/undo`

一键回滚（最高权限）：按 `backup_id` 将文件还原到指定快照。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | body | string | 是 | 目标文件路径 |
| `backup_id` | body | string | 是 | 要回滚到的备份快照 id |

**响应**

```json
{ "status": "success", "message": "<回滚结果描述>" }
```

`message` 为回滚操作的文字结果。失败时返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/filesystem/undo' -H 'Content-Type: application/json' -d '{"path":"/agent_vm/notes.txt","backup_id":"backup_id_1"}'
```

---

## POST `/api/filesystem/ack`

用户确认更改：删除该文件在磁盘上的备份，解决空间膨胀。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | body | string | 是 | 目标文件路径 |
| `backup_id` | body | string | 是 | 要确认的备份快照 id |

**响应**

```json
{ "status": "success" }
```

若当前沙盒解析不到任何备份（文件可能已被外部迁移或销毁），会直接清掉该改动记录并返回：

```json
{ "status": "success", "purged_stale": true }
```

失败时返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/filesystem/ack' -H 'Content-Type: application/json' -d '{"path":"/agent_vm/notes.txt","backup_id":"backup_id_1"}'
```

---

## POST `/api/filesystem/ack_all`

一键接受全部更改：对所有未确认变更执行 ack，清理全部备份（无请求体）。

**响应**

```json
{ "status": "success", "total": 3, "purged_stale": 0 }
```

`total` 为处理的变更总数，`purged_stale` 为其中被直接清掉记录的陈旧变更数。若存在处理失败项则返回：

```json
{ "status": "partial", "failed": 1, "total": 3 }
```

失败时返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/filesystem/ack_all'
```

---

## GET `/api/filesystem/diffs`

全局读取所有未确认的代码变更（DiffView）。

**响应**

```json
{ "status": "success", "diffs": [] }
```

异常时返回 `{ "status": "error", "diffs": [], "message": "<错误详情>" }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/diffs'
```

---

## GET `/api/filesystem/resolve`

返回沙盒/相对路径对应的宿主机真实绝对路径，供前端构造 `file://` URL 在内置浏览器中打开本地文件。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 沙盒/相对路径 |

**响应**

```json
{ "real_path": "D:\\cat-in-cup\\agent_vm\\index.html" }
```

目标不是文件时返回 `404`；其它异常返回 `400`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/resolve?path=/agent_vm/index.html'
```

---

## GET `/api/filesystem/preview`

接收路径并返回文件流供前端预览，绕过浏览器对 `file://` 协议的同源与安全限制。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `path` | query | string | 是 | 文件路径（绝对路径或沙盒路径） |

**响应**

返回 `FileResponse` 文件流，`Content-Type` 由 `mimetypes` 依据文件名推断（无法推断时为 `application/octet-stream`）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/filesystem/preview?path=/agent_vm/index.html' -o preview.html
```
