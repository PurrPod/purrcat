# Graph 开发指南（任务编排中枢）

> 落地目录：`~/.purrcat/graph/<name>/` ｜ 市场仓库：`PurrPod/graphs` ｜ 相关接口：[../api/graph.md](../api/graph.md)

Graph（任务图 / 工作流）用**节点（Node）+ 边（Edge）**描述多步骤工作流；每个 Graph 是**独立文件夹**，由运行时引擎按拓扑顺序执行。

---

## 1. 目录与文件约定

```text
graphs/<graph-name>/          # 市场仓库中的单元
├── graph.json                # 图定义（必需）
└── asset/                     # 静态资源：看板 html 等（可选）
```

**文件夹名 = `graph.json` 内的 `name` 字段**，两者必须严格一致（CI 校验）。

---

## 2. `graph.json` 顶层字段

```json
{
  "version": "2.0",
  "name": "my_graph",
  "description": "One-line English description.",
  "description-zh": "一句话中文描述。",
  "core": "openai:deepseek-v4-flash",
  "global_schema": { "prompt": { "type": "string", "required": true, "description": "用户任务描述" } },
  "nodes": [ ... ],
  "edges": [ ... ],
  "dashboard": "purrcat://graph/my_graph/asset/dashboard.html"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 安装标识，必须与文件夹名一致 |
| `description` | 是 | 英文描述（市场展示）|
| `description-zh` | 是 | 中文描述（市场中文展示）|
| `version` | 否 | Graph 规范版本（当前 `"2.0"`）|
| `core` | 否 | 该图执行所用模型，缺省 `openai:deepseek-v4-flash` |
| `global_schema` | 否 | 全局输入变量的类型声明与必填校验；驱动前端表单 + 运行时参数校验 |
| `nodes` | 否 | 节点定义数组 |
| `edges` | 否 | 连边定义数组 |
| `dashboard` | 否 | 看板地址：单个字符串，或多看板数组 `[{ "name": "...", "url": "..." }]` |

### `global_schema` 结构

键 = 变量名，值 = `{ "type": <类型>, "required": <bool>, "description": "<给用户的提示>" }`。运行时据此校验必填、缺失或多余参数（不满足会直接置任务为 ERROR 并回报参数清单）。

```json
"global_schema": {
  "prompt": { "type": "string", "required": true, "description": "用户任务描述" },
  "depth":  { "type": "number", "required": false }
}
```

---

## 3. 节点对象结构

```json
{
  "id": "nd_tpl",
  "type": "template_renderer",
  "name": "组装指令",
  "position": [100, -50],
  "config": { "template": "你好 {{prompt}}" }
}
```

| 字段 | 说明 |
| --- | --- |
| `id` | 节点唯一标识（图内不重复），边通过它连线 |
| `type` | 节点类型（取值见第 4 节）|
| `name` | 节点显示名（画布上展示）|
| `position` | `[x, y]` 画布坐标 |
| `config` | 该节点类型的配置对象（键随 `type` 而变）|

### 端口与触发语义

- 端口分 **static**（固定输入端/输出端）与 **dynamic**（由 `config` 内容动态生成的端口）。
- 动态端口由 `dynamic_rules` 驱动：常见为 `{ "watch_config": "<config键>", "method": "array_map" }`（配置里列了几项就生成几个端口），模板类用 `{ "watch_config": "template", "method": "regex", "pattern": "..." }`（按模板里的变量名生成）。
- **触发端口 `trigger`**：若某节点有 `trigger` 输入端口且**未连线**，该节点在**开局自动执行**；若**连线**，则等待收到上游数据/信号后再执行。

---

## 4. 节点类型清单（专有词汇表）

节点定义由 `GET /api/graphs/nodes` 返回；源码位于 `src/harness/node/extensions/<type>/<type>.json`。

| `type` | 名称 | 用途 | 主要端口（输入 → 输出）|
| --- | --- | --- | --- |
| `task_input` | 全局输入 | 声明外部参数，按 `global_vars` 生成动态输出 | — → `global_vars`（dynamic）|
| `task_output` | 全局输出 | 定义最终返回的数据 | `target_vars`（dynamic）→ — |
| `string` | 自定义输入 | 直接书写内容，派生字符串/数字/布尔/JSON 四类输出 | `trigger` → `text`/`number`/`boolean`/`json` |
| `template_renderer` | 模板渲染器 | 用 Jinja2 把 `{{变量}}` 注入模板 | `template`/`dynamic_vars` → `rendered_text` |
| `message_card_builder` | 消息卡片构建器 | 把文本+角色包装成标准 MessageList | `content`/`role` → `message_list` |
| `appender` | 列表追加 | 把 `append_list` 追到 `base_list` 后 | `base_list`/`append_list` → `merged_list` |
| `json_builder` | JSON 构建器 | 按 `kv_pairs` 组装 JSON 字符串 | `kv_pairs`（dynamic）→ `json_string` |
| `json_extractor` | JSON 提取器 | 按 `extract_keys` 从 JSON 精准取值 | `data` → `extract_keys`（dynamic）|
| `env_loader` | 环境变量加载器 | 读图目录 `env.json`，按 `exposed_keys` 暴露 | — → `exposed_keys`（dynamic）|
| `skill_info` | Skill 知识包 | 按 `skills_list` 拼装技能描述提示词 | `trigger` → `skill_kit_string` |
| `mcp_info` | MCP 知识包 | 按 `mcp_servers` 拼装 MCP 工具描述提示词 | `trigger` → `mcp_kit_string` |
| `agent_loop` | 智能体循环 | 范式驱动的 Agent 大循环（见 [agentloop.md](agentloop.md)）| `messages`/`agentloop` → `messages`/`summary` |
| `human_intervention` | 人工干预 | 挂起工作流，等人于前端输入指令后放行 | `trigger`/`context_data`/`prompt` → `human_reply`/`context_data` |
| `command` | 命令执行 | 按目标 OS 在宿主机执行命令行 | `command`/`os` → `stdout`/`stderr`/`exit_code`/`skipped` |
| `file_reader` | 文件读取/预览 | 读取/预览 string 或 file（图片/文本/HTML/SVG/PDF）| `source` → `content`/`file` |
| `file_writer` | 文件落盘 | 把文本写入文件，输出 file 信封 | `content`/`filename` → `file` |

> **信封（Envelope）协议**：节点间流转的不只是裸值，还有带类型的「信封」。已废弃的旧节点类型（如旧预览/旧字符串节点）在信封协议重构中移除，加载时会报错并提示改用 `file_reader`/`string`/`agent_loop` 等。

---

## 5. 边（Edge）与数据流映射

```json
{ "source": "nd_input", "target": "nd_tpl", "sourceHandle": "prompt", "targetHandle": "prompt" }
```

| 字段 | 说明 |
| --- | --- |
| `source` | 上游节点 `id` |
| `target` | 下游节点 `id` |
| `sourceHandle` | 上游节点的**输出端口名**（不写默认为 `"default"`）|
| `targetHandle` | 下游节点的**输入端口名**（不写默认为 `"default"`）|

运行时按 `edges` 推导每个节点的输入：目标端口的取值来自上游对应输出端口。同一节点可被多条边连入/连出，实现字段级精确映射。

---

## 6. 看板与 `purrcat://` URI

