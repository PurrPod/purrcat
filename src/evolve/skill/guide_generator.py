"""
Skill 指南生成器模块 (evolve/skill/guide_generator.py)
深度融合 agentskills.io 官方规范，为 Agent 提供详尽的创建、升级、测试专家级指导文档。
"""


def generate_create_guide(skill_name: str) -> str:
    return f"""# {skill_name} 创建指南 (How to Create)

从 0 到 1 构建 `{skill_name}`，请严格遵循 agentskills.io 规范：

## 1. 渐进式披露与目录结构 (Progressive Disclosure)
不要把所有内容塞进一个文件。Agent 会在启动时加载元数据，在触发时加载 SKILL.md，在需要时加载附件。
* `./SKILL.md`：(必须) 核心指令。必须保持在 500 行 / 5000 tokens 以内。
* `./scripts/`：(可选) 存放可复用的 Python/Bash 脚本。
* `./references/`：(可选) 存放供按需加载的 API 文档。必须在 SKILL.md 中明确说明何时加载（例："若 API 返回 400，请阅读 references/errors.md"）。
* `./assets/`：(可选) 存放静态模板或资源文件。
* `./evals/evals.json`：(必须) 测试用例配置。

## 2. SKILL.md 编写标准
顶部必须包含 YAML Frontmatter。
```yaml
---
name: {skill_name}
description: 必须在 1-1024 字符内。必须使用祈使句（如 "Extract text from..."）。描述用户意图而非底层实现。要预判用户的隐性需求（例如："即使他们没提 CSV 这个词，只要提到了表格数据处理也可使用"）。
compatibility: (可选) 例如 "Requires Python 3.14+ and uv"
---
```

## 3. 指令编写最佳实践 (Best Practices)

* **补充你所不知道的 (Add what agent lacks, omit what it knows)**：不要向自己解释什么是 HTTP 或什么是 PDF，专注在这个项目特定的业务逻辑、API Schema 和非直觉的边缘情况上。
* **预留 `## Gotchas` 章节**：记录那些违反直觉的环境特定陷阱（例如"本系统使用软删除，查询必须包含 `WHERE deleted_at IS NULL`"），这是 Skill 中最有价值的部分。
* **面向过程 (Favor procedures over declarations)**：不要说 "计算利润"，要写具体的 Checklist："1. 读取 schema.yaml, 2. Join 客户表, 3. 聚合输出"。
* **提供默认解 (Provide defaults, not menus)**：明确指出默认使用什么工具（例如："默认使用 pdfplumber。只有当它是扫描件时，才退回到 pdf2image"）。
* **模板化输出 (Templates for output format)**：如果要求特定输出，直接在文档里提供一段 Markdown/JSON 模板，Agent 擅长模式匹配。

## 4. 脚本开发红线 (Using Scripts in Skills)

* **严禁交互 (Avoid interactive prompts)**：脚本绝不能包含 `input()`。所有输入必须通过命令参数 (Flags, 比如 `--env staging`) 传入。
* **PEP 723 依赖内联 (Python)**：脚本应是自包含的。严禁 `pip install`，必须使用内联声明，沙盒会用 `uv run` 执行：
```python
# /// script
# dependencies = ["requests", "pandas"]
# ///
```

* **输出规范**：数据以结构化 (JSON/CSV) 格式输出到 `stdout`，诊断/进度/报错打印到 `stderr`。
* **提供 `--help`**：为脚本写好 argparse 和清晰的 `--help` 帮助文档。
"""


def generate_upgrade_guide(skill_name: str) -> str:
    return f"""# {skill_name} 升级与迭代指南 (How to Upgrade)

对 `{skill_name}` 进行维护和升级时，必须基于真实执行的反馈来优化，避免盲目猜测。

## 1. 诊断与反馈 (Diagnosing Root Causes)

分析以下信号：

* **用户的纠正 (User corrections)**：用户让你改用的库、让你注意的边缘情况。
* **人类反馈 (Human feedback)**：输出是否虽然技术正确但没抓住重点？
* **执行轨迹 (Execution traces)**：如果你在某一步反复报错、尝试多次才成功，说明那里的指令太模糊。

## 2. 优化法则 (Applying Improvement Principles)

* **避坑指南 (Gotchas)**：这是 Skill 中最有价值的部分！把你在执行中遇到的特定报错、数据库的软删除逻辑、字段命名不一致等"坑"，全部补充到 `## Gotchas` 章节。
* **从反馈中泛化 (Generalize from feedback)**：修复应面向根本问题，而不是为某个具体案例打狭窄的补丁。每次从错误中总结出通用规则，而非硬编码特例。
* **计划-验证-执行 (Plan-validate-execute)**：对于破坏性或批量操作，引入此模式。
  1. 生成中间计划 (`plan.json`)。
  2. 运行验证脚本 (`scripts/validate.py`) 对比数据源。
  3. 验证通过后才执行真实写入。
* **验证循环 (Validation loops)**：指示自己"做完后，运行脚本检查，失败则分析原因并重试，直到成功为止"。
* **合并脚本 (Bundling scripts)**：如果发现在多次测试/执行中你都在反复手写同样的解析逻辑，立刻将它提取到 `scripts/` 目录下作为一个通用脚本。
* **保持精简 (Keep it lean)**：规则不是越多越好。如果成功率停滞，尝试删除冗余的指令，讲清楚"Why"而不是死板地规定"How"。
* **重新评估 `description` 触发范围**：当技能功能发生变更时，必须检查 `SKILL.md` 的 `description` 字段是否会因过宽或过窄而导致误触发或漏触发。如有需要，按触发准确性测试流程进行验证和修正。
"""


def generate_test_guide(skill_name: str) -> str:
    return f"""# {skill_name} 质量测试指南 (How to Test & Evaluate)

修改代码后，必须完善 `evals/evals.json` 以驱动自动化盲测。

## 1. 隔离运行机制 (Spawning Runs)

反作弊警告：测试将在一个完全干净的沙盒中独立运行！

* 运行区会剔除本指南和 `evals/` 目录。
* 测试 Agent 绝对看不到预期的答案。必须确保 `SKILL.md` 里的信息足够让一个对当前任务一无所知的 Agent 独立完成任务。

## 2. 编写测试用例 (Designing Test Cases)

需要设计 2-3 个真实的用例，覆盖正常情况和边缘情况（例如缺失字段的表格）。

* `prompt`: 真实的、随意的用户语气，包含文件路径、上下文（例："我下载了个表格在 data.csv，里面有些邮箱是空的，帮我清理一下"）。
* `files`: 声明需要的测试文件路径，系统会自动挂载。
* `expected_output`: 总体成功标准的自然语言描述。
* `assertions` (核心！): 可用代码验证或肉眼直观判断的硬性断言。

## 3. 断言编写原则 (Writing Assertions)

断言决定了 QA 裁判的打分质量：

* 强断言 (Good): "输出文件必须是合法的 JSON"、"柱状图必须包含 X 轴标签"、"报告必须包含至少 3 条建议"。
* 弱断言 (Weak): "输出结果很好" (无法验证)、"完全包含某句特定的话" (太脆弱)。

## 4. 描述词触发测试 (Trigger Accuracy)

除了输出质量，还要确保 `SKILL.md` 里的 `description` 能被正确触发。

* 好的描述能包容用户的模糊意图 (Near-misses)。
* 描述过窄会导致该用时不触发，过宽会导致不需要时误触发。
* 确保 `description` 足够准确，系统后台会收集 `benchmark.json`，其中包含时间、Token 消耗和通过率 (Pass Rate)。
"""
