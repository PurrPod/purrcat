# 第1章：AgentTool 是什么？

## 1.1 一句话说清楚

**AgentTool 就是"派小弟干活"的工具。**

想象你在写代码，突然老板说"帮我把项目的所有 API 端点列出来"。你可以：
- **自己干**：手动翻每个文件，一个一个找
- **派小弟**：叫另一个 AI 去帮你翻，翻完回来告诉你

AgentTool 就是"派小弟"这个操作。

## 1.2 它在哪？

在源码里位置：`src/tools/AgentTool/`

整个文件夹有 **15 个文件**，核心文件是：

```
AgentTool/
├── AgentTool.tsx          ← 主文件（233KB，最大！）
├── prompt.ts              ← 生成提示词（教模型怎么用这个工具）
├── runAgent.ts            ← 实际运行 Agent 的核心引擎
├── resumeAgent.ts         ← 恢复一个暂停的 Agent
├── forkSubagent.ts        ← Fork 模式（实验性功能）
├── agentMemory.ts         ← Agent 记忆管理
├── agentMemorySnapshot.ts ← 记忆快照同步
├── agentToolUtils.ts      ← 各种工具函数
├── agentDisplay.ts        ← 展示 Agent 信息
├── agentColorManager.ts   ← 给 Agent 分配颜色
├── loadAgentsDir.ts       ← 从目录加载自定义 Agent
├── builtInAgents.ts       ← 内置 Agent 注册表
├── built-in/              ← 内置 Agent 们
│   ├── exploreAgent.ts
│   ├── planAgent.ts
│   ├── generalPurposeAgent.ts
│   ├── verificationAgent.ts
│   └── claudeCodeGuideAgent.ts
├── constants.ts           ← 常量
└── UI.tsx                 ← 界面组件
```

## 1.3 为什么它这么重要？

**因为它是"AI 调用 AI"的桥梁。**

没有 AgentTool，Claude Code 只能自己一个一个干活。
有了 AgentTool，Claude Code 可以：

1. **并行干活**：同时派出多个 Agent 做不同的事
2. **分工协作**：让 Explore Agent 去搜索代码，Plan Agent 去做计划
3. **后台运行**：把耗时任务丢到后台，自己继续干活
4. **隔离执行**：让 Agent 在沙盒/独立目录里工作，不影响主环境

## 1.4 一张图看懂整体架构

```
┌─────────────────────────────────────────────────┐
│                  主 Agent (你)                     │
│  ┌──────────────────────────────────────────┐   │
│  │         AgentTool（派小弟工具）              │   │
│  │  输入：prompt, subagent_type, isolation等   │   │
│  └──────────────┬───────────────────────────┘   │
│                 │                                 │
│                 ▼                                 │
│  ┌──────────────────────────────────────────┐   │
│  │           runAgent.ts（运行引擎）           │   │
│  │  ┌──────────┐  ┌──────────┐              │   │
│  │  │ 组装提示词  │  │ 组装工具集  │              │   │
│  │  └──────────┘  └──────────┘              │   │
│  │  ┌──────────┐  ┌──────────┐              │   │
│  │  │ 调用query() │  │ 流式输出  │              │   │
│  │  └──────────┘  └──────────┘              │   │
│  └──────────────────────────────────────────┘   │
│                 │                                 │
│                 ▼                                 │
│  ┌──────────────────────────────────────────┐   │
│  │      子 Agent 运行（独立对话循环）            │   │
│  │  有自己的 system prompt、工具集、对话历史      │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## 1.5 它是怎么注册成工具的？

在 `AgentTool.tsx` 的末尾（第196行附近），有一行核心代码：

```typescript
export const AgentTool = buildTool({
  name: 'Agent',          // 工具名，模型通过这个名字调用它
  aliases: ['Task'],      // 曾用名，向后兼容
  searchHint: 'delegate work to a subagent',
  maxResultSizeChars: 100_000,  // 结果最大 10 万字符
  ...
})
```

`buildTool` 是 Claude Code 的工具工厂函数。所有工具（Bash、Read、Write 等）都是通过它注册的。AgentTool 只是其中之一，但它是**唯一一个能调用其他 AI 的工具**。

---

**👉 下一章：[第2章：怎么用？输入和输出拆解](./02-how-to-use.md)**
