# 第3章：Agent 的一生（从生到死）

这是全书最核心的一章。一个 Agent 从被创建到结束，经历了一系列复杂但精密的步骤。

## 3.1 总览：7 个阶段

```
① 接收命令 → ② 校验权限 → ③ 选择 Agent 类型
→ ④ 组装环境 → ⑤ 启动对话 → ⑥ 执行任务
→ ⑦ 清理收尾
```

## 3.2 第一阶段：接收命令（call 函数）

当主 AI 调用 AgentTool 时，会触发 `AgentTool.tsx` 中的 `call` 函数。

```typescript
async call({ prompt, subagent_type, model, run_in_background, ... }, 
            toolUseContext, canUseTool, assistantMessage, onProgress?) {
```

这个函数接收所有参数（我们第 2 章讲的那些），然后进入第二阶段。

## 3.3 第二阶段：权限校验

### 3.3.1 检查 Agent 是否被禁止

```typescript
// 过滤掉被权限规则禁止的 Agent
const filteredAgents = filterDeniedAgents(
  agents, 
  appState.toolPermissionContext, 
  AGENT_TOOL_NAME
);
```

打个比方：公司规定"实习生不能使用生产服务器"。
如果当前上下文不允许使用某个 Agent 类型，系统会直接拒绝。

### 3.3.2 检查团队功能

```typescript
if (team_name && !isAgentSwarmsEnabled()) {
  throw new Error('Agent Teams is not yet available on your plan.');
}
```

如果用户传了 `team_name` 但没有团队功能权限，直接报错。

### 3.3.3 检查 MCP 服务器就绪

如果 Agent 需要特定的 MCP 服务器（比如需要连数据库），
系统会等 MCP 服务器连上了才开始，最多等 30 秒：

```typescript
const MAX_WAIT_MS = 30_000;  // 最多等 30 秒
const POLL_INTERVAL_MS = 500; // 每 500ms 检查一次
```

## 3.4 第三阶段：选择 Agent 类型

这是最关键的分支逻辑。代码里大概长这样：

```
用户传了 subagent_type 吗？
├── 没传 + Fork 实验开启 → 走 Fork 路径（继承全部上下文）
├── 没传 + Fork 没开启 → 用默认的 GeneralPurpose Agent
└── 传了 → 从已注册的 Agent 列表里找匹配的
         ├── 找到了 → 用这个 Agent 定义
         ├── 被权限禁止 → 报错 "XXX 被管理员禁止"
         └── 找不到 → 报错 "没有这个 Agent 类型"
```

### 3.4.1 Agent 的"简历"（AgentDefinition）

每个 Agent 都是一份"简历"，定义了它是什么、能做什么：

```typescript
interface AgentDefinition {
  agentType: string;       // 名字，如 "Explore"
  whenToUse: string;       // 什么时候用它
  tools?: string[];        // 允许使用的工具列表
  disallowedTools?: string[];  // 禁止使用的工具
  model?: string;          // 用什么模型
  getSystemPrompt: () => string;  // 系统提示词
  maxTurns?: number;       // 最大对话轮数
  permissionMode?: string; // 权限模式
  source: string;          // 来源（内置/自定义/插件）
  ...
}
```

### 3.4.2 从哪里加载 Agent？

答案在 `loadAgentsDir.ts` 里。Agent 可以来自：

| 来源 | 文件位置 | 优先级 |
|------|----------|--------|
| 命令行参数 | `--agent` 参数 | 🔺 最高 |
| 用户配置 | `~/.claude/agents/` | 🔺 |
| 项目配置 | `.claude/agents/` | 🟡 |
| 本地配置 | `.claude/agents-local/` | 🟡 |
| 策略配置 | 企业管理员配置 | 🔺 |
| 插件 | 插件注册 | 🟢 |
| 内置 | 写死在代码里 | 🟢 |

**优先级规则**：如果同一个 Agent 名字在不同来源都有定义，
优先级高的覆盖优先级低的。

## 3.5 第四阶段：组装环境

选好 Agent 类型后，系统开始为它"搭建工作台"：

### 3.5.1 组装提示词（System Prompt）

```typescript
// 获取 Agent 自己的 system prompt
const agentPrompt = selectedAgent.getSystemPrompt({ toolUseContext });

// 加上环境信息（当前目录、操作系统等）
const enhancedSystemPrompt = await enhanceSystemPromptWithEnvDetails(
  [agentPrompt], resolvedAgentModel, additionalWorkingDirectories
);
```

### 3.5.2 组装工具集（Tool Pool）

```typescript
// 根据 Agent 定义的 allowed/disallowed tools 过滤
const { resolvedTools } = resolveAgentTools(
  agentDefinition, 
  availableTools, 
  isAsync
);
```

