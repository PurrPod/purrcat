# SPEC-035 任务耗时查询与任务目录名清洗

## 背景

定时器/插件派发的后台任务需要像 token 消耗一样实时展示耗时。耗时由 Task 自己维护，插件只轮询接口；
同时任务名可能来自用户内容（如笔记标题），直接拼进 checkpoint 目录会在 Windows 上触发 `WinError 123`。

## 行为

- `Task` 记录 `started_at`（本次运行起点）与 `finished_at`（最近终态时间），并随 `state.json` 持久化；
  旧的 `execution_time` 仍表示已结束会话的累计耗时。
- 新增 `GET /api/tasks/{task_id}/elapsed`：
  - 运行中：`execution_time + (now - started_at)`；
  - 终态/休眠：直接返回 `execution_time`；
  - 旧档缺 `started_at` 时返回 `null`，不报错；任务不存在返回 404。
- checkpoint 目录名中的任务名经过 `safe_task_dir_name` 清洗（`<>:"/\|?*` 与控制字符替换为 `_`，
  去掉尾部 `.`，截断到 80 字符），目录仍保持 `{safe_name}_{task_id}`，不影响按 task_id 查找历史任务。

## 验收标准

- [ ] AC-1：活跃任务在运行中返回累计耗时 + 当前会话耗时，进入终态后不再增长。
- [ ] AC-2：休眠/已结束任务从 `state.json` 读取耗时；任务不存在返回 404。
- [ ] AC-3：任务名含 `:`、`/`、`\` 等字符时不再产生非法路径，`safe_task_dir_name` 输出可直接作为目录名。

## 非目标

- 不做跨进程的 CPU/内存指标；耗时是墙钟时间。
- 不修改已有 checkpoint 目录名；历史任务仍按 `task_id` 定位。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_task_elapsed.py` | AC-1 ~ AC-3 |

## 风险与回滚

- 进程异常退出时 `state.json` 可能停留在 `running`，休眠读取只返回已落盘的累计耗时，不会虚假增长。
- 回滚：删除接口与 `started_at/finished_at` 字段，任务目录命名恢复原逻辑。
