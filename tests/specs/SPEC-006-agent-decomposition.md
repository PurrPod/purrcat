# SPEC-006：Agent 主循环与压缩逻辑的结构化拆分

## 背景

`Agent` 与 `SubAgentRunner` 各自内联了历史修复、流式拼装、工具参数注入、记忆压缩提示词与重试逻辑。行为正确但职责混杂，难以单测，也难以确认「消息顺序 / 压缩触发时机」这些关键不变量。

## 行为

- 历史消息的构造与修复（workflow_hint、system 事件、断裂 toolchain 清理）由 `agent/history.py` 的纯函数完成，输入输出与改造前一致。
- 流式分片拼装由 `agent/streaming.py` 完成：reasoning 增量、content 增量、tool_calls 按 index 合并并排序、usage 取最后一个非空分片。
- 工具参数解析（含 json_repair 兜底）、快照派发工具延后排序、系统参数注入由 `agent/tool_calls.py` 完成；参数对象不被原地修改。
- 记忆压缩的指令、警告文案、Memo 总结提取、最多 3 次重试与兜底文本由 `agent/compression.py` 统一；主/子 Agent 共用同一压缩指令与兜底文本，仅在警告文案与日志前缀上不同。
- 压缩后的历史：
  - 主 Agent = `[system 新提示词, system 事件(历史记忆总结)]`
  - 子 Agent = `[system 新提示词, 最近 N 条（安全截断点）, system 事件(历史记忆总结)]`，并清空 assistant 的 reasoning_content。
- `Agent.__init__` 允许注入 `model / hook_handler / tracker / memo`，缺省时行为与改造前相同。
- `process_message` 拆为 begin / loop / epoch / finish 阶段，阶段调用顺序、消息写入顺序、`turn_end` 发布时机不变。
- 工具执行仍保证：argument 损坏时写入错误 tool 响应且不派发；BrainStorm create 在该批工具末尾执行；人类打断时写入配对 tool 响应并终止后续工具。

## 验收标准

- [ ] AC-1：历史纯函数的结构与清理规则有 L0 用例。
- [ ] AC-2：流式拼装在 reasoning / content / 多工具分片 / usage 四种输入下与旧实现等价。
- [ ] AC-3：工具参数解析、排序、系统参数注入有 L0 用例，且不改写入参。
- [ ] AC-4：压缩重试、告警追加、兜底与主/子历史重建顺序有 L0 用例。
- [ ] AC-5：真实 `Agent`（替身模型）单轮输入的消息顺序为 `system → user → assistant`，工具批次的执行顺序与 tool 响应顺序一致。
- [ ] AC-6：Manager 的会话切换在锁内一次性更新 session_id / history / token，且删除会话同步清理目录与索引。

## 非目标

- 不改变 Agent Loop 的阶段名、钩子参数与上下文拼接顺序。
- 不改变压缩触发阈值与压缩发生时的模型调用参数。
- 不引入新的会话持久化格式。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_agent_history.py` | AC-1 |
| L0 | `tests/l0/test_agent_streaming.py` | AC-2 |
| L0 | `tests/l0/test_agent_tool_calls.py` | AC-3 |
| L0 | `tests/l0/test_agent_compression.py` | AC-4 |
| L0 | `tests/l0/test_agent_system_prompt.py` | 子代理提示词顺序 |
| L0 | `tests/l0/test_agent_manager_ops.py` | AC-6 |
| L1 | `tests/l1/test_agent_characterization.py` | AC-5 |
| L1 | `tests/l1/test_agent_loop.py` / `test_agent_model_injection.py` | 既有行为回归 |

## 风险与回滚

- 压缩与流式拼装是信息流转核心：任何字段丢失都会影响后续 LLM 调用，故先以 L0 锁纯函数、再用 L1 锁端到端顺序。
- 回滚方式：删除新增模块并恢复 `agent.py` / `sub_runner.py` 的内联实现；测试保留即可定位差异。
