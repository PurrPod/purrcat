# SPEC-022：工具包与配置访问器的最后一轮内聚整理

## 背景

`src/tool/` 下 cron、memo、brainstorm、fetch、kernelupgrade、request、search 仍存在“参数校验 / 文案拼装 / IO / 调度”混写与跨模块重复：
- Cron 的 HH:MM 正则与列表文案在 `cron.py`、`cron_operations.py` 各写一份。
- Memo 的 MEMORY.md 提示词、缓存/检索结果拼装与文件读写混在 `memo.py` / `memo_operations.py`。
- BrainStorm 的计划 Markdown、创建回执、tool_calls 补全逻辑都在主入口内联。
- Fetch 的编码识别、字节解码、HTML→Markdown、原始文本包装在两条抓取路径重复。
- KernelUpgrade 的 target 归一化、URL 判定、`uuid/名字` 解析在 install/merge/test 各写一份。
- Request 的 requests.json 读取/写回在 api 层重复；Search 的“编码→打分→TopK”流程在 MCP/Skill 各写两遍。

这些重复让纯逻辑难以单测，也容易在后续改动中漂移。本次只做内部整理，工具名、参数 schema、返回结构与错误文案必须逐字不变。

## 行为

- Cron：新增 `src/tool/cron/cron_rules.py`，集中纯函数 `is_valid_trigger_time`、`is_valid_repeat_rule`、`next_run_time`、`format_cron_list`；`Cron` 与 CRUD 共用同一套校验。
- Memo：新增 `src/tool/memo/_shared.py`，集中日期校验、MEMORY.md 提示词、覆盖内容解析、缓存与检索结果格式化；文件读写仍留在 `memo_operations.py`。
- BrainStorm：新增 `src/tool/brainstorm/_shared.py`，集中计划 Markdown、创建回执、assistant 批次定位、未应答 tool_call 筛选与补全条目构造。
- Fetch：新增 `src/tool/fetch/_shared.py`，集中 charset 解析、字节解码、字节裁剪、HTML→Markdown、原始文本结果构造；两个抓取通道复用。
- KernelUpgrade：`shared.py` 增加 target 归一化、URL 判定、沙盒路径解析、`uuid/名字` 解析；install/merge/test 复用；校验报告正文抽为纯函数。
- Request：`_shared.build_request_record` 纯函数化请求记录；`request_operations` 提供统一的 requests.json 读/写，各调用点保留原有异常策略。
- Search：`_shared` 增加文档文本模板与 `score_top_k`，MCP/Skill 的 search 与 simulate_trigger 共用同一打分流程。
- Config：内部抽出 settings 读取、按需 JSON 读取两个去重助手；对外访问器签名与返回值不变。

## 验收标准

- [ ] AC-1：Cron 时间/重复规则校验、下次运行时间、列表文案有 L0 用例，且工具输出不变。
- [ ] AC-2：Fetch 的 charset 解析、解码回落、字节裁剪、HTML→Markdown、原始文本包装有 L0 用例。
- [ ] AC-3：Memo 提示词/结果聚合与 BrainStorm 计划/回执/tool_call 补全有 L0 用例。
- [ ] AC-4：配置访问器的缺省值、结构异常、类型回落有 L0 用例。
- [ ] AC-5：既有 L0/L1 全量回归通过，ruff check 与 format 全绿。

## 非目标

- 不修改任何工具的 `*_TOOL_SCHEMA`、动作名、参数名与错误文案。
- 不改变 cron.json / MEMORY.md / requests.json 的磁盘格式。
- 不动 `src/tool/utils/route.py`、`execution.py`、`media.py`、`output_limit.py`。
- 不调整既有 `_shared.py` 中已定稿函数的语义。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_tool_cron.py` | AC-1 |
| L0 | `tests/l0/test_tool_fetch_content.py` | AC-2 |
| L0 | `tests/l0/test_tool_memo_brainstorm.py` | AC-3 |
| L0 | `tests/l0/test_config_model_accessors.py` | AC-4 |
| L0/L1 | 全量 `tests/l0 tests/l1` | AC-5 |

## 风险与回滚

- 风险集中在文案与排序：任何拼装顺序变化都会改变工具返回，必须由 characterization 用例逐字锁定。
- Search 打分流程抽函数后需保持 `clamp_negative` 的 MCP/Skill 差异与原有 TopK 截断。
- 回滚方式：各包新增纯函数文件可独立删除，调用点恢复内联实现即可。
