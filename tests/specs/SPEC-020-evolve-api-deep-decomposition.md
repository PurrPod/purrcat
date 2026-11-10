# SPEC-020：Evolve 与 Config API 的深度拆解

## 背景

三处文件仍超过可维护阈值：`src/evolve/sensor/evaluator.py`（904 行）把子进程夹具、静态检查、运行时检查与报告编排混在一起；`src/evolve/skill/evaluator.py`（697 行）同时承载后台线程入口、Trigger 执行、单用例协程与报告渲染；`src/server/api/config.py`（677 行、约 40 个端点）把路由声明、参数校验、Sensor 进程治理与数据根迁移编排堆在同一文件。纯逻辑无法脱离子进程/模型/磁盘单独测试。

## 行为

- Sensor 体检拆为：`fixtures.py`（网关夹具、子进程环境与整树击杀）、`checks_static.py`（L0 静态契约）、`checks_runtime.py`（L1 协议夹具）、`evaluator.py`（后台入口、结果聚合、报告组装）。
- Skill 评测拆为：`runner.py`（Trigger 执行、单用例协程、并发聚合、盲测编排与落盘）、`report.py`（HTML 报告组装）、`evaluator.py`（后台线程入口与 `record_trace_meta`）。
- Config API 拆为：`config_validation.py`（ACP 端口 / 数据根 / 文件名 / JSON 读取 / registry 归一化）、`config_services.py`（Sensor 配置与运行时控制、数据根迁移、部署与磁盘维护编排）、`config.py`（路由声明与薄委托）。
- 所有既有私有入口（`_static_checks`、`_runtime_checks`、`_aggregate_results`、`_validate_acp_port`、`_validate_data_root`）在原名模块保留薄委托/别名，测试与调用方无需改动。
- 所有 HTTP 路由路径、方法、端点名、状态码、请求/响应字段与错误文案逐字不变；检查项顺序、报告 JSON/HTML 字段与失败文案逐字不变。

## 验收标准

- [ ] AC-1：Sensor 静态检查项 id 顺序、layer、字段集合与 detail 文案在拆分前后一致。
- [ ] AC-2：Sensor 报告块（分层 section 编号、未覆盖项、local source 追加条目）组装结果一致。
- [ ] AC-3：Skill Trigger 结果口径（应触发/反例/框架崩溃的 status 与 detail）与聚合统计一致。
- [ ] AC-4：Skill 盲测并发编排的迭代目录选择、`benchmark.json` / `eval_result.json` 字段与返回文案一致。
- [ ] AC-5：Config 校验分支（端口、数据根、文件名、JSON 读取、registry 归一化）状态码与文案一致。
- [ ] AC-6：`config.py` 路由表与 `docs/api` 记录保持一致，`test_api_routes_contract` 全绿。

## 非目标

- 不新增、删除或重命名任何 HTTP 接口。
- 不调整检查项顺序、并发错位间隔、超时、评分规则与报告文案。
- 不改变 Sensor/Skill 的落盘路径与后台通知文案。
- 不引入包内循环导入，不扩大公开导入面。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_evolve_sensor_checks.py` | AC-1、AC-2 |
| L0 | `tests/l0/test_evolve_skill_runner.py` | AC-3、AC-4 |
| L0 | `tests/l0/test_api_config_validation.py` | AC-5 |
| L1 | `tests/l1/test_api_routes_contract.py` | AC-6 |

## 风险与回滚

- 风险：夹具/检查函数搬到新模块后仍被按旧路径导入。以模块级别名与薄委托保留原名，新增身份/行为断言锁定。
- 风险：`config.py` 拆分时漏改某个路由的异常文案或状态码。以现有路由表契约 + 新校验用例锁定。
- 风险：Skill runner 与 report 互相导入形成环。report 只依赖 common/路径，runner 单向依赖 report。
- 回滚：按文件边界恢复单文件实现，新增测试可原样复用。