比如 Explore Agent 禁止了文件编辑工具，那它的工具集里就没有 EditTool。

### 3.5.3 组装 MCP 服务器

Agent 可以自带 MCP 服务器（在它的定义文件里声明）：

```typescript
// 初始化 Agent 专属的 MCP 连接
const { clients, tools, cleanup } = await initializeAgentMcpServers(
  agentDefinition, parentClients
);
```

这些 MCP 连接在 Agent 结束后会自动清理，不会"污染"主环境。

### 3.5.4 创建子上下文（Subagent Context）

```typescript
const agentToolUseContext = createSubagentContext(toolUseContext, {
  options: agentOptions,   // 新工具集
  agentId,                 // 唯一的 Agent ID
  messages: initialMessages,  // 初始消息
  abortController,         // 取消控制器
  ...
});
```

这个 `createSubagentContext` 非常巧妙——它**克隆**了父 Agent 的上下文，
但替换了其中的工具集、消息列表、权限模式等，
让子 Agent 感觉自己是一个独立的主 Agent。

## 3.6 第五阶段：启动对话（query 循环）

这是最精彩的部分！子 Agent 会有自己的"对话循环"：

```typescript
for await (const message of query({
  messages: initialMessages,   // 初始消息
  systemPrompt: agentSystemPrompt,  // 系统提示词
  userContext: resolvedUserContext,  // 用户上下文
  systemContext: resolvedSystemContext,  // 系统上下文
  canUseTool,
  toolUseContext: agentToolUseContext,
  querySource,
  maxTurns: maxTurns ?? agentDefinition.maxTurns,  // 最大轮数
})) {
  // 处理每一条消息
  if (isRecordableMessage(message)) {
    // 记录到"侧链转录"（sidechain transcript）
    await recordSidechainTranscript([message], agentId, lastRecordedUuid);
    yield message;  // 把消息传给父 Agent
  }
}
```

**等等，"侧链转录"是什么？**

主 Agent 的对话记录叫"主链"。子 Agent 的对话记录叫"侧链"。
它们分开存储，互不干扰。这样：

- 子 Agent 的对话不会污染主 Agent 的上下文
- 子 Agent 结束可以恢复（resume）
- 用户可以查看子 Agent 完整的工作记录

### 前台 vs 后台的差异

| 特性 | 前台（Sync） | 后台（Async） |
|------|-------------|---------------|
| 主 Agent 等不等 | 等 | 不等 |
| 共享取消控制器 | 共享 | 独立 |
| 显示进度 | 实时流式显示 | 完成后通知 |
| 权限提示 | 可以向用户询问 | 自动决策 |
| 使用场景 | 需要结果才能继续 | 独立任务 |

## 3.7 第六阶段：执行任务

子 Agent 开始干活了。它有自己的工具、自己的对话历史，
看起来就像是一个全新的 Claude Code 实例。

**关键点**：子 Agent 完全不知道自己是被另一个 AI 派出来的
（除非走 Fork 路径，它会知道自己是个"工人进程"）。

## 3.8 第七阶段：清理收尾

Agent 结束后，无论成功还是失败，都会执行清理：

```typescript
finally {
  await mcpCleanup();                    // 清理 MCP 连接
  clearSessionHooks(rootSetAppState, agentId);  // 清理钩子
  cleanupAgentTracking(agentId);         // 清理缓存追踪
  agentToolUseContext.readFileState.clear();  // 释放内存
  initialMessages.length = 0;            // 释放消息
  unregisterPerfettoAgent(agentId);      // 取消性能追踪
  killShellTasksForAgent(...);           // 杀掉残留的 shell 进程
}
```

**为什么需要这么彻底的清理？**

如果一个 Agent 在后台启动了一个 `while true` 循环，
不清理的话那个进程就变成"孤儿进程"永远挂在系统里。
Claude Code 一个会话可能产生上百个子 Agent，
不清理的话资源会泄漏殆尽。

## 3.9 流程图总结

```
主 AI 想派小弟干活
       │
       ▼
   AgentTool.call({prompt, ...})
       │
       ▼
   校验权限 → 检查 Agent 是否被禁止
       │
       ▼
   选择 Agent 类型 → 查找到对应的 AgentDefinition
       │
       ▼
   组装环境 → 提示词 + 工具集 + MCP + 权限
       │
       ▼
   创建子上下文 → clone 父上下文并替换关键部分
       │
       ▼
   启动对话循环 → query() 流式输出
       │
       ▼
   子 Agent 用自己的工具干活
       │
       ▼
   结束 → 清理所有资源
```

---

**👉 下一章：[第4章：内置 Agent 们](./04-builtin-agents.md)**
