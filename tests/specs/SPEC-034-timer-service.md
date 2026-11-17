# SPEC-034：通用定时任务中心

## 背景

心跳和 system-clock 各自维护轮询线程/子进程：无法复用、空转耗电，且 Note 的时间线卡片到点不会触发任何动作。需要一份公共定时能力：任何组件按「来源 / 去向 / 效果」派发事件，服务只在事件库变化时计算下次唤醒时间并 sleep，新事件可打断当前等待。

## 行为

- 组件可以提交一次性或重复事件：`source` 标识提交方，`target` 决定去向（`main`/`agent`、`graph:<name>`、`ui:<channel>`），`effect` 描述到点后希望执行的效果。
- 事件落盘在 `~/.purrcat/data/schedule/timer_events.json`；进程重启后未完成的事件继续生效。
- 空闲时不轮询：没有待办事件就无限等待，有待办就精确 sleep 到最近一条事件的触发时刻；期间新增/修改事件会立即打断并重新计算。
- 接收方可以返回 `done`（完成）、`defer`（稍后重试）或 `skip`（放弃）。重复事件在 `done` 后按重复规则排下一次。
- 接收方的 `Signal.data` 会作为回执写入事件的 `result`（含 `action` / `data` / `at` / `attempt`），并随 SSE 广播回传给 source；source 按 `event.source` 过滤即可拿到 target 的反馈（例如 graph 派发后的 `task_id`）。
- 同 `source` 支持声明式覆盖：提交该来源的完整事件集合，服务自动取消不再出现的事件，避免 Note 反复编辑产生残留闹钟。
- 错过的事件：一次性事件在 120 秒宽限内补触发一次，超出则过期；重复事件直接顺延到下一次，不补跑历史场次。
- 提供 HTTP 接口与 SSE 事件流，UI 可订阅到点事件做提示。

## 验收标准

- [ ] AC-1：`next_after` 正确处理 interval / daily 重复规则，且结果严格晚于当前时刻。
- [ ] AC-2：一次性事件到点触发一次并标记完成；新事件能打断长 sleep 立即触发。
- [ ] AC-3：`defer` 会重排事件，`skip` 放弃，重复事件按规则续排。
- [ ] AC-4：`dedupe_key` 与 `replace_source` 能覆盖/移除同来源旧事件。
- [ ] AC-5：重启后按宽限策略处理错过的事件。
- [ ] AC-6：`/api/timer` 的 events/sources/state/delete 接口按契约返回，SSE 推送定时事件。
- [ ] AC-7：target 回执（`Signal.data`）持久化到事件并随 SSE 广播；graph sink 回执携带 `task_id`，source 可据此跟踪任务。

## 非目标

- 不做多进程/多实例定时去重。
- 不迁移旧 `cron.json` 数据（cron 功能下线）。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_timer_models.py` | AC-1 / AC-7 |
| L1 | `tests/l1/test_timer_service.py` | AC-2 / AC-3 / AC-4 / AC-5 / AC-7 |
| L1 | `tests/l1/test_api_timer.py` | AC-6 |

## 风险与回滚

- 定时服务跑在 uvicorn 事件循环内；线程侧（心跳启动）只做「改表 + 落盘 + 线程安全唤醒」，不直接 await。
- 事件重复投递为 at-least-once：进程在 sink 执行中崩溃会重放，接收方需按 `id` 幂等。
