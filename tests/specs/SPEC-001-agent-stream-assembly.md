# SPEC-001：Agent 流式拼装与工具链完整性

## 背景

主模型支持流式返回：思考增量、正文与工具调用参数会分散在多个 chunk 中。
同时 `assistant.tool_calls` 必须始终有配对的 `tool` 响应，否则下一次请求会被
上游以 400 拒绝。这两条路径过去只靠人工联调，缺少可重复的回归用例。

## 行为

1. 流式分片按 `index` 归并工具调用，`name` 与 `arguments` 可跨 chunk 拼接。
2. `reasoning_content` 只用于实时透出，流结束后清空，不写入 history。
3. 流式链路异常时回退一次非流式请求；用户打断（`InterruptedError`）不回退。
4. 工具链断裂时，弹出悬空的 assistant 之后的所有消息；assistant 有正文则保留
   正文并摘除 `tool_calls`，无正文则整条移除。

## 验收标准

- [x] AC-1：跨 chunk 的工具名与参数能拼成完整调用，并按 index 排序。
- [x] AC-2：usage 末帧被正确取到，返回给上层记账。
- [x] AC-3：流式失败只回退一次非流式，且回退后返回兜底消息。
- [x] AC-4：`InterruptedError` 不触发回退，直接上抛。
- [x] AC-5：完整工具链保持原样；缺失/多余响应都会清理到可重试状态。

## 非目标

- 不验证真实模型输出质量。
- 不覆盖工具执行本身的副作用。

## 测试矩阵

| 层级 | 位置 | 覆盖 |
| --- | --- | --- |
| L1 | `tests/l1/test_agent_loop.py::test_consume_stream_*` | AC-1、AC-2 |
| L1 | `tests/l1/test_agent_loop.py::test_stream_failure_*` | AC-3 |
| L1 | `tests/l1/test_agent_loop.py::test_interrupt_*` | AC-4 |
| L1 | `tests/l1/test_agent_loop.py::test_*toolchain*` | AC-5 |

使用 `tests/support/fakes.py` 的 `FakeModel` 提供脚本化分片，不依赖网络和 API Key。
