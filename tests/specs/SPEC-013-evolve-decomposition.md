# SPEC-013：Evolve 包拆解（六类工厂共用底座）

## 背景

`src/evolve/` 下 sensor / skill / mcp / graph / agentloop / ui_plugin 各自重复实现同一批基础能力：迭代目录分配、JSON 读写与容错解析、评分统计与裁判结果归一化、`GOAL.md`/`GUIDE.md` 落盘、校验结论汇总、Git 提交。评估器与工厂单体过大，纯逻辑（JSON 提取、评分聚合、目录命名、模板渲染）无法脱离子进程或模型调用单独测试。

## 行为

- 新增 `src/evolve/common/`：`parsing.py`（信封剥离、平衡 JSON 片段扫描、宽松解析、裁判 JSON 提取）、`scoring.py`（统计、用例计数、裁判结果归一化）、`paths.py`（`iteration-N` 发现与分配）、`report.py`（JSON/HTML 读写、时间戳）、`names.py`（文件名安全校验）、`validation.py`（校验报告结论）、`templates.py`（GOAL/GUIDE/自测脚本落盘）、`git.py`（初始化与提交）。
- 各 `evaluator.py` 保留原有公开函数名，内部按「输入收集 → 评估项构造 → 执行 → 聚合 → 报告」拆为小函数；`guide_generator.py` 保留原有 `generate_*` 函数，模板正文移入同一包的 `prompts.py`。
- 提示词、指南、骨架、HTML/脚本模板逐字不变；迭代目录名、报告文件名（`report.html`）、JSON 字段与缩进、评分与结论文案不变。
- Graph / AgentLoop 校验器仍是可被逐字拷贝到沙盒的独立脚本，不引入包内相对导入。

## 验收标准

- [ ] AC-1：JSON 解析与裁判结果归一化对信封、代码围栏、散文片段、双重编码、不可解析文本的行为与重构前一致。
- [ ] AC-2：评分统计、传感器用例汇总、Skill 并发结果聚合与重构前一致。
- [ ] AC-3：`iteration-N` 分配、复代规则与 `report.html` 命名一致。
- [ ] AC-4：六类指南、Skill 评估提示词、Sensor/MCP/UI 脚手架输出哈希不变。
- [ ] AC-5：Graph / AgentLoop 文档与文件夹校验结论不变。
- [ ] AC-6：原有 `src.evolve` 公开导入面（`__init__`、`__all__`）不变，L0/L1 全绿。

## 非目标

- 不改变任何自进化类型的评估维度、打分规则、提示词内容与拼接顺序。
- 不改变文件落盘路径、JSON 结构与后台线程/通知文案。
- 不拆分必须逐字独立运行的 Graph / AgentLoop 校验脚本。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_evolve_common.py` | AC-1、AC-2、AC-3 |
| L0 | `tests/l0/test_evolve_eval.py` | AC-1、AC-2 |
| L0 | `tests/l0/test_evolve_prompts.py` | AC-4 |
| L0 | `tests/l0/test_evolve_validators.py` | AC-5 |
| L0/L1 | 现有全套 | AC-6 |

## 风险与回滚

- 风险集中在模板搬运：任何空格、换行、花括号转义变化都会改变生成文件；用哈希测试逐字锁定。
- 私有函数名（如 `_extract_eval_json`、`_calculate_stats`、`_get_next_iteration_dir`）保留薄委托，避免外部脚本或临时测试断裂。
- 若某类工厂出现行为差异，可单独回滚该类对 `common` 的调用，保留新模块不影响其它类型。
