# 工具 `/api/tools`

> 源码：`src/server/api/tools.py` ｜ 前缀：`/api/tools` ｜ 端点：31 个

覆盖 Skill、MCP、Cron、心跳（HEARTBEAT）以及市场（sensors / graphs / ui-plugins / agentloops）等接口。市场类接口统一遵循 `registry`（拉取官方注册表）、`installed`（本地已安装列表）、`install`（安装）、`uninstall`（卸载）四类命名。

---

## GET `/api/tools/skills`

获取内存里已加载的 Skill 名称与描述。

**请求**

无参数。

**响应**

```json
[
  { "name": "示例技能", "description": "技能描述", "dir_name": "example-skill" }
]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/skills'
```

---

## POST `/api/tools/skills/install`

根据 GitHub URL 下载第三方 Skill 到本地并热更新内存索引。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `url` | body | string | 是 | Skill 所在 GitHub `tree` / `blob` 地址，如 `https://github.com/owner/repo/tree/main/path/to/skill`；目标目录内必须包含 `SKILL.md`，否则报错。链接若直接指向 `SKILL.md` 等文件，则自动取其所在文件夹 |

**响应**

```json
{ "status": "success", "message": "Skill 'xxx' 下载成功并已热加载入内存！" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/skills/install' -H 'Content-Type: application/json' -d '{"url":"https://github.com/owner/repo/tree/main/path/to/skill"}'
```

---

## POST `/api/tools/skills/install-batch`

批量下载多个第三方 Skill 并一次性热更新内存（同一仓库的 zip 只下载一次）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `urls` | body | array&lt;string&gt; | 是 | 多个 Skill 的 GitHub `tree` / `blob` 地址（规则同 `/skills/install`，每个目录需含 `SKILL.md`） |

**响应**

```json
{
  "status": "success",
  "installed": ["skill-a", "skill-b"],
  "failed": [{ "path": "path/to/skill", "error": "仓库下载失败: ..." }],
  "message": "批量安装完成：成功 2 个，失败 1 个"
}
```

`status` 在有失败项时为 `partial`，全部成功时为 `success`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/skills/install-batch' -H 'Content-Type: application/json' -d '{"urls":["https://github.com/owner/repo/tree/main/skills/a","https://github.com/owner/repo/tree/main/skills/b"]}'
```

---

## POST `/api/tools/skills/uninstall`

删除本地已安装的 Skill（按目录名或 `SKILL.md` 的 `name` 匹配），并热更新内存。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | Skill 目录名或 `SKILL.md` 中声明的名称 |

**响应**

```json
{ "status": "success", "message": "Skill 'xxx' 已删除" }
```

未找到该 Skill 时返回 `404`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/skills/uninstall' -H 'Content-Type: application/json' -d '{"name":"example-skill"}'
```

---

## POST `/api/tools/skills/refresh`

手动扫描本地 Skill 文件夹并更新内存检索树（并后台重建向量矩阵）。刷新进行中时直接返回受理态。

**请求**

无参数。

**响应**

```json
{ "status": "success", "message": "Skill 已刷新，共加载 12 个技能" }
```

刷新进行中时：

```json
{ "status": "refreshing", "message": "Skill 正在刷新中，请稍候…" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/skills/refresh'
```

---

## GET `/api/tools/mcp`

获取内存/缓存里的 MCP 服务器及其包含的工具名称和描述。

**请求**

无参数。

**响应**

以服务器名为键、工具数组为值：

```json
{
  "server_name": [
    { "name": "tool_name", "description": "工具描述" }
  ]
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/mcp'
```

---

## GET `/api/tools/mcp/list`

返回 `mcp_config.json` 中已配置的 MCP Server 名称列表（供市场“已安装”检测用）。

**请求**

无参数。

**响应**

```json
["server-a", "server-b"]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/mcp/list'
```

---

## POST `/api/tools/mcp/install`

