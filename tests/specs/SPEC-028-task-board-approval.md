# SPEC-028：任务看板精简与人工审核批准

## 背景

任务页此前默认展示图里的全部节点，且「看板」入口承载自定义 iframe 看板配置。实际使用中大多数节点（system、appender 等）对观察进度没有价值；人工审核节点缺少可直接操作的批准入口，批准状态也无法在刷新后回显。

## 行为

- 任务页默认进入「简图」：只渲染 `agent_loop` 与 `human_intervention` 两类节点；可见节点之间按全图拓扑先后顺序串联，不要求原始边直连。
- 当简图只剩一个 `agent_loop` 节点时整张图退化为 worker 形态，两种视图都不画节点图：
  - 简图：会话只保留 `role=user` 且 `type=workflow_input` 的输入气泡，以及 assistant / tool 的执行过程；
  - 详情：展示所有 `type` 的消息卡片（含 `system_input`、`workflow_hint` 等）。
- assistant 正文使用一个气泡；工具调用与工具结果使用独立折叠块，不再在折叠块外再套一层消息气泡。
- worker 视图底部保留指令输入框：Enter 发送（Shift+Enter 换行），调用 `POST /api/tasks/{task_id}/push` 向当前 Agent 节点注入指令，不删除输入区。
- `human_intervention` 节点与普通节点同样式渲染，但不提供重置/日志按钮，只保留「批准」按钮：`waiting` 时可点击，批准后按钮变为绿色「✓ 已批准」并禁用。
- 点击「批准」调用 `POST /api/tasks/{task_id}/nodes/{node_id}/approve`，后端落盘 `nodes/{node_id}/approval.json` 后再返回，刷新后从 `GET /state` 的 `node_approvals` 回显已批准状态。
- 节点被重置回 `ready` 时清除其批准记录，按钮恢复为待审核状态。
- 顶部按钮由「看板」改为「详情」，在简图与完整节点视图之间切换；完整视图下按钮显示「简图」。
- 删除自定义看板功能：任务页不再读取 `graph.dashboard`、不再渲染 iframe 看板；图编辑器移除看板配置入口与 `dashboard` 字段的读写。

## 验收标准

- [ ] AC-1：简图只出现 Agent 与人工审核节点，且可见节点按拓扑顺序连成先后链。
- [ ] AC-2：人工审核节点与普通节点同样式，仅有「批准」按钮；`waiting` 时可点击，批准后变为绿色「✓ 已批准」并禁用。
- [ ] AC-3：批准记录写入 checkpoint，刷新任务页后仍显示已批准。
- [ ] AC-4：重置节点后批准记录被清除。
- [ ] AC-5：「详情」按钮可切换完整视图，且不再出现看板入口/iframe。
- [ ] AC-6：图编辑器不再读写 `dashboard` 字段。
- [ ] AC-7：仅含一个 Agent 节点的图在简图下只展示 `workflow_input` 输入气泡与助手/工具过程，不渲染节点图；详情下展示全量类型消息卡片。
- [ ] AC-8：worker 视图始终提供指令输入框，发送后指令注入该 Agent 节点。

## 非目标

- 不改变人工审核节点的执行语义（仍通过注入指令放行）。
- 不新增审批人、审批意见或多人会签。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_task_node_approval.py` | AC-3 的落盘/回读/幂等/清理基础行为 |
| 手工 | 任务页与图编辑器 | AC-1、AC-2、AC-4、AC-5、AC-6、AC-7 |

## 风险与回滚

- 批准文件位于任务 checkpoint 目录，随任务删除而清理；不写入 `~/.purrcat` 其他位置。
- 若图编辑器仍打开旧草稿并保存，`dashboard` 字段会被丢弃，这是预期行为。
