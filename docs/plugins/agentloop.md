# AgentLoop 开发指南（主循环范式）

> 落地目录：`~/.purrcat/paradigms/` ｜ 市场仓库：`PurrPod/agentloops` ｜ 相关接口：[../api/paradigms.md](../api/paradigms.md)

AgentLoop（范式 / PARADIGM）是 PurrCat Agent 的「主循环范式」：用一份 YAML 声明**每一轮循环在哪些阶段（stage）注入什么内容、执行什么检查**，从而定制 Agent 的思考与行动流程。

---

## 1. 运行时模型

- Agent 每轮循环依次触发若干**阶段（stage）**；每个阶段可挂若干个 **hook**，hook 按声明顺序执行。
- hook 三种典型作用：**注入**内容到系统提示/上下文、**执行检查**并决定循环能否结束、**产生反馈**（通过/失败提示词）。
- 命中 `on_loop_end` 的检查不满足时，若未达 `loop_end_max_retry` 上限，本轮回打重试。
- 范式可**会话级热切换**，且设计上**不破坏 KV Cache**（切换前后系统提示前缀保持一致）。

---

## 2. YAML 结构

```yaml
name: my-paradigm
description: 中文一句话描述
description-en: One-line English description.
path: agent_vm                # 执行环境标识（保持默认即可）
loop_end_max_retry: 3         # on_loop_end 检查未通过时的最大重试轮数
trigger:                      # 定时触发声明（可选）
  - cron:
      time: "08:08"
      injection: "【Demo】闹钟响了"
hooks:
  on_build_system_prompt:
    - injection: { content: "你是一个严谨的助手。" }
  on_input_received:
    - keyword_check: { keyword: "周报", type: user, successed_prompt: "用户要写周报：先列出数据来源与周期，再按模板生成。", failed_prompt: "本次输入与周报无关，不要生成周报。" }
  on_loop_start:
    - skill_info: { skills: ["my-skill"], failed_prompt: "缺少技能，请先获取。" }
  on_loop_end:
    - tool_use_check: { name: "finish_task", parameter_check: "summary", successed_prompt: "任务完成。", failed_prompt: "你必须调用 finish_task 并给出 summary 才能结束。" }
```

### 顶层字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 安装标识，与文件名一致 |
| `description` | 是 | 中文描述（市场展示）|
| `description-en` | 是 | 英文描述 |
| `path` | 是 | 执行环境，保持 `agent_vm` |
| `loop_end_max_retry` | 否 | `on_loop_end` 检查未通过时的最大重试轮数 |
| `trigger` | 否 | 定时触发声明（见下）|
| `hooks` | 是 | 阶段 → hook 列表的映射 |

### `trigger` 结构

数组，元素形如 `{ "cron": { "time": "HH:MM", "injection": "文本" } }`：到点向当前会话注入一条消息（定时唤醒类场景）。

---

## 3. 阶段（stage）清单（专有词汇表 · 阶段）

`hooks` 的键即阶段名，全部可选、按需声明：

| 阶段 | 时机 | 典型 hook |
| --- | --- | --- |
| `on_build_system_prompt` | 构建系统提示时 | `injection`、`memo_injection` |
| `on_input_received` | 收到用户输入时（携带本批 `received_messages`） | `keyword_check`、`injection`、`search` |
| `on_loop_start` | 一轮循环开始时 | `injection`、`skill_info`、`file_operation` |
| `on_loop_epoch` | 循环内每一 epoch（每次模型调用）前 | `injection`、`file_operation`、`command_run` |
| `on_tool_calling` | 即将调用工具时 | `tool_use_check`、`injection` |
| `on_loop_end` | 一轮循环结束判定时 | `tool_use_check`、`file_operation` |

> `keyword_check`（in检查）只检查「本批收到的输入」是否含关键词，因此仅在带 `received_messages` 的 `on_input_received` 阶段有意义；它不拦截输入，唯一产出就是提示词——两个提示词都留空则等于什么都没做。

> `on_build_system_prompt` 的**作用域**：主 Agent 会话里它是 system 头部；但在 **graph（任务图）的 `agent_loop` 节点**里，它的输出会被转成一条 **user** 消息、只在「从零开始的会话」时追加到上游输入末尾（不占 system 位、不破坏 KV Cache）。两个场景都照常写这个阶段即可，无需为 graph 改写范式。

---

## 4. hook 类型（专有词汇表 · 动作）

每个 hook 是一个「单键对象」：`<action>` 为键，值为该 action 的参数对象。

### 4.1 注入类

| action | 参数 | 说明 |
| --- | --- | --- |
| `injection` | `content` | 直接注入提示文本；`content` 支持 `@引用` |
| `memo_injection` | `type`、`count` | 注入记忆 `type` 取 `full` / `light` / `<自定义 key>`；`count` 为条目数 |

### 4.2 知识包/检索类

| action | 参数 | 说明 |
| --- | --- | --- |
| `skill_info` | `skills`、`failed_prompt` | 拼装指定技能的描述提示；缺失时给 `failed_prompt` |
| `search` | `query`、`route` | 调 Search 工具检索并注入结果；`route` ∈ `skill` / `mcp` / `memory` / `local`（技能+MCP）/ `web`，默认 `local` |

### 4.3 检查/反馈类

