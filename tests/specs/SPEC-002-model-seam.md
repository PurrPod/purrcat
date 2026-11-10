# SPEC-002：模型接缝与可注入 ChatModel

## 背景

`Agent.__init__` 硬编码 `AgentModel(self.session_id)`，测试只能绕过构造函数、用宿主桩调用未绑定方法（见 `tests/l1/test_agent_loop.py` 的 `StreamHost`）。这带来两个问题：

1. 模型调用是 Agent 与外部世界唯一的边界，却没有可替换的契约，测试替身与真实实现容易悄悄漂移；
2. 想对 Agent 做端到端编排测试，必须连真实 Key 与网络，无法在 L1 里跑。

因此把「Agent 需要模型提供什么」显式抽成协议，并允许注入。

## 行为

- 新增 `ChatModel` 协议，声明 Agent 依赖的模型能力：`chat`、`bind_task`、`unbind`。`vision` 是可选能力，Agent 继续用 `getattr(..., False)` 兼容读取，不进入必需契约。
- `Agent` 接受可选参数 `model`：传入时直接使用，不再构造 `AgentModel`；不传时行为与现在完全一致。
- 注入的模型同样会收到 `bind_task(session_id, "AgentMain")`，`Agent.stop()` 同样会调用它的 `unbind()`。
- 测试替身 `FakeModel` 补齐 `bind_task`、`unbind`，并与真实实现保持调用签名一致。

## 验收标准

- [x] AC-1：`ChatModel` 是 `runtime_checkable` 协议，至少包含 `chat`、`bind_task`、`unbind`。
- [x] AC-2：`FakeModel` 满足 `ChatModel`（`isinstance` 通过）。
- [x] AC-3：`Agent(model=...)` 使用注入模型，且不构造 `AgentModel`；注入模型收到 `bind_task`、`stop()` 时收到 `unbind`。
- [x] AC-4：不传 `model` 时仍构造并使用 `AgentModel`，既有调用方无需改动。
- [x] AC-5：`FakeModel.chat` 的必填参数与 `Model.chat` 一致，且覆盖 `Model.chat` 的全部参数名，防止签名漂移。

## 非目标

- 不改 `LLMClient`、`key_manager`、`usage_tracer` 的内部实现。
- 不引入依赖注入容器，不把所有协作者都改成可注入。
- 不改 Harness / 子 Agent 的模型获取方式，本次只覆盖 `Agent` 主循环。
- 不重构 `process_message` 等大函数（后续单独 spec）。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_model_seam.py` | AC-1、AC-2 |
| L1 | `tests/l1/test_agent_model_injection.py` | AC-3、AC-4 |
| L3 | `tests/l3/test_model_contract.py` | AC-5 |

## 风险与回滚

- `Agent` 构造函数新增关键字参数，默认值保持原行为，调用方无感。
- 协议只做结构化约束，不改变继承关系，`Model` / `AgentModel` 无需修改。
- 若注入模型缺少 `bind_task`/`unbind`，会在构造/停止时立刻报错——这是契约要求，不回退为静默兼容。
