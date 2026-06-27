"""
Skill 指南生成器模块 (evolve/skill/guide_generator.py)
深度融合 agentskills.io 官方规范，为 Agent 提供详尽的创建、升级、测试专家级指导文档。
"""


def generate_create_guide(skill_name: str) -> str:
    return f"""# {skill_name} 创建指南 (How to Create)

从 0 到 1 构建 `{skill_name}`，请严格遵循 agentskills.io 规范：

## 1. 渐进式披露与目录结构 (Progressive Disclosure)
不要把所有内容塞进一个文件。系统会在启动时加载元数据，触发时加载 SKILL.md，需要时加载附件。
* `./SKILL.md`：(必须) 核心指令。必须保持在 500 行 / 5000 tokens 以内。
* `./scripts/`：(可选) 存放可复用的 Python/Bash 脚本。用于让使用者可以减少一些重复性操作，节省消耗。
* `./evals/evals.json`：(必须) 测试用例配置（包含激发测试 triggers 与质量盲测 evals）。

## 2. SKILL.md 编写标准与触发器 (Crucial for Triggering)
顶部必须包含 YAML Frontmatter。**其中 `description` 承担了技能是否能被调用的全部责任！**
```yaml
---
name: {skill_name}
description: 必须在 1-1024 字符内。
---
```

**编写 Description 的铁律 (Optimizing description):**

* **必须使用祈使句**：例如 "Use this skill when..." 或 "Analyze CSV files..."，告诉大模型什么时候采取行动。
* **关注用户意图，而非底层实现**：描述用户想要达成什么目标，而不是你的 Python 脚本用了什么库。
* **尽可能具有"侵略性" (Pushy)**：明确列出适用的边缘场景。例如："即使他们没显式提及 CSV 这个词，只要提到了表格数据处理也可使用"。

## 3. 指令编写最佳实践 (Best Practices)

* **面向过程 (Favor procedures over declarations)**：不要说 "计算利润"，要写具体的 Checklist："1. 读取 schema, 2. Join 客户表, 3. 聚合输出"。
* **提供默认解 (Provide defaults, not menus)**：明确指出默认使用什么工具。
* **模板化输出 (Templates for output format)**：如果要求特定输出，直接在文档里提供一段 Markdown/JSON 模板。
"""


def generate_upgrade_guide(skill_name: str) -> str:
    return f"""# {skill_name} 升级与迭代指南 (How to Upgrade)

对 `{skill_name}` 进行迭代时，必须基于 `benchmark.json` 的客观指标和 `trace.md` 的行为轨迹来进行调优 (Eval-driven iteration)。

## 1. 核心指标诊断法则 (Analyzing Patterns)

每次运行测试后，请查阅 `iteration-N/benchmark.json`，关注以下指标：

* **激发失败 (Trigger Fails) 与 竞争者 (Competitors)**：
如果一个本该触发的 Query 失败了，去测试报告里看 `competitors` 字段。是被哪个现存技能抢占了风头？此时必须修改你的 `description`，用更精确的语言与那个"竞争者"划清界限。
* **高标准差 (High stddev)**：
如果在质量测试中，某项耗时或 Token 消耗的标准差 (`stddev`) 极高，这说明你的指令 (SKILL.md) 存在**严重歧义**。盲测工人每次的理解都不一样，导致有时快有时慢。你必须收紧指令，增加具体示例或规则。
* **全军覆没 (Always fails)**：
如果断言在所有测试里都失败，要么是你的要求超出了大模型的能力，要么是测试用例本身写错了。

## 2. 优化法则 (Applying Improvement Principles)

* **从反馈中泛化 (Generalize from feedback) & 防过拟合 (Avoid Overfitting)**：
修复应面向根本问题，绝对不要为了让某一个特定的测试用例 Pass 而在 SKILL.md 里硬编码特定关键词。寻找那些失败用例背后的通用概念并解决它。
* **保持精简 (Keep it lean)**：
规则不是越多越好。如果通过率停滞，尝试删除冗余的指令。当你发现测试工人在反复写相似的辅助代码时，立即将其提取到 `scripts/` 目录下打包。
* **解释"Why" (Explain the why)**：
与其死板地规定 "ALWAYS do X, NEVER do Y"，不如告诉模型 "Do X because Y tends to cause Z"，模型在理解意图后执行得更可靠。
* **避坑指南 (Gotchas)**：
把你在执行 Trace 中发现的特定报错、软删除逻辑等坑，全部补充到 `## Gotchas` 章节，这是技能中最有价值的部分。
"""