| action | 参数 | 说明 |
| --- | --- | --- |
| `tool_use_check` | `name`、`parameter_check`、`successed_prompt`、`failed_prompt` | 检查本轮是否调用了工具 `name`（可要求特定参数 `parameter_check`）；据此放行或回打并附提示 |
| `keyword_check` | `keyword`、`type`、`successed_prompt`、`failed_prompt` | in检查：看本批输入里有没有 `keyword`，`type` 只检查该类型的消息（留空不限）；只做提示注入、不拦截输入（见下方「in检查的语义」）|
| `file_operation` | `action`、`path`、`content`、`failed_prompt` | 文件检查/操作，`action` ∈ `read` / `exist_check` / `write_in` / `add_in` / `delete` |
| `command_run` | `command`、`return_log`、`failed_prompt` | 执行命令并按结果判定（`on_loop_epoch` 常用）|

### 4.4 其它通用参数

- `delay`：仅在第 `delay` 个 epoch 执行（与 `interval` 配合做“第 N 次才注入”）。
- `interval`：每 `interval` 个 epoch 执行一次。
- `expect`：`on_loop_end` 中 `"fail"` 表示“未满足才算通过”（用于反向结束条件）。

### 4.5 检查类动作的通用语义（重点：提示词才是它的产出）

- 检查类动作——`tool_use_check`、`keyword_check`、`file_operation` 的 `read` / `exist_check` / `delete`、`command_run`、`skill_info`——只做两件事：判断通过 / 不通过，并把 `successed_prompt` / `failed_prompt` 以 role=user 的提示消息注入回历史给模型看。
- 因此**不写提示词的检查等于白写**：条件不通过时既没有回打理由，也没有任何内容注入给模型。除「纯放行的闸门」外，都应写出 `failed_prompt`。
- 各阶段「不通过」的后果不同：

  | 阶段 | 不通过时的后果 | 提示词效果 |
  | --- | --- | --- |
  | `on_tool_calling` | 拦下本次工具调用的后续流程、继续循环 | 注入 `failed_prompt`，模型据此重来 |
  | `on_loop_end` | 未达 `loop_end_max_retry` 上限时整轮打回重试（系统另附一条通用打回提示）| 注入 `failed_prompt`；**通过时 `successed_prompt` 不生效**（结束即静默放行）|
  | `on_input_received` | **不拦不挡，只做提示**（不决定循环能否结束）| 命中注入 `successed_prompt`，未命中注入 `failed_prompt` |

- 结论：挂在 `on_input_received` 上的检查**价值 100% 体现在提示词上**，只写检查条件、两个提示词都留空，是最典型的“写了但没用”的写法。

### 4.6 in检查（`keyword_check`）的语义（重点）

- 它检查的是**输入侧**：本批 `type=user` 的输入消息里有没有 `keyword`——不检查模型输出，也不检查文件。
- 输入 = 真人 / 传感器等 `type=user` 的消息（每批 1 条或多条）；钩子自己注入的提示消息（`workflow_hint`）、`on_loop_end` 的打回提示等系统注入**不会触发本阶段**，无需再靠 `type: user` 去排除它们。
- 命中即通过、未命中即不通过，但它**不拦截输入、不阻塞流程、不影响循环能否结束**，唯一作用是往历史里追加一条提示，用来做**输入分诊**。
- 只在 `on_input_received` 上有意义：其他阶段拿不到本批输入，会**恒定判为「未命中」**并一直注入 `failed_prompt`。

```yaml
on_input_received:
  # 输入分诊：用户提到「周报」才引导周报流程；没提到也要明确告诉模型别乱走流程
  - keyword_check:
      keyword: "周报"
      type: user
      successed_prompt: "用户要写周报：先列出数据来源与周期，再按模板生成。"
      failed_prompt: "本次输入与周报无关，不要生成周报，按用户真实诉求处理。"
```

### 4.7 `@引用` 语法（`injection.content` 内可直接使用）

| 引用 | 含义 |
| --- | --- |
| `@RULES` | 系统规则 |
| `@INFO` | 环境信息 |
| `@SOUL` | 人格/灵魂设定 |
| `@MEMORY` | 记忆 |
| `@SYS` | 系统提示 |
| `@USERQUERY` | 本轮用户输入 |
| `@TASKSPACE` | 任务空间 |
| `@PLAN` | BrainStorm 总计划（每次调用 BrainStorm 刷新；无计划时返回「暂无 BrainStorm 计划」） |

---

## 5. 完整示例（带重试的“必须调工具才能结束”）

```yaml
name: strict-finish
description: 强制 Agent 调用 finish_task 并提供 summary 才允许结束
description-en: Force the agent to call finish_task with a summary before ending.
path: agent_vm
loop_end_max_retry: 3
hooks:
  on_build_system_prompt:
    - injection: { content: "@RULES\n你必须在结束前调用 finish_task。" }
  on_loop_epoch:
    - injection:
        content: "当前进度：{{@TASKSPACE}}"
        interval: 3
  on_loop_end:
    - tool_use_check:
        name: "finish_task"
        parameter_check: "summary"
        successed_prompt: "任务已完成，可以结束。"
        failed_prompt: "尚未调用 finish_task 或缺少 summary 参数，请补齐后重试。"
```

---

## 6. 使用与接口

- 列出/读取/保存：`GET /api/paradigms`、`GET/POST /api/paradigms/{name}`。
- 会话热切换：`POST /api/sessions/{session_id}/paradigm`（切换后 KV Cache 前缀保持，冷启动更快）。
- 默认范式：`~/.purrcat/paradigms/PARADIGM.yaml`；用户未提供时回退到内置 `src/agent/system_rules/PARADIGM.yaml`。

