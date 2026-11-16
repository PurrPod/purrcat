# SPEC-027：默认通用后台 Worker 图

## 背景

Task 工具派发任务时必须显式提供 `graph_name`，且系统没有一张通用后台 worker 图。主 Agent 在收到大量任务时缺少一个「默认容器」：先写 spec、再派发、由 worker 按 spec 执行并回写进度。

默认图应当是一张普通图，落在用户图目录 `~/.purrcat/graph/default/`，可被查看、编辑、覆盖或删除；随包只携带模板，启动时缺失才补齐。

## 行为

- 启动初始化（`ensure_initialized`）时调用 `ensure_default_graph`：`~/.purrcat/graph/default/graph.json` 不存在则从内置模板复制，已存在则绝不覆盖。
- `Task(action="add")` 未传 `graph_name` 时使用 `default`；传入未知图名仍然报错。
- `Task(action="list_graphs")` 直接扫描用户图目录，因此初始化后能看到 `default`；其 description 说明这是默认通用后台 worker，以及「spec 可选 → 有 spec 时 worker 读取并回写计划与进度，没有则直接按 prompt 执行 → 完成后自动通知」的派发约定。
- `default` 图的 `global_schema` 只有 `prompt` 一项，spec 路径不在 schema 中，只能作为 prompt 内容可选提供。
- `default` 图的系统提示词要求 worker：先判断 prompt 是否包含 spec 路径；有则完整读取、追加执行计划并持续回写进度、必要时复核；没有则直接按 prompt 执行、不自行创建 spec；两种情况下完成时都写 summary，且不自行轮询或等待派发方确认。

## 验收标准

- [ ] AC-1：启动初始化在 `GRAPHS_DIR/default/graph.json` 缺失时创建，已有文件不被覆盖。
- [ ] AC-2：未传 `graph_name` 的 `add` 使用 `default`，显式传 `default` 同样可用。
- [ ] AC-3：`default` 图节点类型均可实例化，边引用的节点都存在。
- [ ] AC-4：`default` 的 `global_schema` 只有 `prompt`。
- [ ] AC-5：`default` 的系统提示词包含 spec 读取、计划/进度回写、自动通知三类约束。

## 非目标

- 不实现 `Task.inspect`、运行中 `steer` 或节点 inbox。
- 不引入 git worktree 隔离，不改调度器与任务并发模型。
- 不在升级时覆盖用户修改过的 `default` 图。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_default_worker_graph.py` | AC-1 ~ AC-5 |

## 风险与回滚

- 模板位于 `src/harness/graph_templates/default/graph.json`，随包分发；模板缺失时初始化跳过并打印告警，不影响其他启动流程。
- 默认图落盘后即用户数据：删除该目录后重启即可重新生成；不要在代码里静默覆盖。
