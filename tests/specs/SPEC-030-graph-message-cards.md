# SPEC-030 Graph 消息卡片语义

## 背景

Graph 里的消息必须靠 `type` 区分来源：任务输入与系统提示都不再占用 `system` 角色（会破坏 KV Cache），
统一用 `role=user` + JSON 消息卡片表达。

## 行为

- `message_card_builder` 不再接受 `role` 输入，只接收 `content`；输出固定为
  `{"role": "user", "content": "{\"type\": \"workflow_input\", \"content\": ...}"}`。
- Graph 的 `agent_loop` 在 `on_build_system_prompt` 阶段的注入被包成
  `role=user`、`type=system_input` 的消息卡片，仍只在节点记忆为空时追加到上游输入末尾一次。
- 默认图 `default` 的系统提示词改由 `on_build_system_prompt` 注入；图内只保留「任务简报」一张卡片。
- 人工注入（`/api/tasks/{id}/push`）在 agent_loop 消费 `force_push` 时同样包成
  `role=user`、`type=workflow_input` 的卡片，内容保留 `[人工指令]` 前缀。

## 验收标准

- [ ] AC-1：`message_card_builder` 输出消息的 `role` 恒为 `user`，卡片 `type` 恒为 `workflow_input`。
- [ ] AC-2：向节点多传 `role` 不会改变输出角色。
- [ ] AC-3：Graph `on_build_system_prompt` 注入为 `role=user`、`type=system_input` 卡片。
- [ ] AC-4：人工注入指令进入记忆时为 `type=workflow_input` 卡片。

## 测试矩阵

| 层级 | 用例 | 覆盖 |
| --- | --- | --- |
| L0 | `tests/l0/test_message_card_builder.py` | AC-1、AC-2 |
| L0 | `tests/l0/test_default_worker_graph.py` | AC-3（默认图范式含 on_build_system_prompt）|
