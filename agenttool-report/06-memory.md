# 第6章：Agent 的记忆系统

Agent 怎么能记住之前学到的东西？这就靠记忆系统了。

## 6.1 记忆的三种"范围"

代码在 `agentMemory.ts` 中定义：

```typescript
export type AgentMemoryScope = 'user' | 'project' | 'local';
```

| 范围 | 存储位置 | 说明 | 比喻 |
|------|----------|------|------|
| `user` | `~/.claude/agent-memory/` | 全局记忆，跨项目 | 你的"通用经验" |
| `project` | `.claude/agent-memory/` | 项目共享，会进版本控制 | 团队的"项目规范" |
| `local` | `.claude/agent-memory-local/` | 仅本地，不进版本控制 | 你私人的"小抄" |

## 6.2 记忆怎么存？

每个 Agent 类型有自己的记忆文件夹：

```
~/.claude/agent-memory/
└── Explore/          ← Agent 类型名
    └── MEMORY.md     ← 记忆文件
```

`MEMORY.md` 是一个 Markdown 文件，Agent 可以用 Write 工具修改它。
系统会在 Agent 启动时自动加载这个文件的内容，拼到系统提示词里。

## 6.3 记忆怎么加载？

```typescript
export function loadAgentMemoryPrompt(agentType: string, scope: AgentMemoryScope): string {
  const memoryDir = getAgentMemoryDir(agentType, scope);
  
  // 异步创建目录（不阻塞 Agent 启动）
  void ensureMemoryDirExists(memoryDir);
  
  // 构建记忆提示词
  return buildMemoryPrompt({
    displayName: 'Persistent Agent Memory',
    memoryDir,
    extraGuidelines: [scopeNote],
  });
}
```

在 Agent 的定义里启用记忆：

```yaml
---
memory: project  # 在 agent 的 frontmatter 里声明
---
```

这样每次 Agent 启动时，系统提示词里就会多一段：

```
## Persistent Agent Memory
以下是这个 Agent 之前记住的内容（位置：.claude/agent-memory/Explore/）：
[这里填 MEMORY.md 的内容]
```

## 6.4 记忆快照同步（agentMemorySnapshot.ts）

这是多人协作时的功能。想一想：

- 小明在项目里创建了一个 Agent 记忆
- 小明提交到了 Git
- 小红 pull 了代码
- 小红的 Agent 启动时检测到"快照更新了"

这就是 `agentMemorySnapshot.ts` 做的事情：

```typescript
export async function checkAgentMemorySnapshot(agentType, scope) {
  // 1. 检查项目里有没有 .claude/agent-memory-snapshots/{agentType}/
  const snapshotMeta = readJsonFile(getSnapshotJsonPath(agentType), schema);
  
  if (!snapshotMeta) return { action: 'none' };  // 没有快照
  
  // 2. 检查本地有没有记忆
  if (!hasLocalMemory) return { action: 'initialize', ... };  // 首次初始化
  
  // 3. 检查快照是否比本地新
  if (快照更新) return { action: 'prompt-update', ... };  // 需要更新
  
  return { action: 'none' };  // 已经是最新
}
```

三种结果：
| action | 含义 | 处理方式 |
|--------|------|----------|
| `none` | 不用做任何事 | — |
| `initialize` | 第一次初始化 | 复制快照到本地记忆目录 |
| `prompt-update` | 快照更新了 | 删除旧记忆，复制新快照 |

## 6.5 记忆系统的设计哲学

```
┌────────────────────────────────────────────────┐
│               Agent 启动时                        │
│                                                    │
│  1. 检查快照是否更新（团队共享）                      │
│  2. 如果有更新 → 同步到本地                          │
│  3. 加载本地记忆文件 → 注入系统提示词                  │
│  4. Agent 开始工作                                  │
│  5. Agent 在工作中可以读写 MEMORY.md（持续学习）       │
│  6. Agent 结束后 → 团队可以提交快照到 Git             │
└────────────────────────────────────────────────┘
```

**核心思想**：记忆 = 文件。Agent 能读写文件，所以 Agent 能读写自己的记忆。
不需要复杂的数据库，不需要 API，就是最简单的文件操作。

---

**👉 下一章：[第7章：Fork 模式](./07-fork-mode.md)**