def generate_test_guide(skill_name: str) -> str:
    return f"""# {skill_name} 质量测试与提交流程指南 (How to Test & Merge)

**严禁在未经过沙盒盲测的情况下直接申请 skill_merge！**
修改代码后，必须完善 `evals/evals.json` 以驱动自动化盲测，它包含两个核心数组：`triggers` (激发测试) 和 `evals` (质量测试)。

## 1. 编写触发测试用例 (Designing Trigger Evals)

你需要在 `evals.json` 中添加 `triggers` 数组。建议设计 5-10 个用例。

* **正例 (Should-trigger)**：包含正式请求、随意的口语、缩写或错别字，以及隐藏在多步长对话中的复杂意图。
* **反例与擦边球 (Should-not-trigger/Near-misses) (极度重要)**：必须设计那些**包含你的技能关键词，但实际上并不需要你处理**的请求。
* *例如：对于 CSV 处理技能，不要用"今天天气如何"当反例，要用"帮我写一个能读取 CSV 到数据库的 Python 脚本"（这是写代码，不是分析数据）。*

## 2. 编写质量盲测用例 (Designing Quality Evals)

`evals` 数组用于测试执行结果：

* `prompt`: 真实的、包含文件路径的随利用户语气。
* `expected_output`: 人类可读的成功标准。
* `assertions`: 硬性断言。好的断言必须是可验证的（如"输出包含3个公式"），坏的断言是含糊的（如"输出得很好"）。不要在断言里规定必须使用某个一字不差的短语，这太脆弱了。

```json
{{
  "skill_name": "{skill_name}",
  "triggers": [
    {{"query": "我的表格销售额好像算错了，帮我查查", "should_trigger": true}},
    {{"query": "怎么用 Python 把这个表格文件转换格式？", "should_trigger": false}}
  ],
  "evals": [
    {{
      "id": "eval-sales-chart",
      "prompt": "I have a CSV in data/sales.csv. Make a bar chart.",
      "expected_output": "A bar chart image",
      "assertions": ["输出包含图表文件", "图表展示了完整的月份"]
    }}
  ]
}}
```

## 3. 如何发起测试与阅读档案 (Spawning Runs & Reading Archives)

使用 `KernelUpgrade` 工具发起 `test_skill` 后，系统会自动生成并累加 `iteration-N` 归档目录。
收到测试完毕的通知后，你必须按顺序阅读以下文件：

1. **`benchmark.json`**: 查看全局平均通过率 (mean) 和 标准差 (stddev)。评估你的技能修改是否值得。
2. **`eval_report.md`**: 查看 `triggers` 测试中，你是否被其他技能抢占了触发权。如果是，你需要修改 SKILL.md 里的 description 以使其更加贴合通用的使用场景。
3. **`trace.md` (必读)**: 去失败的用例目录下读取行为轨迹。看大模型在哪一步偏离了你的指令，反思是否可以通过优化 SKILL.md 或相应脚本工具来避免这些多余的消耗。

总之，优化的方向包含但不限于以下：
1. `triggers` 测试命中率要尽可能高
2. token/时间等资源消耗量要尽可能低
3. 指令要足够准确以防止使用者绕远路
4. 如有重复性操作可以固化为脚本
"""
