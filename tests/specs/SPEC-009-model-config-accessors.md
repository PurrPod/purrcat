# SPEC-009：模型配置读取的统一入口

## 背景

`main.<model>` 的读取散落在 Agent、SubAgent、Manager、ModelFacade，`max_token` 默认值 500000 被重复硬编码，API Key 选择逻辑在初始化与热重载中各写一遍。

## 行为

- `utils/config.py` 新增：
  - `get_main_model_config(model_name=None)`：按名取配置；不传名取 main 下第一个模型；结构异常返回 `{}`。
  - `get_model_max_token(model_name=None, default=500000)`：非整数或缺失时回落到 default。
- `AgentModel` 的 API Key 选择为：`api_key` 优先，否则取 `api_keys` 中第一个非空字符串；初始化与重载共用同一实现。
- `vision` 开关与 base_url 的读取行为不变。

## 验收标准

- [ ] AC-1：按名、默认名、缺失名、结构异常四种读取有 L0 用例。
- [ ] AC-2：`max_token` 的整数解析与默认回落有 L0 用例。
- [ ] AC-3：API Key 单选/列表/空列表选择规则有 L0 用例。
- [ ] AC-4：`apply_model_config` 正确写入 model_name/base_url/api_key/vision。

## 非目标

- 不改变 model.json 的字段结构。
- 不改变模型热重载的触发方式。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_config_model_accessors.py` | AC-1, AC-2 |
| L0 | `tests/l0/test_agent_model_config.py` | AC-3, AC-4 |
| L1 | `tests/l1/test_agent_model_injection.py` | 既有注入回归 |

## 风险与回滚

- 读取失败必须返回空字典而非抛异常，否则会在启动期放大成白屏。
- 回滚方式：恢复各处内联读取；新增访问器可保留。
