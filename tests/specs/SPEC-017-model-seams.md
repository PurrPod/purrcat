# SPEC-017：Model 层接缝（用量账本与重试策略）

## 背景

`src/model/` 里两块确定性逻辑与外部 I/O 混在一起，难以 TDD：

1. `usage_tracer.py` 的字段提取、快照初始化、增量累加与磁盘账本合并全部写在单例方法内，测试必须构造真实目录。
2. `llm_client.py` 的模型名清洗、可重试判定、指数退避内联在重试循环里，只能通过伪造整个 OpenAI 客户端来覆盖。

## 行为

- `model/manager/usage_stats.py` 提供纯函数：
  - `mask_api_key`：空 Key → `UNKNOWN`；长度 ≤10 → `***`；否则保留前 6 后 4。
  - `extract_usage_fields`：读取 `prompt_tokens / completion_tokens / total_tokens`，并从 `*_tokens_details` 提取 `cached_tokens / reasoning_tokens`，缺失时回落 0。
  - `empty_bucket` / `apply_delta`：一次调用计数 +1，token 字段累加，时长按 3 位小数累加。
  - `merge_into_disk`：按 `model|api_key` 合并，已存在则逐字段累加（时长保留 3 位小数），新键追加在末尾。
- `model/core/retry.py` 提供纯函数：`strip_model_prefix`（取冒号后段）、`is_retryable_error`（限速 / 429 / 连接或服务端错误 / 502-504 可重试）、`backoff_seconds`（`2 * 2^attempt * jitter`，jitter 默认 `[0.8, 1.2]`）。
- `usage_tracer` 与 `LLMClient` 的公开行为、日志文案、重试次数（8）与退避分布保持不变，仅改为委托上述纯函数。

## 验收标准

- [ ] AC-1：`mask_api_key` 三种分支与示例输出符合预期。
- [ ] AC-2：`extract_usage_fields` 能读取缓存/思考 Token，缺失时回落 0。
- [ ] AC-3：`apply_delta` 的计数、token、时长累加与舍入正确。
- [ ] AC-4：`merge_into_disk` 对已存在键累加、对新键追加，顺序稳定。
- [ ] AC-5：`ModelUsageTracer.record → flush` 在临时目录写出 `YYYY-MM-DD_summary.json`，并清空增量账本；空 usage 不记账。
- [ ] AC-6：`strip_model_prefix`、`is_retryable_error`、`backoff_seconds` 的参数化用例全部通过；`MAX_RETRIES == 8`。

## 非目标

- 不改变单例生命周期、60 秒刷盘间隔与 atexit 注册。
- 不改变 OpenAI 客户端超时（60s）与每次请求前 0.2s 等待。
- 不引入异步客户端或新的重试库。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_model_usage_stats.py` | AC-1 ~ AC-5 |
| L0 | `tests/l0/test_model_retry.py` | AC-6 |

## 风险与回滚

- 退避抖动仍由 `random.uniform(0.8, 1.2)` 生成，分布不变；若需固定值测试可显式传入 `jitter`。
- `usage_tracer` 的磁盘合并已抽为纯函数，若出现字段缺失回归，优先检查 `SUMMARY_FIELDS` 与旧账本键名是否一致。
