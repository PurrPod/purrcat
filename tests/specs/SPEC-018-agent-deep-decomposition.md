# SPEC-018：src/agent 深层拆分（保持运行时序不变）

## 背景

`agent.py`、`hook_handler.py`、`session_store.py` 单文件承载了过多职责：主循环编排、
流式拼装、工具批次执行、记忆压缩、Hook 配置/引用/路径解析、会话目录与索引维护混在
一起，既难做纯逻辑测试，也让改动容易误伤消息顺序。需要在**不改变任何运行时行为**的
前提下按职责拆分，便于后续 TDD。

## 行为

拆分后对外行为完全不变，尤其是：

- 主 Agent 消息顺序：`on_loop_epoch` → 模型调用 → assistant 落盘 →
  `on_tool_calling`/工具执行 → `on_loop_end` → 打回提示。
- 工具批次顺序：同批工具按原顺序执行，BrainStorm(create) 延后到批次末尾；人类打断时
  仍写入配对的 tool 响应并终止后续工具。
- 压缩重建顺序：`[system 新提示, system_event(总结)]`。
- Hook 的 @引用单次左到右展开；`/agent_vm` 与 `agent_vm` 路径映射保持现有语义，
  相似前缀（如 `agent_vm_backup`）不误判。
- 会话切换/新建/分支的原子操作与保存时机不变。

`Agent`、`HookHandler`、`SessionStore` 的公开方法名与参数保持不变，内部只做薄委托。

## 验收标准

- [ ] AC-1：`src/agent/agent.py` 按 epoch 消费、工具批次、记忆压缩、交互生命周期分层，
      原方法名保留并委托；主循环事件顺序由 `tests/l0/test_agent_turn_order.py` 锁定。
- [ ] AC-2：`hook_handler.py` 拆出 `hook_config.py` / `hook_refs.py` / `hook_paths.py`，
      `tests/l0/test_hook_refs.py` 与 `tests/l0/test_sandbox_path.py` 保持全绿。
- [ ] AC-3：`session_store.py` 拆出 `session_layout.py`，公开静态方法签名不变；
      目录/索引/meta 行为由 `tests/l0/test_agent_session_store_layout.py` 锁定。
- [ ] AC-4：`uv run pytest -q tests/l0 tests/l1` 全绿且用例数不低于基线。

## 非目标

- 不重构 `manager.py` 与 `sub_runner.py` 的既有流程（仅在其明显混合职责且不增风险时
  才做小幅整理）。
- 不改变任何提示词文案、日志文案、状态机取值或 Bus 事件时序。
- 不新增功能，不为拆分引入无意义抽象。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_agent_hook_config.py` | AC-2 |
| L0 | `tests/l0/test_agent_session_store_layout.py` | AC-3 |
| L0 | `tests/l0/test_agent_turn_order.py` | AC-1 |
| L1 | `tests/l1/test_agent_characterization.py` | AC-1、AC-4 |
| L1 | `tests/l1/test_agent_loop.py` | AC-1、AC-4 |

## 风险与回滚

- 高风险路径：主循环消息顺序、工具链配对、压缩历史重建、Hook @引用展开。
- 回归手段：三个新 L0 用例 + 既有 L1 特征测试；出现分歧时以“先恢复原行为”为准，
  不允许放宽断言。
- 回滚：拆分模块均为新增文件，`Agent`/`HookHandler`/`SessionStore` 的委托行可逐一
  还原，不影响磁盘数据格式。
