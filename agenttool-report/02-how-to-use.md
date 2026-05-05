# 第2章：怎么用 AgentTool？

## 2.1 从模型的角度看

当 Claude Code（主 AI）想要派小弟干活时，它会调用 Agent 工具，传入一堆参数。这些参数定义在 `AgentTool.tsx` 的 schema 里。

## 2.2 输入参数全解

先看代码（`AgentTool.tsx` 约第 100-140 行）：

```typescript
const baseInputSchema = z.object({
  prompt: z.string(),                              // ★ 必填：任务描述
  subagent_type: z.string().optional(),             // Agent 类型（Explore/Plan 等）
  model: z.enum(['sonnet', 'opus', 'haiku']).optional(),  // 模型选择
  run_in_background: z.boolean().optional(),        // 是否后台运行
})

// 再加上多人协作参数
const multiAgentInputSchema = z.object({
  name: z.string().optional(),       // 给 Agent 起个名，方便发消息
  team_name: z.string().optional(),  // 团队名
  mode: permissionModeSchema().optional(),  // 权限模式
})

// 再加上隔离参数
const fullInputSchema = baseInputSchema.extend({
  isolation: z.enum(['worktree', 'remote']).optional(), // 隔离模式
  cwd: z.string().optional(),        // 工作目录
})
```

翻译成人话：

| 参数 | 类型 | 必填 | 说明 | 比喻 |
|------|------|------|------|------|
| `prompt` | string | ✅ | 告诉小弟做什么 | 任务工单 |
| `subagent_type` | string | ❌ | 选哪种小弟 | 选"搜索专员"还是"开发全栈" |
| `model` | "sonnet"\|"opus"\|"haiku" | ❌ | 指定用哪个脑子 | 给小弟配什么级别的电脑 |
| `run_in_background` | boolean | ❌ | 后台运行 | "干完了告诉我" |
| `name` | string | ❌ | 给小弟起名 | 方便喊他 |
| `team_name` | string | ❌ | 加入哪个团队 | 编入小组 |
| `mode` | string | ❌ | 权限模式 | "plan" = 只给计划，不改代码 |
| `isolation` | "worktree"\|"remote" | ❌ | 隔离模式 | 给小弟一个单独的房间干活 |
| `cwd` | string | ❌ | 工作目录 | 指定在哪个文件夹干活 |

## 2.3 输出结果

Agent 干完活后返回：

```typescript
// 后台运行 → 返回一个任务 ID，后续查结果
{ isAsync: true, status: 'async_launched', 
  agentId: 'xxx', description: '...', 
  outputFile: '/path/to/output' }

// 前台运行 → 返回完整结果
// （子 Agent 的所有输出消息都流回给主 Agent）
```

## 2.4 三种典型用法

### 用法1：前台派小弟

```
Agent(prompt: "帮我查一下 src/api 目录下有哪些路由")
```

主 Agent 会等小弟干完活、拿到结果，再继续。

### 用法2：后台派小弟（不阻塞）

```
Agent(
  prompt: "跑一遍测试看看有没有失败的",
  run_in_background: true
)
```

主 Agent 不等待，直接继续干别的。小弟干完了自动通知。

### 用法3：隔离干活

```
Agent(
  prompt: "重构这个模块",
  isolation: "worktree"
)
```

系统会自动创建一个 git worktree（相当于代码的"复印件"），
小弟在里面随便改，改坏了也不影响主仓库。

## 2.5 底层：输入校验

AgentTool 使用 **Zod** 这个库做参数校验。Zod 的作用是：

```typescript
// 定义"这个参数必须是字符串"
const mySchema = z.object({
  name: z.string()
})

// 校验：如果传入数字或对象，直接报错
mySchema.parse({ name: 123 })  // ❌ 抛出错误
mySchema.parse({ name: "hello" })  // ✅ 通过
```

每次主 AI 调用 AgentTool 时，系统会用 Zod schema 校验参数。
如果参数不对（比如 prompt 忘了写），工具会直接报错，
不会让子 Agent 白跑一趟。

---

**👉 下一章：[第3章：Agent 的一生](./03-lifecycle.md)**
