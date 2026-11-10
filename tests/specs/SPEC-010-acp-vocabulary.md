# SPEC-010：ACP 词汇翻译与 RPC 分发分离

## 背景

`server/acp/dispatch.py` 同时处理 JSON-RPC 分发、文件上传和「内部事件 → ACP 词汇」翻译。翻译规则与传输/分发无关，却被绑在一个 600 行文件里。

## 行为

- 工具语义映射移入 `server/acp/tool_vocab.py`：ToolKind 选择、标题摘要、locations、rawInput 预算、vision 文本提取。
- 事件翻译移入 `server/acp/updates.py`：`to_updates` 仍是唯一实现，输出结构与改造前一致。
- `dispatch.py` 保留 `handle_rpc`、`save_inbound_file` 与常量，并从 `updates` 导出 `to_updates`，既有导入路径不变。
- 工具调用仍输出三段：`tool_call(pending) → tool_call_update(in_progress) → tool_call_update(completed/failed)`。
- error metadata → failed；vision parts 只透出文本占位，不透出 base64。
- `turn_end` 仍先发 `session_info_update`，再返回 `stopReason`。

## 验收标准

- [ ] AC-1：ToolKind、标题、locations、rawInput 预算、vision 文本提取有 L0 用例。
- [ ] AC-2：agent_message / tool_call / usage / turn_end 的输出结构有 L0 用例。
- [ ] AC-3：vision 结果与 error 结果的 status/内容处理有 L0 用例。
- [ ] AC-4：`sensor/bridge.py` 与 `server/api/acp.py` 的导入路径保持可用。

## 非目标

- 不改变 ACP 方法名、JSON-RPC 错误码与 SSE/stdio 传输方式。
- 不新增 ACP 词汇。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_acp_updates.py` | AC-1 ~ AC-3 |
| L3 | 静态导入检查 | AC-4 |

## 风险与回滚

- 翻译模块被两条传输共用，任何字段变化都会影响编辑器渲染：先锁结构再拆文件。
- 回滚方式：把两个模块并回 `dispatch.py`；测试保留。