解析并合并用户传入的 MCP Server JSON 配置，落盘到 `mcp_config.json` 后刷新 Schema 并热更新检索树；官方仓库（`PurrPod/mcps`）会额外下载源码。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `config_json` | body | string | 是 | 合法的 JSON 字符串，顶层键必须为 `mcpServers` |
| `repo` | body | string | 否 | 源码仓库地址；为官方仓库 `PurrPod/mcps` 时额外下载对应源码 |

**响应**

```json
{ "status": "success", "message": "MCP 配置已合并并热加载成功！当前系统共载入 30 个工具。" }
```

JSON 非法或缺少 `mcpServers` 顶层键时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/mcp/install' -H 'Content-Type: application/json' -d '{"config_json":"{\"mcpServers\":{\"demo\":{\"command\":\"npx\",\"args\":[\"-y\",\"demo-mcp\"]}}}","repo":""}'
```

---

## POST `/api/tools/mcp/uninstall`

从 `mcp_config.json` 移除该 Server，清理本地源码目录并热更新 Schema。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | 要移除的 MCP Server 名称 |

**响应**

```json
{ "status": "success", "message": "MCP Server 'demo' 已删除" }
```

未配置该 Server 时返回 `404`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/mcp/uninstall' -H 'Content-Type: application/json' -d '{"name":"demo"}'
```

---

## POST `/api/tools/mcp/refresh`

手动刷新 MCP Schema 并更新内存检索树（并后台重建向量矩阵）。刷新进行中时直接返回受理态。

**请求**

无参数。

**响应**

```json
{ "status": "success", "message": "MCP 缓存已刷新，共加载 30 个工具" }
```

刷新进行中时：

```json
{ "status": "refreshing", "message": "MCP 正在刷新中，请稍候…" }
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/mcp/refresh'
```

---

## GET `/api/tools/cron`

读取 `cron.json` 返回现有闹钟列表。

**请求**

无参数。

**响应**

返回闹钟列表（结构由 `list_crons()` 决定），形如：

```json
[
  { "id": "xxxx", "title": "喝水提醒", "trigger_time": "2026-10-14 09:00", "repeat_rule": "none", "task_hook": "Agent" }
]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/cron'
```

---

## POST `/api/tools/cron`

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `title` | body | string | 是 | 闹钟标题 |
| `trigger_time` | body | string | 是 | 触发时间 |
| `repeat_rule` | body | string | 否 | 重复规则，默认 `none` |
| `task_hook` | body | string | 否 | 到点触发的任务钩子，默认 `Agent` |
| `task_inputs` | body | object | 否 | 传给任务钩子的参数，默认 `{}` |

**响应**

```json
{ "status": "success", "data": { "id": "xxxx" } }
```

添加失败时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/cron' -H 'Content-Type: application/json' -d '{"title":"喝水提醒","trigger_time":"2026-10-14 09:00","repeat_rule":"none","task_hook":"Agent","task_inputs":{}}'
```

---

## DELETE `/api/tools/cron/{identifier}`

删除闹钟，`identifier` 支持传 id 或 title。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `identifier` | path | string | 是 | 闹钟的 id 或 title |

**响应**

```json
{ "status": "success", "data": { "id": "xxxx" } }
```

删除失败时返回 `400`。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/tools/cron/喝水提醒'
```

---

## GET / POST `/api/tools/heartbeat`

GET：获取心跳配置与 `GOAL.md` 当前内容；POST：保存心跳配置（开启心跳时必须提交非空 `GOAL.md`）。

**请求**

GET 无参数。POST：

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `interval` | body | integer | 是 | 心跳间隔（秒），最短 `60`，实际落盘取 `max(60, interval)` |
| `active` | body | boolean | 是 | 是否开启心跳 |
| `goal` | body | string | 否 | `GOAL.md` 内容；`active=true` 时必须非空 |

**响应**

GET：

```json
{ "interval": 300, "active": true, "goal": "# 目标\n..." }
```

