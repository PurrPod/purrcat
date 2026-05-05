# 第4章：内置 Agent 们

Claude Code 自带了好几个"预制小弟"，
每个都有自己擅长的领域。它们在 `builtInAgents.ts` 里注册。

## 4.1 注册表（builtInAgents.ts）

```typescript
export function getBuiltInAgents(): AgentDefinition[] {
  const agents = [
    GENERAL_PURPOSE_AGENT,     // 通用型，啥都能干
    STATUSLINE_SETUP_AGENT,    // 状态栏设置
  ]

  if (areExplorePlanAgentsEnabled()) {
    agents.push(EXPLORE_AGENT, PLAN_AGENT);  // 探索和计划
  }

  // 非 SDK 模式下加入 "Claude Code 使用指南" Agent
  agents.push(CLAUDE_CODE_GUIDE_AGENT);

  if (verification实验开启) {
    agents.push(VERIFICATION_AGENT);  // 验证型
  }

  return agents;
}
```

其中 Explore 和 Plan 是 **实验性功能**，需要特性开关开启。

## 4.2 General Purpose Agent（通用型）

**文件：** `built-in/generalPurposeAgent.ts`

```typescript
agentType: 'general-purpose',
whenToUse: '用于研究复杂问题、搜索代码、执行多步骤任务',
tools: ['*'],  // 所有工具都能用
model: 未指定（使用默认模型）
```

它的系统提示词很简洁：

> "你是 Claude Code 的一个 Agent。用你的工具完成任务。  
> 完成时要给出简洁的报告——调用你的人会把结果转述给用户。"

**特点：**
- 全能型选手
- 没有禁用任何工具
- 没有固定模型（使用全局默认配置）

## 4.3 Explore Agent（探索型）

**文件：** `built-in/exploreAgent.ts`

```typescript
agentType: 'Explore',
disallowedTools: ['Agent', 'ExitPlanMode', 'FileEdit', 'FileWrite', 'NotebookEdit'],
model: 'haiku'  // 用最便宜的模型，追求速度
```

**特点：**
- 🚫 **只读！** 不能改任何文件
- 🚫 不能写文件、不能编辑、不能创建
- 🚫 不能派生其他的 Agent
- ✅ 只允许搜索（Glob、Grep）、读取（Read）、Bash（只读命令）
- ⚡ 默认用 Haiku 模型（便宜、快）
- 💰 **每秒省流量**：因为只读，不需要加载 CLAUDE.md 里的 git/commit 规则

它的系统提示词里有这么一段狠话：

> **关键：只读模式——禁止修改文件**
> 你严格禁止：创建文件、修改文件、删除文件、移动文件、在 /tmp 创建临时文件……

**使用场景：** "帮我找找所有用到了 useCallback 的文件"

## 4.4 Plan Agent（计划型）

**文件：** `built-in/planAgent.ts`

```typescript
agentType: 'Plan',
disallowedTools: 同 Explore（也是只读）
model: 'inherit'  // 继承父 Agent 的模型
```

**特点：**
- 同样是只读，但它的任务是**设计方案**而不是单纯搜索
- 要求输出格式化的计划：步骤、关键文件、依赖关系
- 用 `inherit` 模型（跟主 Agent 同一个级别的大脑）

它的系统提示词说：

> "你是一个软件架构师和计划专家。你的角色是探索代码库并设计方案。  
> 你不能改任何文件，只能看和计划。"

输出格式要求：
```
### 实施关键文件
- path/to/file1.ts
- path/to/file2.ts
```

**使用场景：** "帮我想想要重构这个模块，该怎么做"

## 4.5 Verification Agent（验证型）

**文件：** `built-in/verificationAgent.ts`

```typescript
agentType: 'verification',
color: 'red',    // 红色标识
background: true,  // 强制后台运行
disallowedTools: 同 Explore（不能改项目文件）
model: 'inherit'
```

**特点：**
- 🔴 **专门负责"挑刺"**——验证代码改对了没有
- 📢 **永远在后台运行**（不影响主 Agent 节奏）
- 🚫 不能修改项目文件，但**可以在 /tmp 写临时测试脚本**
- 输出格式严格：必须有 `VERDICT: PASS/FAIL/PARTIAL`

它的系统提示词非常有趣：

> "你不是来确认代码能跑的——你是来搞破坏的。  
> 第一个 80% 很简单，你的全部价值在于找到最后那 20% 的坑。"

它还明确指出了两个常见的"验证失败"模式：
1. **验证回避**：读了一遍代码就说"没问题"，实际没跑任何命令
2. **被前 80% 迷惑**：界面看起来很漂亮就通过了，但一半按钮没反应

每个检查必须包含：
```
### Check: [在测什么]
**Command run:** [执行的命令]
**Output observed:** [实际输出]
**Result: PASS** (或 FAIL)
```

**使用场景：** 改完代码后自动验证，"帮我看看这次的改动有没有问题"

## 4.6 自定义 Agent（补充）

除了内置的，用户还可以自己写 Agent！`loadAgentsDir.ts` 负责加载。

Agent 定义可以是：
1. **Markdown 文件**（`.claude/agents/*.md`），用 frontmatter 写配置
2. **JSON 文件**（`.claude/agents/*.json`），纯 JSON 格式

Markdown 示例：
```markdown
---
agentType: my-custom-agent
whenToUse: 专门用来处理图片
tools:
  - Read
  - Bash
disallowedTools:
  - Write
model: sonnet
---

你是我的图片处理专家。你可以读取图片文件，用 Bash 调用 ImageMagick，
但你不能修改任何文件。
```

## 4.7 对比总结

| Agent | 只读？ | 可写文件？ | 能用其他Agent？ | 默认模型 | 后台？ |
|-------|--------|-----------|----------------|---------|-------|
| General | ❌ | ✅ | ✅ | 默认 | 可选 |
| Explore | ✅ | ❌ | ❌ | Haiku（快） | 可选 |
| Plan | ✅ | ❌ | ❌ | Inherit（继承） | 可选 |
| Verification | ✅ | ❌ 项目文件 / ✅ /tmp | ❌ | Inherit | ✅ 强制 |

---

**👉 下一章：[第5章：隔离与安全](./05-isolation-security.md)**
