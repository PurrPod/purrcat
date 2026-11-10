# SPEC-003：工具注册契约

## 背景

工具涉及三份事实来源：`AGENT_TOOL_SCHEMA`（模型可见参数）、`TOOL_FUNC_MAP`（工具名 → 函数名）、真实工具函数签名。

三者**不应该相等**：模型只该看到它可以填的参数，而函数还可以有系统注入的隐藏参数（`session_id`、`_tool_call_id`、`_vision_mode` 等），由 Agent、Harness、dispatch 自动补齐。真正会出事故的是「不可调用」：

- schema 里暴露的工具名解析不到函数 → 模型每次调用都拿到错误；
- schema 声明了参数，函数既没有该形参也不收 `**kwargs` → 必然 `TypeError`；
- 函数有无默认值的必填参数，但既不在 schema 里、也没人注入 → 每次调用必失败。

## 行为

- 解析工具的逻辑收敛为一个函数 `resolve_tool(tool_name)`，`dispatch_tool` 与测试共用同一份真相，避免测试重写一套 importlib 规则。
- 系统注入的参数集合显式声明为 `SYSTEM_INJECTED_ARGUMENTS`，并保持冻结：新增注入点必须同步修改常量与测试。
- 进程隔离白名单保持当前四项，不得静默扩大（AGENTS 红线 5）。

## 验收标准

- [x] AC-1：`AGENT_TOOL_SCHEMA` 中每个工具名都能解析到可调用对象。
- [x] AC-2：`TOOL_FUNC_MAP` 与模型可见工具集合一致（注册了但模型看不到、或模型看得到但没注册，都算失败）。
- [x] AC-3：schema 的每个 property 都被函数接收：要么是显式形参，要么函数声明了 `**kwargs`。
- [x] AC-4：函数的每个无默认值参数都可被填充：在 schema properties 中，或属于系统注入白名单。
- [x] AC-5：`SYSTEM_INJECTED_ARGUMENTS` 与 `PROCESS_ISOLATED_TOOLS` 均被冻结断言，变更需显式改测试。

## 非目标

- 不要求 schema 参数与函数签名相等（系统注入是设计的一部分）。
- 不验证工具内部语义与外部依赖（网络、MCP、向量检索），这些按工具单独补测。
- 不修改任何工具实现，不改 `TOOL_FUNC_MAP` 的现有内容。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L3 | `tests/l3/test_tool_registry_contract.py` | AC-1 ~ AC-5 |

## 风险与回滚

- `resolve_tool` 是从 `dispatch_tool` 原样抽出的解析逻辑，行为不变，异常文案保持原样。
- 若未来允许「同一工具多个函数名」，需要扩展本契约，而不是放宽断言。
