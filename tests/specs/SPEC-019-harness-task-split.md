# SPEC-019：Harness 任务调度、控制与持久化拆分

## 背景

`src/harness/process.py` 的 `Task` 仍在单个类里混放主循环、节点并发启动、控制指令、级联重置与检查点读写，文件接近 800 行。主循环顺序、写盘时机与状态流转难以独立验证，新增改动容易牵动数据面。

## 行为

- `Task` 保留原有公开方法与签名（`run`、`kill`、`inject_instruction`、`reset_node`、`load_checkpoint`、`save_state` 等），只持有字段并委托给三个新模块：
  - `task_state.py`：`force_push` 指令入队、注入后的任务唤醒状态、终态 kill 判定、等待人工节点的挂起文案；
  - `task_scheduler.py`：取可运行节点、按并发上限启动协程、等待首个完成、成功置位与失败置 ERROR；
  - `task_persistence.py`：`meta.json` / `state.json` 的保存、新旧格式恢复与旧 `node_memory` 迁移。
- 主循环的可观察顺序不变：
  - 每轮先判 kill，再取可运行节点，再判挂起/完成；
  - 启动节点时先置 RUNNING 再 `create_task`，超过 `max_concurrency` 停止启动；
  - 本轮有候选节点（即使因并发上限未真正启动）先同步写盘，再等待完成；
  - 节点成功先置 COMPLETED 再点亮端口；失败置节点与任务 ERROR 后返回错误；
  - 等待结束后无条件写盘，终态写盘与 kill 写盘保持同步。
- 检查点字段、`_io_lock` 串行化与 `asyncio.to_thread` 包装时机不变。
- 级联重置仍按 BFS 顺序执行，目标节点在注入时保留 `live_memory.json`，彻底重置删除整个节点目录。
- `agent_node.py` 评估结论：文件内的 `_parse_tool_arguments` 等已是模块级纯函数，`_sanitize_messages` 只服务 agent_loop 一处，未发现可独立拆出的提示词组装逻辑，本次不拆。

## 验收标准

- [ ] AC-1：注入指令写入 `force_push` + `skip_upstream`，运行中任务保持 RUNNING，非 Agent 节点与 Agent 越权注入被拒。
- [ ] AC-2：`kill` 在终态忽略，非终态置 `_killed` 并取消运行中协程；`kill_task` 最终置 KILLED。
- [ ] AC-3：可运行集合、并发上限、首完成处理顺序与失败置 ERROR 有 L0 用例。
- [ ] AC-4：完整 `run` 中「启动写盘 → 成功写盘 → 下一节点 → 终态写盘」的时序有 L0 用例。
- [ ] AC-5：挂起、kill、初始化错误三种终态返回结构有 L0 用例。
- [ ] AC-6：既有 L0/L1 全绿，`ruff check src/harness tests/l0 tests/l1` 通过。

## 非目标

- 不改变节点执行器、DAG 状态机、检查点文件名与磁盘布局。
- 不改变工具、API 与前端契约。
- 不为缩短行数而拆分 `agent_node.py`。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_harness_task_control.py` | AC-1、AC-2 |
| L0 | `tests/l0/test_harness_scheduler.py` | AC-3 |
| L0 | `tests/l0/test_harness_process_flow.py` | AC-4、AC-5 |
| 全量 | `tests/l0`、`tests/l1` | AC-6 |

## 风险与回滚

- 主循环的启动/等待/写盘时序最易出错：先由 characterization 测试锁定，再等价搬移。
- 调度器只操作 `Task` 已有字段与方法，不新增并行路径。
- 回滚方式：将三个模块逻辑并回 `process.py`，测试保留。
