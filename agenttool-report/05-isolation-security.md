# 第5章：隔离与安全

子 Agent 如果乱搞怎么办？Claude Code 设计了好几层防护。

## 5.1 权限过滤（Permission Filtering）

**代码位置：** `AgentTool.tsx` 的 `call` 函数开头

```typescript
const filteredAgents = filterDeniedAgents(
  agents, 
  appState.toolPermissionContext, 
  AGENT_TOOL_NAME
);
```

系统会检查用户的权限规则。比如用户设置了一条规则：
```
禁止 Agent(Explore)
```
那 Explore Agent 就直接被过滤掉了，根本到不了选择阶段。

## 5.2 工具权限控制（Tool Permissions）

每个 Agent 定义里可以配置可用的工具：

```typescript
// 只允许读文件
tools: ['Read', 'Glob', 'Grep']

// 或者反过来，禁止写文件
disallowedTools: ['Write', 'Edit', 'Bash(rm *)']
```

实现方式：`resolveAgentTools()` 函数根据 Agent 定义的
`tools`（白名单）和 `disallowedTools`（黑名单），
从完整的工具池中筛选出该 Agent 能用的工具。

## 5.3 隔离模式（Isolation）

### 5.3.1 Worktree 隔离

```typescript
isolation: "worktree"
```

当指定这个模式时，系统会：

1. **创建 git worktree**（Git 工作树）：
   ```typescript
   const worktreeInfo = await createAgentWorktree(selectedAgent.agentType);
   ```
   相当于把当前仓库"复制"一份到临时目录

2. **修改工作目录**：子 Agent 的所有操作都在 worktree 里

3. **结束后清理**：
   - 如果子 Agent **没有改任何文件** → 自动删除 worktree
   - 如果子 Agent **改了文件** → 保留 worktree，返回路径和分支名

```typescript
// 清理逻辑
if (headCommit) {
  // 检查是否有未提交的更改
  const hasUncommittedChanges = ...;
  if (!hasUncommittedChanges) {
    // 没改东西，删除 worktree
    await removeWorktree(worktreePath);
    return {};
  }
  // 改了东西，保留
  return { worktreePath, worktreeBranch };
}
```

### 5.3.2 远程隔离

```typescript
isolation: "remote"
```

（仅限 Anthropic 内部使用）
把 Agent 发射到一个远程 CCR 沙盒环境执行，
连网络都是隔离的。

### 5.3.3 目录覆盖

```typescript
cwd: "/some/specific/path"
```

指定工作目录，Agent 的所有文件操作都在这个目录下。

## 5.4 权限模式（Permission Mode）

Agent 可以有自己的权限模式：

```typescript
const agentPermissionMode = agentDefinition.permissionMode;
// 可能的值：'bubble'（冒泡到父终端）、'plan'（需审批）等
```

- **bubble**：权限提示冒泡到父 Agent 的终端，用户能看到并决定
- **plan**：Agent 只能提方案，不能执行
- **bypassPermissions**：跳过权限检查（信任模式）

注意：如果父 Agent 是 `bypassPermissions` 模式，
子 Agent 无法降级为更严格的模式——"管理员的孩子依然是管理员"。

## 5.5 内存安全

子 Agent 结束后，系统会清理：

```typescript
// 1. 杀死所有子进程
killShellTasksForAgent(agentId, ...);

// 2. 清理 MCP 连接
await mcpCleanup();

// 3. 释放文件缓存
agentToolUseContext.readFileState.clear();

// 4. 清理消息（防止内存泄漏）
initialMessages.length = 0;

// 5. 清理 TODO 列表
const { [agentId]: _removed, ...todos } = prev.todos;
```

**一句话：** 子 Agent 来过，但像没来过一样（除了它产生的结果）。

## 5.6 一层层的安全护盾

```
第1层：权限规则 → 能不能用这个 Agent？
第2层：Agent 定义 → 这个 Agent 能用哪些工具？
第3层：Worktree 隔离 → 在副本里改，不影响主仓库
第4层：权限模式 → bubble/plan/bypass
第5层：结束清理 → 杀进程、清缓存、释放内存
```

---

**👉 下一章：[第6章：Agent 的记忆系统](./06-memory.md)**
