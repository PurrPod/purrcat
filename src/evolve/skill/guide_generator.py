"""
Skill 指南生成器模块 (evolve/skill/guide_generator.py)
单文件指南：覆盖创建、升级、盲测与提交全流程。
"""


def generate_skill_guide(skill_name: str, goal: str = "") -> str:
    goal_section = (
        f"\n> 🎯 **本次构建目标**：{goal}\n" if goal else ""
    )
    return f"""# {skill_name} 技能工厂指南 (GUIDE)

本指南覆盖创建、升级、盲测与提交全流程，动手前请先通读。
{goal_section}
## 1. 目录结构（渐进式披露）

不要把所有内容塞进一个文件：系统启动时只加载元数据，触发时加载 SKILL.md，需要时才加载附件。

* `./SKILL.md`：(必须) 核心指令，≤500 行 / 5000 tokens。超长内容拆到 references/ 并在文中注明相对路径。
* `./references/`：(可选) 大篇幅参考材料。
* `./scripts/`：(可选) 可复用的 Python/Bash 脚本，把重复操作固化下来省消耗。
* `./evals/evals.json`：(必须) 盲测用例配置。
* `./evals/files/`：(可选) 测试附件。

## 2. SKILL.md 编写标准

顶部 YAML Frontmatter，`description` 承担技能能否被触发的全部责任：

```yaml
---
name: {skill_name}
description: 1-200 字符，祈使句，描述用户意图而非底层实现，明确列出边缘场景。
---
```

指令最佳实践：
* **面向过程**：写具体 Checklist（1.读取 schema 2.Join 客户表 3.聚合输出），不要只写目标。
* **提供默认解**：明确默认用什么工具/路径。
* **模板化输出**：要求特定格式时直接给出 Markdown/JSON 模板。
* **解释 Why**："Do X because Y tends to cause Z" 比死板的 ALWAYS/NEVER 更可靠。
* **Gotchas**：把踩过的坑全部沉淀到 `## Gotchas` 章节，这是技能最有价值的部分。

## 3. evals.json 测试用例铁律

⚠️ `evals` 数组**只能写 1 个盲测用例**（后台盲测仅运行单用例，多用例只会浪费资源）。

`triggers` 数组为激发测试用例（建议 5-10 个）：
* **正例 (should_trigger=true)**：正式请求、口语、缩写、隐藏在多步长对话中的复杂意图。
* **反例 (should_trigger=false)**：包含技能关键词但实际不需要该技能处理的请求（如对 CSV 分析技能，"帮我写一个读取 CSV 的 Python 脚本"是写代码不是分析数据）。

`evals` 盲测用例的字段：
* `prompt`: 模拟用户的真实请求。**必须自包含**——从第一条消息开始就写明本次任务所需的全部信息（目标、输入、期望格式）。**严禁**设计任何需要用户中途提供输入、确认或交互的流程。
* `files`: 附件相对路径数组（先放入 `evals/files/`）；prompt 中只用文件名，**严禁绝对路径**。
* `expected_output`: 人类可读的成功标准。
* `assertions`: 可验证的硬性断言（如"输出包含3个公式"），禁止模糊断言（如"输出得很好"），也不要规定一字不差的短语。

```json
{{
  "skill_name": "{skill_name}",
  "triggers": [
    {{"query": "我的表格销售额好像算错了，帮我查查", "should_trigger": true}},
    {{"query": "怎么用 Python 把这个表格文件转换格式？", "should_trigger": false}}
  ],
  "evals": [
    {{
      "id": "basic_test_1",
      "prompt": "（自包含的模拟用户请求，只用附件文件名）",
      "files": ["evals/files/示例附件.txt"],
      "expected_output": "人类可读的预期结果描述",
      "assertions": ["输出的 JSON 文件格式必须合法"]
    }}
  ]
}}
```

## 4. 如何测试（Trigger 免审直接跑，盲测需老板批准）

你**无权**直接运行测试！须调用 `Request(request_type="skill_test", target="工作区uuid/{skill_name}")` 发起，两级流程如下：

1. **Trigger 激发测试（免审）**：提交后立即在后台运行（影子节点注入真实检索环境，检验 description 能否击败现存技能被唤醒），完成后收到系统级通知，报告归档在 `trigger-N/trigger_report.md`（与盲测目录解耦，独立计数）。
2. **后台盲测（需审批）**：老板批准后系统自动在后台双 Agent 隔离环境运行盲测。若本地无 skill_eval 图，盲测会被自动跳过（工具会明确提示），需老板安装测试图后重新申请。
3. 阅读本次产物（trigger-N 与 iteration-N 分开归档）：
   * `trigger-N/trigger_report.md`：激发唤醒率与语义竞争者，若被其他技能抢占需修改 description 划清界限。
   * `benchmark.json`：全局通过率 (mean)、耗时/Tokens 及标准差 (stddev)。
   * `eval_report.md`：本次用例的裁判评估结论。
   * `trace.md` (必读)：测试工人的行为轨迹，看它在哪一步偏离了你的指令。
4. 若盲测申请被拒绝，根据老板批注继续修复后再次申请。

## 5. 升级迭代诊断 (Eval-driven)

* **通过率低**：读 trace 找通用性根因。严禁为了让单个用例 Pass 而硬编码特定关键词（防过拟合），要解决失败背后的通用概念。
* **stddev 高**：指令存在歧义，盲测工人每次理解不同。收紧措辞、增加具体示例。
* **保持精简**：规则不是越多越好，通过率停滞时尝试删除冗余指令；重复出现的辅助代码提取到 `scripts/`。

## 6. 提交合并

**严禁在未经过沙盒盲测的情况下直接申请合并！** 测试通过后调用 `Request(request_type="skill_merge", target="{skill_name}")`，并在 reason 中简述修改点供老板 Code Review。
"""