POST：

```json
{ "status": "success", "data": { "interval": 300, "active": true } }
```

`active=true` 且 `goal` 为空时返回 `400`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/heartbeat'
curl -X POST 'http://127.0.0.1:8000/api/tools/heartbeat' -H 'Content-Type: application/json' -d '{"interval":300,"active":true,"goal":"# 目标\n持续优化项目"}'
```

---

## GET `/api/tools/market/sensors`

从官方 `PurrPod/sensors` 仓库拉取 `registry.json` 返回给前端市场。

**请求**

无参数。

**响应**

```json
{ "version": "1.0.0", "repository": "PurrPod/sensors", "sensors": [{ "name": "feishu-bot", "description": "..." }] }
```

拉取失败时返回 `502`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/sensors'
```

---

## GET `/api/tools/market/sensors/installed`

返回 `activate_sensor.json` 中已配置（不论是否 `enabled`）的传感器列表。

**请求**

无参数。

**响应**

```json
[
  { "name": "feishu-bot", "enabled": true, "has_code": true }
]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/sensors/installed'
```

---

## POST `/api/tools/market/sensors/install`

安装 Sensor（支持覆盖式重新下载）：合并配置写入 `activate_sensor.json`（按 name 覆盖，保留用户已填 env），并下载对应代码文件到本地。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `sensor` | body | object | 是 | registry 中的单条 sensor 对象，必须含 `name` 字段 |

**响应**

成功：

```json
{ "status": "success", "message": "Sensor 'feishu-bot' 配置已合并，代码已下载到 ...。", "code_downloaded": true }
```

配置写入成功但代码下载失败时返回 `partial`，`code_downloaded` 为 `false`。缺少 `name` 时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/sensors/install' -H 'Content-Type: application/json' -d '{"sensor":{"name":"feishu-bot","description":"..."}}'
```

---

## POST `/api/tools/market/sensors/uninstall`

从 `activate_sensor.json` 移除该 Sensor，并删除本地代码文件。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | 要移除的 Sensor 名称 |

**响应**

```json
{ "status": "success", "message": "Sensor 'feishu-bot' 已删除" }
```

未配置该 Sensor 时返回 `404`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/sensors/uninstall' -H 'Content-Type: application/json' -d '{"name":"feishu-bot"}'
```

---

## GET `/api/tools/market/graphs`

从官方 `PurrPod/graphs` 仓库拉取 `registry.json` 返回给前端市场。

**请求**

无参数。

**响应**

```json
{ "version": "1.0.0", "repository": "PurrPod/graphs", "graphs": [{ "name": "demo", "files": ["graph.json"] }] }
```

拉取失败时返回 `502`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/graphs'
```

---

## GET `/api/tools/market/graphs/installed`

返回本地 `graph` 目录下已安装的 Graph（文件夹结构）名字列表。

**请求**

无参数。

**响应**

```json
["demo", "writer"]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/graphs/installed'
```

---

## POST `/api/tools/market/graphs/install`

安装 Graph（文件夹结构）：从 registry 取文件清单逐文件下载落盘；安装前会检查 `graph.json` 声明的 mcp/skill 依赖，本地缺失的先从市场安装，市场也缺失时跳过。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | Graph 名称 |

**响应**

```json
{ "status": "success", "message": "Graph 'demo' 已安装到 ...（3 个文件）。已从市场自动安装 MCP 依赖: xxx" }
```

注册表缺失该 Graph 时返回 `404`，拉取/下载失败时返回 `502`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/graphs/install' -H 'Content-Type: application/json' -d '{"name":"demo"}'
```

---

## POST `/api/tools/market/graphs/uninstall`

删除 `{GRAPHS_DIR}/{name}` 文件夹。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | 要删除的 Graph 名称 |

**响应**

```json
{ "status": "success", "message": "Graph 'demo' 已删除" }
```

