# 进化工厂 `/api/evolve`

> 源码：`src/server/api/evolve.py` ｜ 前缀：`/api/evolve` ｜ 端点：14 个

进化工厂（Evolution Factory）管理接口。`type` 指定加工厂类型：`skill`（默认）、`mcp`、`sensor`、`agentloop`、`graph`。每个沙盒按 `workplace_id` 组织，位于 `AGENT_VM_DIR/{type}_workplace/{workplace_id}/` 下。

**约定**

- `type` 取值：`skill` | `mcp` | `sensor` | `agentloop` | `graph`（缺省 `"skill"`）。
- skill/mcp 的「本体」为 workplace 下同名子目录；sensor 的本体为 workplace 根目录下的单个 `<name>.py`；agentloop 的本体为 workplace 根目录下的单个 `<name>.yaml`；graph 的本体为 workplace 下的同名目录（含 `graph.json`）。
- `POST /api/evolve/test/run` 为后台异步接口，立即返回受理态，进度经 `/api/evolve/test/iterations`、`/api/evolve/test/report` 轮询。

---

## GET `/api/evolve/list`

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| type | query | string | 否 | 加工厂类型，默认 `skill` |

**响应**

```json
[
  { "workplace_id": "wp-001", "name": "my-skill", "status": "processing" }
]
```

返回沙盒数组；无有效本体（未知名称）的沙盒会被跳过。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/evolve/list?type=skill'
```

---

## POST `/api/evolve/init`

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| type | body | string | 否 | 加工厂类型，默认 `skill` |
| name | body | string | 是 | 模块名称 |
| is_upgrade | body | boolean | 是 | 是否为升级（`false` 为改进） |
| goal | body | string | 否 | 本次构建目标（写入 `GOAL.md` 并嵌入 `GUIDE.md`），默认空串 |
| trace | body | boolean | 否 | trace2skill 入口：为 `true` 时快照来源会话 Token 到沙盒 `trace_meta.json`，默认 `false` |
| session_id | body | string | 否 | 来源会话 ID，配合 `trace` 使用 |

**响应**

```json
{
  "status": "success",
  "workplace_id": "wp-001",
  "message": "初始化完成"
}
```

分配失败（无 `workplace_id`）返回 `400`；内部异常返回 `500`。

当 `trace=true` 且 `type=skill` 且有 `session_id` 时，会把该会话的累计 Token 快照写入 `skill_workplace/<workplace_id>/trace_meta.json`，随后盲测报告据此对比展示「该技能让后台盲测任务少花了多少 token」。快照失败不影响建厂。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/evolve/init' \
  -H 'Content-Type: application/json' \
  -d '{"type": "skill", "name": "my-skill", "is_upgrade": false, "goal": "补全文档", "trace": true, "session_id": "main"}'
```

---

## GET `/api/evolve/file`

读取沙盒内文件；不传 `filename` 时返回文件树。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| name | query | string | 是 | 模块名称 |
| type | query | string | 否 | 加工厂类型，默认 `skill` |
| filename | query | string | 否 | 相对文件名；为空则返回文件列表，默认空串 |

**响应**

```json
{ "content": "", "attachments": ["SKILL.md", "main.py"] }
```

`filename` 为空时返回 `attachments`（排除 `__pycache__` / `.venv` / `node_modules` / `iteration-*` / `trigger-*` 目录及 `.pyc` / `.png` / `.jpg` 文件，已排序）；否则返回 `{ "content": "<文件文本>" }`。工作区或文件不存在返回 `404`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/evolve/file?workplace_id=wp-001&name=my-skill'
curl 'http://127.0.0.1:8000/api/evolve/file?workplace_id=wp-001&name=my-skill&filename=SKILL.md'
```

---

## PUT `/api/evolve/file`

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| name | query | string | 是 | 模块名称 |
| filename | query | string | 是 | 相对文件名 |
| type | query | string | 否 | 加工厂类型，默认 `skill` |
| content | body | string | 是 | 要写入的文件内容 |

**响应**

```json
{ "status": "success", "message": "保存成功" }
```

写入前会自动创建父目录；异常返回 `500`。

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/evolve/file?workplace_id=wp-001&name=my-skill&filename=SKILL.md' \
  -H 'Content-Type: application/json' \
  -d '{"content": "# My Skill"}'
```

---

## GET `/api/evolve/paradigm`

读取沙盒内 AgentLoop 范式（`<name>.yaml`）并解析为结构化对象，供前端范式编辑器加载。

> 仅用于 `agentloop` 工厂：沙盒路径固定为 `agentloop_workplace/{workplace_id}/<name>.yaml`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| name | query | string | 是 | 范式名称（对应沙盒内 `<name>.yaml`）|

**响应**

```json
{ "name": "my-paradigm", "data": { "name": "my-paradigm", "hooks": {} } }
```

`data` 为解析后的范式对象（顶层非映射时归一化为 `{}`）。文件不存在返回 `404`，YAML 解析失败返回 `400`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/evolve/paradigm?workplace_id=wp-001&name=my-paradigm'
```

---

## POST `/api/evolve/paradigm`

把结构化范式对象序列化回沙盒内 `<name>.yaml`（前端编辑器的「保存到沙盒」）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| name | query | string | 是 | 范式名称（写回 `<name>.yaml`）|
| data | body | object | 是 | 完整范式对象；序列化时保留原始键序、不转 flow 风格 |

**响应**

```json
{ "status": "success", "message": "保存成功" }
```

写入前会自动创建父目录；非映射的 `data` 会被写成空映射。YAML 序列化失败返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/evolve/paradigm?workplace_id=wp-001&name=my-paradigm' \
  -H 'Content-Type: application/json' \
  -d '{"data": {"name": "my-paradigm", "path": "agent_vm", "hooks": {}}}'
```

