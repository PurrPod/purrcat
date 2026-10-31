"""
AgentLoop 指南生成器模块 (evolve/agentloop/guide_generator.py)
单文件指南：覆盖范式模型、阶段/动作词汇表、校验与提交全流程。
"""


def generate_agentloop_guide(name: str, goal: str = "") -> str:
    goal_section = f"\n> 🎯 **本次构建目标**：{goal}\n\n" if goal else ""
    return f"""# {name} AgentLoop 工厂指南 (GUIDE)

AgentLoop（范式 / PARADIGM）用一份 YAML 声明**每一轮循环在哪些阶段注入什么内容、执行什么检查**，
从而定制 Agent 的思考与行动流程。本指南覆盖结构规范、专有词汇表、校验与提交全流程，动手前请先通读。
{goal_section}
> ⚠️ **动手前先查证能力，严禁瞎编工具 / 技能**：凡是要写进 `skill_info.skills` 的**技能名**、或要经 `CallMCP` 调用的 **MCP 工具名**，
> 都必须先确认它真实存在于宿主机。**写之前请先调用 `Search` 工具查证**：
> `Search(route="skill", query="<技能名或用途>")`、`Search(route="mcp", query="<服务器名或工具名>")`，
> 或用 `Search(route="local", query="<用途>")` 一次混合搜索技能库与 MCP 工具。
> **搜不到就不要写**——宁可改用原生工具、或把该步骤交给 Agent 自行处理，也绝不捏造一个不存在的技能 / MCP 工具名。

## 1. 运行时模型

* Agent 每轮循环依次触发若干**阶段（stage）**；每个阶段可挂若干 **hook**，按声明顺序执行。
* hook 三种典型作用：**注入**内容、**检查**并决定循环能否结束、**反馈**（通过/失败提示词）。
* 命中 `on_loop_end` 的检查不满足时，若未达 `loop_end_max_retry` 上限，本轮回打重试。
* 范式支持**会话级热切换**，且切换前后系统提示前缀保持一致（不破坏 KV Cache）。

## 2. YAML 结构

```yaml
name: {name}                      # 安装标识，必须与本文件名一致
description: 一句话中文描述
description-en: One-line English description.
path: agent_vm                     # 执行环境标识（保持默认即可）
loop_end_max_retry: 3              # on_loop_end 检查未通过时的最大重试轮数（可选）
hooks:                             # 阶段 → hook 列表（必填、非空）
  on_build_system_prompt:
    - injection: {{ content: "@RULES" }}
  on_input_received:
    - keyword_check:                 # in检查：只看本批输入，命中/未命中都靠提示词生效
        keyword: "周报"
        type: user                    # 只看真实用户消息（留空则不限类型）
        successed_prompt: "用户要写周报：先列出数据来源与周期，再按模板生成。"
        failed_prompt: "本次输入与周报无关，不要生成周报，按用户真实诉求处理。"
  on_loop_start:
    - skill_info: {{ skills: ["my-skill"], failed_prompt: "缺少技能，请先获取。" }}
  on_loop_end:
    - tool_use_check:
        name: "Memo"                   # 必须是宿主机原生工具名（见第 4 节工具清单）
        parameter_check:               # 检查项列表：任一项匹配即算「用了且满足条件」
          - action: "add"              # 一项内多个键需同时满足（精确相等）
        successed_prompt: "记忆已更新。"
        failed_prompt: "结束前请先用 Memo 记录本轮经验。"
```

**顶层字段**

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 安装标识，与文件名一致 |
| `description` | 建议 | 中文描述（市场展示）|
| `description-en` | 建议 | 英文描述 |
| `path` | 建议 | 执行环境，保持 `agent_vm` |
| `loop_end_max_retry` | 否 | `on_loop_end` 检查未通过时的最大重试轮数 |
| `hooks` | 是 | 阶段 → hook 列表的映射，非空 |

## 3. 阶段清单（专有词汇表 · 阶段）

`hooks` 的键即阶段名，全部可选、按需声明：

| 阶段 | 时机 | 典型 hook |
| --- | --- | --- |
| `on_build_system_prompt` | 构建系统提示时 | `injection`、`memo_injection` |
| `on_input_received` | 收到用户输入时（携带本批 received_messages） | `keyword_check`、`injection`、`search` |
| `on_loop_start` | 一轮循环开始时 | `injection`、`skill_info`、`file_operation` |
| `on_loop_epoch` | 循环内每个 epoch（每次模型调用）前 | `injection`、`file_operation`、`command_run` |
| `on_tool_calling` | 即将调用工具时 | `tool_use_check`、`injection` |
| `on_loop_end` | 一轮循环结束判定时 | `tool_use_check`、`file_operation` |

> `keyword_check`（in检查）只检查「本批收到的输入」是否含关键词，因此仅在带 `received_messages` 的
> `on_input_received` 阶段有意义；它不拦截输入，唯一产出就是提示词——两个提示词都留空则等于什么都没做。
>
> `on_build_system_prompt` 的**作用域**：主 Agent 会话里它是 system 头部；但在 **graph（任务图）的 `agent_loop` 节点**里，
> 它的输出会被转成一条 **user** 消息、只在「从零开始的会话」时追加到上游输入末尾（不占 system 位、不破坏 KV Cache）。
> 两个场景都照常写这个阶段即可，无需为 graph 改写范式。
>
> `on_loop_epoch` 上的 `injection` 必须写 `interval`（或 `delay`），**禁止每轮注入**（见「周期性提醒的注入规则」）。

## 4. 动作清单（专有词汇表 · 动作）

每个 hook 是「单键对象」：`<action>` 为键，值为该 action 的参数对象。

| action | 必填参数 | 说明 |
| --- | --- | --- |
| `injection` | `content` | 直接注入提示文本；`content` 支持 `@引用` |
| `memo_injection` | — | 注入记忆，参数 `type`（`full`/`light`/自定义 key）、`count` |
| `skill_info` | `skills` | 拼装指定技能的描述提示；缺失时给 `failed_prompt` |
| `search` | `query` | 调 Search 检索并注入结果，`route` ∈ `skill`/`mcp`/`memory`/`local`/`web` |
| `tool_use_check` | `name` | 检查本轮是否调用**原生工具** `name`（可要求 `parameter_check`），据此放行或回打；检查 MCP 工具须用 `CallMCP` 的参数检查（见下方「工具使用检查的语义」） |
| `keyword_check` | `keyword` | in检查：看本批输入里有没有 `keyword`，`type` 只检查该类型的消息（留空不限）。只在 `on_input_received` 上有意义，且只做提示注入、不拦截输入（见下方「in检查的语义」）|
| `file_operation` | `action` | 文件检查/操作，`action` ∈ `read`/`exist_check`/`write_in`/`add_in`/`delete` |
| `command_run` | `command` | 执行命令并按结果判定（`on_loop_epoch` 常用） |

**通用可选参数**：`delay`（仅第 `delay` 个 epoch 执行）、`interval`（每 `interval` 个 epoch 执行一次）、
`expect`（仅 `on_loop_end`：取 `false` 或 `"fail"` 时，表示该检查“未满足”才算通过，用以放行跳出循环）。

**周期性提醒的注入规则（硬性约束：禁止每轮都注入）**

* 需要在循环中**反复提醒**的内容（进度要求、纪律提示、阶段性约束），一律挂在 `on_loop_epoch` 的 `injection` 上，
  并且**必须配合 `interval: N`**——每隔 N 轮才注入一次，例如：

  ```yaml
  on_loop_epoch:
    - injection:
        content: "提醒：每完成一个步骤都要用 Memo 记录。"
        interval: 3                  # 每 3 轮才提醒一次
  ```

* **禁止在 `on_loop_epoch` 不写 `interval` / `delay` 直接 `injection`**：那等于每一轮、每次模型调用前都把
  同一段话塞进上下文，既挤占上下文又严重干扰任务执行。
* 如果某段提示确实"每一轮都必须存在"，说明它属于**系统的常驻约束**，应该放进 `on_build_system_prompt`，
  而不是在循环里重复注入。
* 只在第 N 轮注入一次（开局交底、中途某轮才提醒）用 `delay: N`。

**检查类动作的通用语义（重点：提示词才是它的产出）**

* 检查类动作——`tool_use_check`、`keyword_check`、`file_operation` 的 `read`/`exist_check`/`delete`、
  `command_run`、`skill_info`——只做两件事：**判断通过 / 不通过**，并把 `successed_prompt` / `failed_prompt`
  以 role=user 的提示消息注入回历史给模型看。
* 因此**不写提示词的检查等于白写**：条件不通过时既没有回打理由，也没有任何内容注入给模型。
  除「纯放行的闸门」外，检查类动作都应写出 `failed_prompt`（告诉模型“你漏了什么、该补什么”）。
* 各阶段「不通过」的后果不同，写提示词前先想清楚这个检查归谁管：

  | 阶段 | 不通过时的后果 | 提示词效果 |
  | --- | --- | --- |
  | `on_tool_calling` | 拦下本次工具调用的后续流程、继续循环 | 注入 `failed_prompt`，模型据此重来 |
  | `on_loop_end` | 未达 `loop_end_max_retry` 上限时整轮打回重试（系统另附一条「未满足结束循环条件，已自动打回」）| 注入 `failed_prompt`；**通过时 `successed_prompt` 不生效**（结束即静默放行）|
  | `on_input_received` | **不拦不挡，只做提示**（不决定循环能否结束）| 命中注入 `successed_prompt`，未命中注入 `failed_prompt` |

* 结论：挂在 `on_input_received` 上的检查**价值 100% 体现在提示词上**，只写检查条件、两个提示词都留空，
  是最典型的“写了但没用”的写法。

**退出期望 `expect` 的两种写法（重点：只对 `on_loop_end` 生效）**

* **不写 `expect` ＝ 期望成功（默认玩法）**：该检查条件**满足**才允许结束这一轮循环。
  绝大多数检查都属于这一类，所以 `on_loop_end` 里没写 `expect` 不是漏项，而是默认就按“期望成功”跑。
* **写 `expect: false`（等价于 `"fail"`）＝ 期望失败**：该条件**不满足**才算通过、才允许结束循环。
  用于“看到某现象就继续干、看不到才收工”的反向看门逻辑，例如“结束时草稿文件必须已被清理”。
* 注意事项：
  * `expect` **只对 `on_loop_end` 生效**，挂在其他阶段会被忽略；
  * 期望失败时，“条件满足”反而成了拦下循环的原因，所以此时的 `failed_prompt` 要写成
    “条件出现了，必须继续处理”的提示，而不是普通的“你漏了某步”。
* 典型写法（期望失败）：

  ```yaml
  on_loop_end:
    # 期望失败：草稿还没被删除（exist_check 仍成立）就继续干活，删掉了才允许收工
    - file_operation:
        action: exist_check
        path: agent_vm/output/draft.md
        expect: false
        failed_prompt: "草稿文件仍在，说明还没收尾，请处理干净后再结束。"
  ```

**in检查（`keyword_check`）的语义（重点）**

* 它检查的是**输入侧**：本批 `type=user` 的输入消息里有没有 `keyword`——不检查模型输出，也不检查文件。
* 输入 = 真人 / 传感器等 `type=user` 的消息（每批 1 条或多条）；钩子自己注入的提示消息（`workflow_hint`）、
  `on_loop_end` 的打回提示等系统注入**不会触发本阶段**，无需再靠 `type: user` 去排除它们。
* 命中即通过、未命中即不通过，但它**不拦截输入、不阻塞流程、不影响循环能否结束**，
  唯一作用是往历史里追加一条提示，用来做**输入分诊**：例如「只有用户提到『周报』时才引导周报流程」。
* 只在 `on_input_received` 上有意义：其他阶段拿不到本批输入，会**恒定判为「未命中」**并一直注入 `failed_prompt`。
* 典型写法（两个提示词都要有，命中与未命中都明确告诉模型该怎么做）：

  ```yaml
  on_input_received:
    # 输入分诊：用户提到「周报」才引导周报流程；没提到也要明确告诉模型别乱走流程
    - keyword_check:
        keyword: "周报"
        type: user
        successed_prompt: "用户要写周报：先列出数据来源与周期，再按模板生成。"
        failed_prompt: "本次输入与周报无关，不要生成周报，按用户真实诉求处理。"
  ```

**工具使用检查的语义（重点）**

* `name` 只能填**宿主机真实存在的原生工具**——工具集固定，只有下面这几个，模型正是用这些名字调用工具：

  `FileSystem`、`Bash`、`BrainStorm`、`Cron`、`CallMCP`、`Memo`、`Request`、`Search`、`Fetch`、`Task`、`KernelUpgrade`。

* **外部拓展工具（MCP）不是原生工具**，模型是通过原生工具 `CallMCP(server_name, tool_name, arguments)` 间接调用的。
  所以**要检查「是否用了某个 MCP 工具」，必须检查 `CallMCP` 的入参**，而不是把 MCP 工具名直接写进 `name`（那样永远匹配不到）：

  ```yaml
  - tool_use_check:
      name: "CallMCP"
      parameter_check:
        - tool_name: "chrome_navigate"   # 直接命中该 MCP 工具
        # - server_name: "chrome"       # 需要时再限定服务器
      failed_prompt: "结束前请先用 CallMCP 调用 chrome_navigate。"
  ```

* **skill 与 MCP 都必须真实存在于宿主机**才能被检查或注入：`skill_info.skills`、`search(route='mcp')` 等注入动作，
  以及上面的 `CallMCP` 参数检查，都只有在宿主机确实装了这个 skill / 配了这个 MCP 时才成立；
  不存在时注入会走 `failed_prompt`，`CallMCP` 也会直接报「不在配置里」。
  **因此写这些名字之前必须先用 `Search` 工具查证**（`route="skill"` / `route="mcp"` / `route="local"`），
  确认存在再写；搜不到就不写，不要凭印象编造技能名或 MCP 工具名。

* `parameter_check` 的匹配语义：拿**本轮实际调用 `name` 工具时的入参**逐项比对；一项内多个键需**同时**命中（值精确相等），
  多项之间为**或**——任一项命中即视为「用了且满足条件」。

**`@引用` 符号**（`injection.content` 内可直接使用）：
`@RULES`、`@INFO`、`@SOUL`、`@MEMORY`、`@SYS`、`@USERQUERY`、`@TASKSPACE`、`@PLAN`。

> `@PLAN` 展开为**当前会话最近一次 BrainStorm 落盘的总计划**（主干 Main 纲要 + 后台支线任务明细）。
> BrainStorm 每次被调用都会整体刷新这份计划；会话尚无计划时展开为「暂无 BrainStorm 计划」。

## 5. 校验脚本（格式 / 功能 / 关键词汇）

沙盒根目录内置自测脚本 `evals/validate.py`，做三重校验：

* **格式**：YAML 可解析；顶层为映射；`name` 与文件名一致；必填字段齐备。
* **关键词汇**：`hooks` 的每个阶段、每个动作都必须属于白名单；动作的必填参数齐备；
  `file_operation.action` 取值合法；`tool_use_check.name` 属于原生工具白名单（MCP 工具请走 `CallMCP`）；`@引用` 符号已登记。
* **功能**：`loop_end_max_retry` 为整数；`file_operation` 具备可用的 `path`；
  **检查类动作**（`tool_use_check`、`keyword_check`、`file_operation` 的 `read`/`exist_check`/`delete`、
  `command_run`）**漏写 `failed_prompt` 会判 warn**——这类检查不通过时不会有任何反馈注入给模型，等于白写
  （`command_run` 写了 `return_log` 时会回传命令输出，不在此列）。

```bash
cd /agent_vm/agentloop_workplace/<uuid>
uv run evals/validate.py
```

结论写入 `evals/outputs/validation.json`。**有 ❌（error）项一律不许提交合并**，⚠️（warn）项按需处理。

## 6. 提交合并

校验全绿后调用 `KernelUpgrade(action="merge", type="agentloop", target="uuid/{name}")` 申请合并审批（uuid 为沙盒目录名）。批准后系统会：
1. 把 `{name}.yaml` 拷贝到正式目录 `~/.purrcat/paradigms/`；
2. Git 提交版本记录。
合并前系统会**宿主侧重跑同一套校验**（防止篡改脚本），有错直接拒绝——所以务必先自查再申请。
"""


__all__ = ["generate_agentloop_guide"]