未安装该 Graph 时返回 `404`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/graphs/uninstall' -H 'Content-Type: application/json' -d '{"name":"demo"}'
```

---

## GET `/api/tools/market/ui-plugins`

从官方 `PurrPod/ui-plugins` 仓库拉取 `registry.json` 返回给前端市场。

**请求**

无参数。

**响应**

```json
{ "version": "1.0.0", "repository": "PurrPod/ui-plugins", "plugins": [{ "name": "hello", "root": "user" }] }
```

拉取失败时返回 `502`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/ui-plugins'
```

---

## GET `/api/tools/market/ui-plugins/installed`

返回已安装的 UI 插件名字列表（用户根 + 沙盒根两个可写根合并去重）。

**请求**

无参数。

**响应**

```json
["hello", "dashboard"]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/ui-plugins/installed'
```

---

## POST `/api/tools/market/ui-plugins/install`

安装 UI 插件到其注册表条目声明的 root（`user` → 用户根、`sandbox` → 沙盒根），逐文件从官方仓库下载落盘，并按插件声明的 dependency 逐一补齐 skill / mcp / sensor / graph / agentloop / plugin 依赖；依赖缺失或失败只记录说明，不阻断插件本体安装。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | UI 插件名称 |

**响应**

```json
{ "status": "success", "message": "UI 插件 'hello' 已安装到 ...（4 个文件）。..." }
```

注册表缺失该插件时返回 `404`；`root` 为 `builtin`（内置插件）时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/ui-plugins/install' -H 'Content-Type: application/json' -d '{"name":"hello"}'
```

---

## POST `/api/tools/market/ui-plugins/uninstall`

卸载 UI 插件：在用户根 / 沙盒根中找到该插件目录，移为同根下的 `<name>.trash`（可恢复）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | UI 插件名称 |

**响应**

```json
{ "status": "success", "message": "UI 插件 'hello' 已删除" }
```

未安装该插件时返回 `404`；名称含 `/`、`\` 或 `..` 时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/ui-plugins/uninstall' -H 'Content-Type: application/json' -d '{"name":"hello"}'
```

---

## GET `/api/tools/market/agentloops`

从官方 `PurrPod/agentloops` 仓库拉取 `registry.json` 返回给前端市场。

**请求**

无参数。

**响应**

```json
{ "version": "1.0.0", "repository": "PurrPod/agentloops", "agentloops": [{ "name": "demo", "files": ["demo.yaml"] }] }
```

拉取失败时返回 `502`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/agentloops'
```

---

## GET `/api/tools/market/agentloops/installed`

返回 `paradigms` 目录下已安装的 AgentLoop 名字列表。

**请求**

无参数。

**响应**

```json
["demo", "writer"]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/tools/market/agentloops/installed'
```

---

## POST `/api/tools/market/agentloops/install`

安装 AgentLoop（范式 YAML）到 `paradigms` 目录：从注册表取文件清单逐文件下载落盘，落盘后解析 YAML 校验 `hooks`；缺失或校验失败会报错。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | AgentLoop 名称 |

**响应**

```json
{ "status": "success", "message": "AgentLoop 'demo' 已安装到 ...（1 个文件）" }
```

注册表缺失该 AgentLoop 时返回 `404`；下载或 YAML 校验失败时返回 `502`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/agentloops/install' -H 'Content-Type: application/json' -d '{"name":"demo"}'
```

---

## POST `/api/tools/market/agentloops/uninstall`

卸载 AgentLoop：删除 `paradigms` 目录下对应的 YAML（默认 `PARADIGM` 除外）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | body | string | 是 | AgentLoop 名称 |

**响应**

```json
{ "status": "success", "message": "AgentLoop 'demo' 已删除" }
```

未安装该 AgentLoop 时返回 `404`；名称为 `PARADIGM`（大小写不敏感）或含 `/`、`\`、`..` 时返回 `400`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tools/market/agentloops/uninstall' -H 'Content-Type: application/json' -d '{"name":"demo"}'
```
