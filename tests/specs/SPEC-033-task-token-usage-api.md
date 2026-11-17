# SPEC-033 任务总 token 消耗实时查询

## 背景

`Task` 已在内存中按 LLM 调用累加 `total_tokens`，并落盘到 checkpoint 的 `state.json`，但只有任务列表接口以 `token_usage` 的形式返回（且活跃任务取错属性恒为 0），没有任何接口能单独实时读取某个任务图的累计 token 消耗。

## 行为

- 新增只读接口 `GET /api/tasks/{task_id}/token`，返回任务累计消耗的 token 总数。
- 任务在内存中时直接读最新值，保证轮询能看到运行中的实时增长；任务不在内存时读取磁盘 `state.json` 的快照。
- 任务不存在返回 404；响应不允许缓存（`Cache-Control: no-store`）。

## 验收标准

- [ ] AC-1：活跃任务返回内存中的 `total_tokens`，且同一任务后续累加后再次请求能得到新值。
- [ ] AC-2：非活跃任务返回 checkpoint `state.json` 中的 `total_tokens`；任务不存在返回 404。
- [ ] AC-3：路由契约、`docs/api` 生成物与手写任务文档同步。

## 非目标

- 不修正任务列表 `build_active_task` 读取 `token_usage` 的既有偏差。
- 不拆分节点级 token，也不统计子代理/后台会话的消耗。
- 不改变 `Task.total_tokens` 的累加口径与落盘时机。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_task_token_usage.py` | AC-1、AC-2 |
| L1 | `tests/l1/test_api_routes_contract.py` | AC-2、AC-3 |
| L3 | `scripts/check_api_docs.py` | AC-3 |

## 风险与回滚

只新增只读路由与查询函数，不改动任务引擎与持久化格式；风险集中在路由顺序与文档生成物漂移，回滚时删除路由、函数与文档条目即可。