任务产出的文件通过 `purrcat://` URI 引用，运行时将其映射到真实路径：

- `purrcat://graph/<name>/asset/<file>` → `{GRAPHS_DIR}/<name>/asset/<file>`（看板/静态资源）
- 其他产物按信封协议解析；`GET /api/tasks/{task_id}/artifact?uri=<uri>` 可下载。

`dashboard` 指向 `asset/` 下的 html 时写作：

```json
"dashboard": "purrcat://graph/my_graph/asset/dashboard.html"
```

---

## 7. 最小可用示例

```json
{
  "version": "2.0",
  "name": "hello_graph",
  "description": "Render a greeting and hand it to an agent loop.",
  "description-zh": "渲染问候语并交给智能体循环。",
  "global_schema": {
    "name": { "type": "string", "required": true, "description": "称呼" }
  },
  "nodes": [
    { "id": "in", "type": "task_input", "name": "全局输入", "position": [-400, 0],
      "config": { "global_vars": [{ "name": "name", "required": true }] } },
    { "id": "tpl", "type": "template_renderer", "name": "组装指令", "position": [-100, 0],
      "config": {} },
    { "id": "tpl_text", "type": "string", "name": "模板内容", "position": [-350, -180],
      "config": { "value": "你好 {{name}}，请做一次自我介绍。" } },
    { "id": "card", "type": "message_card_builder", "name": "构建消息", "position": [200, 0],
      "config": { "role": "user" } },
    { "id": "loop", "type": "agent_loop", "name": "智能体循环", "position": [500, 0],
      "config": {} },
    { "id": "out", "type": "task_output", "name": "全局输出", "position": [800, 0],
      "config": { "target_vars": [{ "name": "reply" }] } }
  ],
  "edges": [
    { "source": "in",  "target": "tpl",  "sourceHandle": "name",          "targetHandle": "name" },
    { "source": "tpl_text", "target": "tpl", "sourceHandle": "text",      "targetHandle": "template" },
    { "source": "tpl", "target": "card", "sourceHandle": "rendered_text", "targetHandle": "content" },
    { "source": "card", "target": "loop", "sourceHandle": "message_list", "targetHandle": "messages" },
    { "source": "loop", "target": "out", "sourceHandle": "summary",       "targetHandle": "reply" }
  ]
}
```

---

## 8. 开发与调试

- **可视化编辑**：前端 DAG 画布内置编辑与一键 JSON 导入/导出。
- **保存/读取**：`GET/POST /api/graphs/{name}`、`GET /api/graphs/{name}/schema`（返回 `global_schema` 供前端生成表单）。
- **运行**：`POST /api/tasks/run`（工作流名 + 初始参数，后台异步执行），状态走 `GET /api/tasks/{task_id}/state`。
- **热更新**：`graph.json` 落盘即被后续任务读取，无需重启。

---

## 9. 安装与提交

- 安装：`/api/tools/market/graphs/install`（下载到 `~/.purrcat/graph/<name>/`）。
- 提交：在 `extension/graphs/graphs/<graph-name>/`（含 `graph.json`，可选 `asset/`）提 PR。CI 校验文件夹名与 `name` 一致、三个必填描述字段非空；合并后自动合并为全局 `registry.json`。
