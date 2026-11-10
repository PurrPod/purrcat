# SPEC-008：Harness 图加载、检查点与节点 I/O 的解耦

## 背景

`harness/process.py` 的 `Task` 同时负责图解析、参数校验、节点实例化、输入组装、输出落盘与检查点恢复，且三套检查点格式各自重复恢复逻辑。

## 行为

- 图加载与校验移入 `harness/graph_spec.py`：
  - 缺失 `graph.json` 返回 `None`；
  - 必填/未知参数错误文案与改造前一致；
  - 已移除节点类型给出替换指引，未知类型报「节点加载失败」。
- 检查点纯数据操作移入 `harness/checkpoint.py`：
  - 落盘/恢复的枚举转换一致；
  - 恢复时 RUNNING 的节点降级为 READY、任务降级为 INTERRUPTED；
  - `meta.json` 优先于旧 `checkpoint.json`；
  - 落盘 node_memory 只保留 `force_push`。
- 节点 I/O 移入 `harness/node_io.py`：
  - 仅从 HAS_DATA 的上游端口组装输入；
  - 信封化后做类型硬校验，类型不兼容抛 `ValueError`；
  - 读取上游的非 ValueError 异常记录日志并跳过；
  - 输出按端口信封写入 `nodes/<id>/outputs.json`；file 端口的大内容剥离到 `files/` 并返回 task URI。

## 验收标准

- [ ] AC-1：必填缺失、未知参数、合法输入三种校验结果有 L0 用例。
- [ ] AC-2：节点实例化成功/未知类型/废弃类型有 L0 用例。
- [ ] AC-3：检查点序列化与 RUNNING 降级、描述文件优先级有 L0 用例。
- [ ] AC-4：输入组装在 HAS_DATA/PENDING、类型不兼容、上游损坏三种情况下的行为有 L0 用例。
- [ ] AC-5：输出信封与大文件剥离有 L0 用例。
- [ ] AC-6：既有 harness 集成测试保持通过。

## 非目标

- 不改变图 schema、节点协议与端口状态机。
- 不改变检查点文件名与磁盘布局。
- 不修改节点执行顺序与并发模型。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_harness_graph_spec.py` | AC-1, AC-2 |
| L0 | `tests/l0/test_harness_checkpoint.py` | AC-3 |
| L0 | `tests/l0/test_harness_node_io.py` | AC-4, AC-5 |
| L1 | 既有 harness 测试 | AC-6 |

## 风险与回滚

- 节点输入/输出是 DAG 数据面，先锁纯函数再由 `Task` 薄封装调用，保证异常类型与日志字段不变。
- 回滚方式：把三个模块的逻辑并回 `process.py`；测试保留。
