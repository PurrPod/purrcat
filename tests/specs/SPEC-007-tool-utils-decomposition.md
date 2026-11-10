# SPEC-007：工具路由、媒体与执行器的解耦

## 背景

`src/tool/utils/route.py` 同时承担注册表、参数解析、进程/线程执行、多媒体落盘、vision 直注与超长输出处理，任何一处调整都牵动整个工具层。

## 行为

- `route.py` 保留工具注册映射、隔离名单、`resolve_tool` 与 `dispatch_tool` 的封包/异常语义。
- 多媒体处理移入 `tool/utils/media.py`：
  - 非媒体内容原样返回；
  - vision 模式下图片（png/jpg/jpeg/gif/webp）转为 OpenAI `text + image_url` parts，不落盘；
  - SVG/BMP 等非常规格式与视频/音频/PDF 继续落盘，返回宿主机与沙盒双路径。
- 执行器移入 `tool/utils/execution.py`：
  - 同步与异步工具均可执行；
  - 进程内执行在 cancel_event 触发时返回统一的「人类打断」结果；
  - 隔离执行在打断时物理 terminate 子进程，超硬上限返回超时提示；
  - 子进程异常在父进程重新抛出。
- 超长输出移入 `tool/utils/output_limit.py`：完整内容写入 `.buffer/<tool>/<时间戳>_<随机>.txt`，返回含路径与预览的提示；预览按 token 预算截断。

## 验收标准

- [ ] AC-1：媒体类型、vision 白名单、双路径文案有 L0 用例。
- [ ] AC-2：同步/异步、错误传播、打断返回有 L0 用例。
- [ ] AC-3：落盘文件名、提示文案与预览截断有 L0 用例。
- [ ] AC-4：既有 `test_tool_truncation.py`（含 BUFFER_DIR 注入）保持通过。
- [ ] AC-5：工具注册契约与调度路径不变。

## 非目标

- 不扩大进程隔离白名单。
- 不改变工具返回的 JSON 封包结构。
- 不新增媒体格式支持。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_tool_media.py` | AC-1 |
| L0 | `tests/l0/test_tool_execution.py` | AC-2 |
| L0 | `tests/l0/test_tool_output_limit.py` | AC-3 |
| L0 | `tests/l0/test_tool_truncation.py` | AC-4 |
| L0 | `tests/l0/test_tool_registry_contract.py` | AC-5 |

## 风险与回滚

- vision 直注结果包含 base64，任何格式化/截断都可能破坏图片：分派顺序仍为「媒体处理 → vision 短路 → 输出限额 → YAML 格式化」。
- 回滚方式：恢复单文件 `route.py`；测试可直接复用。
