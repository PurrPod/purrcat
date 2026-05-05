# AgentTool 源码深度剖析

> **面向读者：** 大一学生 / 编程初学者  
> **内容：** Claude Code 中最核心的工具——AgentTool（子 Agent 系统）  
> **目标：** 用大白话讲清楚"一个 AI 怎么派生出另一个 AI 来帮自己干活"

---

## 📚 报告目录

| 章节 | 文件名 | 内容 |
|------|--------|------|
| 第1章 | [01-intro.md](./01-intro.md) | AgentTool 是什么？为什么它是核心？ |
| 第2章 | [02-how-to-use.md](./02-how-to-use.md) | 怎么用 AgentTool？输入和输出拆解 |
| 第3章 | [03-lifecycle.md](./03-lifecycle.md) | Agent 的一生：从生到死经历了什么 |
| 第4章 | [04-builtin-agents.md](./04-builtin-agents.md) | 内置 Agent 们：Explore、Plan、General、Verification |
| 第5章 | [05-isolation-security.md](./05-isolation-security.md) | 隔离与安全：如何让子 Agent 不捣乱 |
| 第6章 | [06-memory.md](./06-memory.md) | Agent 的记忆系统：怎么学会记住东西 |
| 第7章 | [07-fork-mode.md](./07-fork-mode.md) | Fork 模式：高级玩法——继承全部记忆 |

---

**阅读建议：** 按顺序读，第1章先搞懂概念，第3章最核心。
