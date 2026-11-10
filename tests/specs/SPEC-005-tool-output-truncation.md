# SPEC-005：工具输出超长截断

## 背景

工具输出在 `dispatch_tool` 内按 token 统一拦截，超限内容落盘并返回预览，避免撑爆上下文。此前没有测试锁住落盘位置、封包结构、vision 例外与异常兜底。

## 行为

- 上限由 `get_output_token_limit(available_tokens)` 计算：
  - 不传可用 token → `DEFAULT_OUTPUT_TOKEN_LIMIT`（10000）；
  - 传入值 → `available_tokens - 500`，夹在 `[500, 10000]`。
- 超过上限且不是 `fetch(source=skill)` 时：
  - 完整内容写入 `BUFFER_DIR/<tool>/<时间戳>_<随机>.txt`，内容与工具原始输出逐字一致；
  - 返回的 `content` 以系统拦截提示开头，包含沙盒内缓存路径与预览；
  - `metadata.type == "warning"`，`metadata.snip` 提示已截断落盘。
- 未超限时原样返回，不创建缓存目录。
- 输出是 OpenAI 多模态 parts 时跳过截断与格式化，`metadata.type` 归一为 `text`，`snip` 并入首个文本 part。
- 工具解析失败或执行抛异常时返回 `metadata.type == "error"` 的 JSON，不向上抛。

## 验收标准

- [ ] AC-1：`get_output_token_limit` 的默认、下界、动态、上界四种取值正确。
- [ ] AC-2：超长输出会落盘、返回 warning 封包，且落盘内容与原始输出完全一致。
- [ ] AC-3：短输出不落盘、`metadata.type` 保持原值。
- [ ] AC-4：vision parts 不被截断、不落盘，`snip` 合并进文本 part。
- [ ] AC-5：工具抛异常 / 无法解析时返回 error 封包而非抛出。

## 非目标

- 不调整 token 预算常量与截断算法。
- 不覆盖各工具自身的输出语义。
- 不测试真实网络或真实大文件读取。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_tool_truncation.py` | AC-1 ~ AC-5 |

## 风险与回滚

- 测试通过 monkeypatch `route.resolve_tool` 注入假工具，不触碰真实工具实现；`BUFFER_DIR` 指向 `tmp_path`，不写用户数据目录。
