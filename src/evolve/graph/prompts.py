"""graph 提示词模板（从 guide_generator 逐字搬移，内容不可改写）。"""

"""
Graph 指南生成器模块 (evolve/graph/guide_generator.py)
单文件指南：覆盖目录约定、节点/边词汇表、校验与提交全流程。
"""


def build_graph_guide(name: str, goal: str = "") -> str:
    goal_section = f"\n> 🎯 **本次构建目标**：{goal}\n\n" if goal else ""
    return f"""# {name} Graph 工厂指南 (GUIDE)

Graph（任务图 / 工作流）是「任务编排中枢」：用**节点（Node）+ 边（Edge）**描述一条多步骤工作流。
每个 Graph 是一个独立文件夹（`graph.json` + 可选 `asset/`），由运行时引擎按拓扑顺序执行。
本指南覆盖结构规范、专有词汇表、校验与提交全流程，动手前请先通读。
{goal_section}
## 1. 目录约定

```text
{name}/                       # 沙盒内你的图文件夹
├── graph.json                # 图定义（必需）
└── asset/                    # 静态资源（可选）
```

**文件夹名 = `graph.json` 内的 `name` 字段**，两者必须严格一致（合并校验会拦）。

## 2. graph.json 顶层字段

```json
{{
  "version": "2.0",
  "name": "{name}",
  "description": "One-line English description.",
  "description-zh": "一句话中文描述。",
  "core": "openai:deepseek-v4-flash",
  "global_schema": {{ "prompt": {{ "type": "string", "required": true, "description": "用户任务描述" }} }},
  "nodes": [ ... ],
  "edges": [ ... ]
}}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 必须与文件夹名一致 |
| `description` | 是 | 英文描述（市场展示）|
| `description-zh` | 是 | 中文描述 |
| `version` | 建议 | 规范版本（当前 `"2.0"`）|
| `core` | 否 | 该图执行所用模型，缺省 `openai:deepseek-v4-flash` |
| `global_schema` | 否 | 全局输入变量声明 `{{ 变量名: {{ type, required, description }} }}`，驱动前端表单与运行时校验 |
| `nodes` | 否 | 节点定义数组 |
| `edges` | 否 | 连边定义数组 |

## 3. 节点对象与端口语义

```json
{{ "id": "nd_tpl", "type": "template_renderer", "name": "组装指令", "position": [100, -50],
  "config": {{ "template": "你好 {{{{prompt}}}}" }} }}
```

| 字段 | 说明 |
| --- | --- |
| `id` | 节点唯一标识（图内不重复），边通过它连线 |
| `type` | 节点类型（见第 4 节白名单）|
| `name` | 节点显示名 |
| `position` | `[x, y]` 画布坐标 |
| `config` | 该节点类型的配置对象；**只有少数节点需要填**，见第 4.1 节 |

* 端口分 **static**（固定）与 **dynamic**（由 `config` 动态生成，如 `task_input.global_vars` 生成输出端口、
  `template_renderer.template` 里的 `{{{{变量}}}}` 生成输入端口）。
* **触发端口 `trigger`**：若节点有 `trigger` 输入端口且**未连线**，开局自动执行；**连线**则等上游信号。

## 4. 节点类型白名单（专有词汇表）

| `type` | 名称 | 主要端口（输入 → 输出）| `config` 需填 |
| --- | --- | --- | --- |
| `task_input` | 全局输入 | — → `dynamic_outputs`（按 global_vars 生成）| `global_vars` |
| `task_output` | 全局输出 | `dynamic_inputs` → — | `target_vars` |
| `string` | 自定义输入 | `trigger` → `text`/`number`/`boolean`/`json` | `value` |
| `template_renderer` | 模板渲染器 | `template`/`dynamic_vars`/`trigger` → `rendered_text` | `template` |
| `message_card_builder` | 消息卡片构建器 | `content`/`role`/`trigger` → `message_list` | — |
| `appender` | 列表追加 | `base_list`/`append_list` → `merged_list` | — |
| `json_builder` | JSON 构建器 | `dynamic_inputs`/`trigger` → `json_string` | `kv_pairs` |
| `json_extractor` | JSON 提取器 | `data` → `dynamic_outputs` | `extract_keys` |
| `env_loader` | 环境变量加载器 | — → `dynamic_outputs` | `exposed_keys` |
| `skill_info` | Skill 知识包 | `trigger` → `skill_kit_string` | `skills_list` |
| `mcp_info` | MCP 知识包 | `trigger` → `mcp_kit_string` | `mcp_servers` |
| `agent_loop` | 智能体循环 | `messages`/`agentloop` → `messages`/`summary` | 范式靠端口，`config` 可留空 |
| `human_intervention` | 人工干预 | `trigger`/`context_data`/`prompt` → `human_reply`/`context_data` | — |
| `command` | 命令执行 | `command`/`os`/`trigger` → `stdout`/`stderr`/`exit_code`/`skipped` | — |
| `file_reader` | 文件读取/预览 | `trigger`/`source` → `content`/`file` | — |
| `file_writer` | 文件落盘 | `trigger`/`content`/`filename` → `file` | — |

> 已废弃类型（`preview`、`if_else_router`、`python_runner` 等）会被校验器判错，必须改用上表类型。

### 4.1 `config` 只有少数节点需要填（重点）

**上表 `config` 需填 列为 `—` 的 7 种节点完全不需要 `config`**（写成 `{{}}` 或干脆省略即可）：
`message_card_builder`、`appender`、`human_intervention`、`command`、`file_reader`、`file_writer`，
外加 `agent_loop`（它唯一的 `config.summary_file` 有默认值 `summary.txt`，可留空）。
它们的行为**全靠输入端口**决定，不要凭空臆造 config 字段。

其余 9 种节点的 `config` 字段如下（下表字段名是固定的，写错名字不会生效）：

| 节点 | `config` 字段 | 类型 | 说明与示例 |
| --- | --- | --- | --- |
| `task_input` | `global_vars` | list | 声明全局输入变量，逐项 `{{name, required, description}}`，据此生成输出端口与任务表单。示例：`[{{"name":"prompt","required":true,"description":"用户任务描述"}}]` |
| `task_output` | `target_vars` | list | 声明要输出的目标键，逐项 `{{name}}`，据此生成动态输入端口 |
| `string` | `value` | textarea | 常量内容正文，节点按内容自动派生 `text`/`number`/`boolean`/`json` 输出端口 |
| `template_renderer` | `template` | textarea | Jinja2 模板正文，正文里的 `{{{{变量}}}}` 会派生左侧输入端口；若另有连线接入 `template` 端口，**连线内容优先** |
| `json_builder` | `kv_pairs` | list | 要构建的 JSON 键名，逐项 `{{name}}`；某键有连线时取连线值，无连线则取此处默认值 |
| `json_extractor` | `extract_keys` | list | 要从输入 JSON 中提取的键名（支持嵌套），逐项 `{{name}}` |
| `env_loader` | `exposed_keys` | list | 从本工作流 `env.json` 中暴露的键名，逐项 `{{name}}`；未声明者保持隐藏，避免数据流污染 |
| `skill_info` | `skills_list` | list | 推荐给 Agent 的技能名，逐项 `{{name}}`；**必须先用 `Search(route="skill")` 查证其真实存在** |
| `mcp_info` | `mcp_servers` | list | 推荐给 Agent 的 MCP 服务器名，逐项 `{{name}}`；**必须先用 `Search(route="mcp")` 查证其真实存在** |

> **`agent_loop` 用哪个范式，不是靠 `config`**：由它的 `agentloop` **输入端口**决定（常见做法：用 `string` 节点写一个常量接进去）。该端口接受三种形态：
> ① 完整的 AgentLoop YAML 文本；② **范式名**（如 `"video-editing"`，运行时经 `resolve_paradigm_path` 解析到 `~/.purrcat/paradigms/<名>.yaml`）；③ 范式文件的绝对路径。
> 不连线则按**空范式**执行：**完全不响应任何钩子**（不构建系统提示、不注入、不做结束校验），也不会回退默认范式。传范式名是**合法且推荐**的用法。

## 5. 边（Edge）映射

```json
{{ "source": "nd_input", "target": "nd_tpl", "sourceHandle": "prompt", "targetHandle": "prompt" }}
```

| 字段 | 说明 |
| --- | --- |
| `source` / `target` | 上游 / 下游节点 `id`（都必须存在，校验器会拦）|
| `sourceHandle` | 上游输出端口名（不写默认 `"default"`）|
| `targetHandle` | 下游输入端口名（不写默认 `"default"`）|

## 6. 编排建议（最佳实践）

* **引用技能 / MCP 前必须先用 `Search` 工具查证，严禁瞎编**：`skill_info.skills_list` 里只能写宿主机上**真实存在**的技能名，
  `mcp_info.mcp_servers` 里只能写**真实配置过**的 MCP 服务器名。动笔前先调用 `Search` 工具确认：
  `Search(route="skill", query="<技能名或用途>")`、`Search(route="mcp", query="<服务器名或工具名>")`，
  或用 `Search(route="local", query="<用途>")` 一次混合搜索技能库与 MCP 工具。
  **搜不到就不写**——宁可不给推荐、或改让 Agent 自行处理，也绝不捏造一个不存在的技能 / MCP 服务器名。
* **尽量不用命令执行节点**：能交给 Agent 解决的就不要用 `command` 节点，直接把要做的事写进提示词交给 `agent_loop` 即可。
* **不通用就别单独建 AgentLoop**：若这段 Agent 逻辑只是本图专用、没有复用价值，就不必单独做一个 `agentloop` 范式，直接把提示词写在 `string`（自定义输入）节点里，接到 `agent_loop` 的 `messages` 输入即可；只有通用、可被多处复用的逻辑才值得沉淀成独立范式。
* **复杂任务拆多个 Agent**：一个 `agent_loop` 只承担单一职责，复杂任务应拆成多个 `agent_loop` 节点，让每个节点的提示词保持聚焦、不臃肿。
* **独立子任务并行**：彼此独立的子任务拆成并行分支，让多个 `agent_loop` 同时推进，提高整体效率。
* **上下文交接分两种**：前后环节相关性高的，把上游 `messages` 接到下游 `messages`，用**共享上下文**无缝交接；相关性不高的，只接上游 `summary` 传递摘要即可，避免把无关历史灌给下游。**判据、接线与 KV Cache 注意事项见第 7 节；但多路分支汇合一律走 `summary`（见 7.4）。**

## 7. agent_loop 上下文交接：什么时候直连 `messages`，什么时候用 `summary`

**唯一判据是前后环节的关联强度**：前后信息关联度大 → 直连 `messages`；关联度小 → 只传 `summary`。

> ⚠️ **直连 `messages` 仅限「单条串行链」**（A → B → C，一路往下传）。**两路及以上分支汇合时必须改用 `summary`**，详见 7.4。

### 7.1 强关联阶段：直连 `messages`（信息丢失率最小，首选，仅限串行链）

上游 `agent_loop` 的 `messages` 是它**完整的思考轨迹**（含每一步工具调用、工具原始返回、试错过程）。
把新阶段指令**直接拼接**到这条历史尾部再交给下一个 `agent_loop`，等于让下游 Agent 读到全部一手证据，
**信息丢失率最小**；而 `summary` 是上游自己写的压缩总结，字段、数值、失败经验在压缩传递过程中天然会损耗，
下游拿到的只是一个"转述版"——**所以只要前后阶段需要共享过程细节，就应该直连 `messages`，不要图省事用 `summary`。**

标准接线（三节点组合，`appender` 负责拼接）：

```json
[
  {{ "source": "loop_a", "target": "merge_ab", "sourceHandle": "messages", "targetHandle": "base_list" }},
  {{ "source": "card_b", "target": "merge_ab", "sourceHandle": "message_list", "targetHandle": "append_list" }},
  {{ "source": "merge_ab", "target": "loop_b", "sourceHandle": "merged_list", "targetHandle": "messages" }}
]
```

* `loop_a` 是上游 `agent_loop`，`loop_b` 是下一个 `agent_loop`，`merge_ab` 是 `appender`，
  `card_b` 是 `message_card_builder`（内容来自 `string` 或 `template_renderer`），承载"进入下一阶段"的指令。
* 新阶段指令**必须用 `role=user`**，不要拿它当 `system` 覆盖：历史里出现第二个 system 会语义冲突，且破坏前缀缓存（见 7.3）。
* 直连要"只加不改"：**不要**用 `template_renderer` 把整段历史拼成一段新文本重排后再传——那会把结构化历史压成一段散文，
  既丢结构，也让缓存前缀失效。

### 7.2 弱关联阶段：传 `summary`

仅当上游的过程细节对下游决策确实无用、且上下文预算紧张时，才用上游 `summary`（可直接接下游 `messages`，或经 `template_renderer` 织入）。
它省 token，但**有损**；两个阶段越接近"各干各的"，越适合用 summary。

### 7.3 直连时必须保护 KV Cache

直连的优势一半来自信息完整，另一半来自**前缀缓存复用**：下游收到的消息是「上游历史 + 尾部追加一条 user 指令」，
前缀与上游逐字一致，云侧可直接命中 KV Cache，长图里时延与成本都明显更低。因此：

* ✅ **只在尾部追加**（`appender` 天然满足）。
* ✅ **graph 里从不构建 `system` 角色**：`agent_loop` 节点不会再把范式的 `on_build_system_prompt` 输出插到头部，
  而是把它转成一条 **user** 消息，且**只在「从零开始的会话」（该节点记忆尚为空）时追加到上游输入末尾**一次。
  所以角色提示词照旧写在范式里即可；下游直连 `messages` 时会原样沿用上游历史，节点不重排、也不会再插 system，
  会话中途绝不刷新系统提示。
* ❌ **不要在追加指令里追加 `role=system` 的消息**：历史中途插入 system 会让其后所有 token 的位置整体后移，
  **KV Cache 直接失效**（语义上也会出现第二个 system）。新阶段指令一律用 `role=user`。
* ❌ **不要改写 / 删除 / 前插已有消息**：把新指令插到历史前面、或重排历史，都会改变前缀，整段缓存作废。
* ✅ 同一张图尽量保持同一个 `core` 模型与同一把密钥；模型 / 密钥跳变会让已缓存的前缀失效。
* ✅ `agentloop` 的 hook 注入（`on_loop_start` 等）本身就是尾部追加的 `user` 消息，保持这种"只追加"的写法，不要在 hook 里改动历史。

### 7.4 多路汇合：必须用 `summary` 合并，严禁拼接多份完整上下文

直连只适用于**单条串行链**。当**两路及以上并行的 Agent 分支要汇合**时（如多位分析师并行跑完，再由一个决策 Agent 汇总）：

* **必须**在各支路上取 `summary`（接 `template_renderer` 织成一份汇总指令，或经 `message_card_builder` 转成 `user` 消息），
  统一**用 `summary` 传递合并**；
* **严禁**用 `appender` 把两份及以上的完整 `messages` 首尾拼起来汇合：N 路就是 N 份完整轨迹，
  上下文长度**线性膨胀**，严重损耗上下文窗口，还把大量与汇总无关的过程塞给下游；并且从第二份起历史里会再出现 system 消息，
  语义混乱、缓存前缀也会失效；
* 汇合点的 `string`/`template_renderer` 提示词要写清"以下是各支路提交的报告摘要"，让下游只基于摘要做汇总决策。

## 8. 校验脚本（格式 / 功能 / 关键词汇）

沙盒内置自测脚本 `evals/validate.py`，做三重校验：

* **格式**：`graph.json` 可解析；顶层为对象；`name` 与文件夹名一致；`description`/`description-zh` 非空。
* **关键词汇**：每个节点的 `type` 必须属于白名单（已废弃类型直接判错）；节点 `id` 唯一。
* **功能**：边的 `source`/`target` 必须指向已定义节点；端口名与类型匹配性复核（动态端口仅告警）；
  检出**孤立节点**（既无连边又无 trigger，开局不会执行）；`global_schema` 必填键与 `task_input` 声明的一致性。

```bash
cd /agent_vm/graph_workplace/<uuid>/{name}
uv run evals/validate.py
```

结论写入 `evals/outputs/validation.json`。**有 ❌（error）项一律不许提交合并**，⚠️（warn）项按需处理。

报告会**逐条打印全部校验项**（编号 + `✅ PASS` / `❌ FAIL` / `⚠️ WARN` + 明细），不只列失败项，末尾附「通过 N/M」统计——
所以无需再自写补充校验脚本兜底；以本脚本输出为准即可。

## 9. 提交合并

校验全绿后调用 `KernelUpgrade(action="merge", type="graph", target="uuid/{name}")` 申请合并审批（uuid 为沙盒目录名）。批准后系统会：
1. 把整个 `{name}/` 文件夹拷贝到正式目录 `~/.purrcat/graph/`；
2. Git 提交版本记录，落盘即被后续任务读取（热更新，无需重启）。

合并前系统会**宿主侧重跑同一套校验**（防止篡改脚本），有错直接拒绝——所以务必先自查再申请。
"""


__all__ = ["build_graph_guide"]