---

## POST `/api/evolve/test/run`

启动盲测 / 评测（后台异步）。

每次调用都会**新开一代**（`iteration-N`）。`skill` 类型会把 Trigger 激发测试与盲测一并跑进这一代，不复用最近一代；`mcp` / `sensor` 本就按新代归档。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| type | body | string | 否 | 加工厂类型，默认 `skill` |
| workplace_id | body | string | 是 | 沙盒工作区 ID |
| name | body | string | 是 | 模块名称 |
| session_id | body | string | 否 | 会话 ID，默认 `main` |

**响应**

```json
{ "status": "success", "message": "盲测已启动" }
```

启动异常返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/evolve/test/run' \
  -H 'Content-Type: application/json' \
  -d '{"type": "skill", "workplace_id": "wp-001", "name": "my-skill", "session_id": "main"}'
```

---

## GET `/api/evolve/test/iterations`

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| type | query | string | 否 | 加工厂类型，默认 `skill` |

**响应**

```json
[1, 2, 3]
```

扫描 `iteration-<n>` 目录并返回升序轮次编号数组。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/evolve/test/iterations?workplace_id=wp-001&type=skill'
```

---

## GET `/api/evolve/test/report`

读取某轮评测的 HTML 报告页。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| name | query | string | 是 | 模块名称 |
| type | query | string | 否 | 加工厂类型，默认 `skill` |
| iteration | query | integer | 否 | 轮次；缺省取最新轮次 |

**响应**

```json
{ "report_html": "<!DOCTYPE html>\n<html lang=\"zh-CN\">...</html>" }
```

报告统一以自包含的瑞士国际主义风格 HTML 页面输出，各类型同取该轮次目录下的 `report.html`（`skill` 为 Trigger + 盲测合并的单一页面）。页面零外部依赖，前端以 iframe 直接承载，故接口不再返回文件清单或 Markdown。无报告时返回 `{ "report_html": "" }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/evolve/test/report?workplace_id=wp-001&name=my-skill&type=skill'
```

---

## GET `/api/evolve/test/benchmark`

读取某轮体检的结构化结论（`benchmark.json`），供前端展示逐条判据与未覆盖项。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| type | query | string | 否 | 加工厂类型，默认 `sensor` |
| iteration | query | integer | 否 | 轮次；缺省取最新轮次 |

**响应**

```json
{ "benchmark": { "criteria": [], "coverage": {} } }
```

读取 `iteration-<n>/benchmark.json`；轮次不存在、文件缺失或解析失败均返回 `{ "benchmark": null }`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/evolve/test/benchmark?workplace_id=wp-001&type=sensor'
```

---

## GET `/api/evolve/diff`

生成沙盒与正式库的差异（Diff）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 | 沙盒工作区 ID |
| name | query | string | 是 | 模块名称 |
| type | query | string | 否 | 加工厂类型，默认 `skill` |

**响应**

```json
{ "diff_content": "diff --git ..." }
```

对比正式库与沙盒：`skill` 对比 `SKILL_DIR/{name}`，`mcp` 对比 `./mcps/{name}`，`sensor` 对比 `{name}.py`，`agentloop` 对比 `PARADIGMS_DIR/{name}.yaml`，`graph` 对比 `GRAPHS_DIR/{name}`。全新模块返回文字说明，无变化返回提示语。异常返回 `500`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/evolve/diff?workplace_id=wp-001&name=my-skill&type=skill'
```

---

## POST `/api/evolve/handle`

处理进化合并请求（人工审批）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| type | body | string | 否 | 加工厂类型，默认 `skill` |
| workplace_id | body | string | 是 | 沙盒工作区 ID |
| name | body | string | 是 | 模块名称 |
| is_approved | body | boolean | 是 | 是否批准 |
| reject_reason | body | string | 否 | 拒绝原因，默认空串 |

**响应**

```json
{ "status": "success", "message": "合并完成" }
```

拒绝时（`is_approved = false`）将拒绝意见写入 `REJECT_REASON.md` 并返回：

```json
{ "status": "rejected", "message": "已将拒绝意见抛回沙盒，Agent可读取并继续调整。" }
```

异常返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/evolve/handle' \
  -H 'Content-Type: application/json' \
  -d '{"type": "skill", "workplace_id": "wp-001", "name": "my-skill", "is_approved": true}'
```

---

## POST `/api/evolve/rollback`

回滚指定模块至上一个 Git 版本。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| type | body | string | 否 | 加工厂类型，默认 `skill` |
| name | body | string | 是 | 模块名称 |

**响应**

```json
{ "status": "success", "message": "回滚成功！'my-skill' 已恢复至上一个版本，并生成了 Rollback Commit。" }
```

回滚失败或无 Git 历史时返回 `400`；异常返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/evolve/rollback' \
  -H 'Content-Type: application/json' \
  -d '{"type": "skill", "name": "my-skill"}'
```

---

## DELETE `/api/evolve/workplace/{workplace_id}`

前端手动彻底删除工厂沙盒。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | path | string | 是 | 沙盒工作区 ID |
| type | query | string | 否 | 加工厂类型，默认 `skill` |

**响应**

```json
{ "status": "success", "message": "沙盒已彻底清理" }
```

递归删除 workplace 目录（只读文件会先改权限）。沙盒不存在返回 `404`；异常返回 `500`。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/evolve/workplace/wp-001?type=skill'
```
