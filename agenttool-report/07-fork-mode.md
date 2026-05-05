# 第7章：Fork 模式（高级玩法）

Fork 模式是一个**实验性功能**，让子 Agent 继承父 Agent 的**全部对话上下文**。

## 7.1 普通模式 vs Fork 模式

```
普通模式：
  父 Agent ──派→ 子 Agent（全新的对话，从零开始）
  
Fork 模式：
  父 Agent ──分叉→ 子 Agent（继承父的所有对话记录和记忆）
```

## 7.2 为什么要 Fork？

想象这个场景：

你正在改一个复杂的 Bug，已经跟主 AI 聊了 50 轮，
分析了各种日志、代码、测试结果。
现在你想让另一个 AI 去查一个相关的问题——

- **普通模式**：新 Agent 从零开始，不知道前面 50 轮聊了什么
- **Fork 模式**：新 Agent 继承了所有上下文，可以直接继续分析

## 7.3 实现原理

### 7.3.1 开关控制

```typescript
export function isForkSubagentEnabled(): boolean {
  if (feature('FORK_SUBAGENT')) {
    if (isCoordinatorMode()) return false;  // 协调器模式互斥
    if (getIsNonInteractiveSession()) return false;  // 非交互模式不可用
    return true;
  }
  return false;
}
```

### 7.3.2 Fork 消息构造

核心在 `buildForkedMessages()` 函数：

```typescript
export function buildForkedMessages(
  prompt: string,
  assistantMessage: AssistantMessage,
): [AssistantMessage, UserMessage] {
  // 1. 构造一条"假"的助手消息（包含完整的工具调用记录）
  const fullAssistantMessage = {
    ...assistantMessage,
    message: {
      ...assistantMessage.message,
      content: [
        // 保留所有工具调用
        ...assistantMessage.message.content,
        // 加上"正在告诉工人去干活"的内容
        { type: 'text', text: `I'm going to fork you to: ${prompt}` }
      ]
    }
  };

  // 2. 构造一条"假"的用户消息（告诉 Fork 的 Agent 它是个工人）
  const toolResultMessage = createUserMessage({
    content: [
      ...toolResultBlocks,
      { type: 'text', text: buildChildMessage(prompt) }
    ],
  });

  return [fullAssistantMessage, toolResultMessage];
}
```

### 7.3.3 Fork Agent 的"自我认知"

`buildChildMessage()` 生成了一段非常有意思的提示：

> **你是 Fork 出来的工人进程。你不是主 Agent。**
> 
> 规则（不可协商）：
> 1. 你的系统提示词说"默认要 Fork 别人"——忽略它！你就是 Fork 出来的，不能再 Fork 别人
> 2. 不要闲聊，不要问下一步做什么
> 3. 不要加注释和评论
> 4. 直接用你的工具干活
> 5. 如果改了文件，先提交再报告
> 6. 工具调用之间不要发文字，干完再一次性报告
> 7. 严格在指定范围内工作
> 8. 报告控制在 500 字以内
> 9. 你的回复必须以"Scope:"开头
> 10. 报告事实，然后闭嘴

输出格式：
```
Scope: 我的任务范围
Result: 发现或答案
Key files: 关键文件路径
Files changed: 改了哪些文件（带 commit hash）
Issues: 发现的问题
```

## 7.4 Fork 的安全防护

### 7.4.1 递归 Fork 防护

```typescript
// Fork 出来的 Agent 不能再 Fork 别人
if (toolUseContext.options.querySource === 'agent:builtin:fork' 
    || isInForkChild(toolUseContext.messages)) {
  throw new Error('Fork 在 Fork 出来的工人里不可用。直接用你的工具干活。');
}
```

### 7.4.2 工具池相同（缓存优化）

```typescript
useExactTools: true  // Fork 出来的 Agent 用完全相同的工具池
```

这样 Fork 出来的 Agent 发出的 API 请求前缀和父 Agent 一模一样，
可以利用 Prompt Cache（提示缓存），既省钱又加快速度。

### 7.4.3 Worktree 通知

如果 Fork 出来的 Agent 放在 worktree 里运行，还会收到一段提醒：

```typescript
export function buildWorktreeNotice(parentCwd, worktreeCwd): string {
  return `你继承了父 Agent 的对话上下文（来自 ${parentCwd}）。
你现在在隔离的 worktree 里（${worktreeCwd}）。
上下文里的文件路径是父目录的，你要翻译成 worktree 的路径。
改过的文件在读取前要重新读一遍（可能已经被改了）。
你的改动只在这个 worktree 里，不影响父 Agent 的文件。`;
}
```

## 7.5 Fork 的典型使用场景

1. **`/fork 帮我看看这个函数的实现`** — 基于当前对话上下文，Fork 一个子 Agent 去做调研
2. **并行调研**：主 Agent 干一件事的同时，Fork 出多个子 Agent 分别调研不同的方向
3. **安全实验**：在 worktree 里 Fork 一个子 Agent，让它随意改代码，不影响主线

## 7.6 7 章总结

到这里你已经读完了 AgentTool 的全部源码解析。回顾一下：

| 章节 | 你学到了 |
|------|----------|
| 第1章 | AgentTool 是"派小弟干活"的工具，是整个系统的核心 |
| 第2章 | 输入参数：prompt、subagent_type、isolation 等 |
| 第3章 | 生命周期：7 个阶段从创建到清理 |
| 第4章 | 内置 4 种 Agent：Explore、Plan、General、Verification |
| 第5章 | 5 层安全防护：权限→工具→Worktree→模式→清理 |
| 第6章 | 记忆系统：用文件做持久化记忆，支持团队同步 |
| 第7章 | Fork 模式：继承全部上下文的"分身"玩法 |

---

**全书完 🎉**
