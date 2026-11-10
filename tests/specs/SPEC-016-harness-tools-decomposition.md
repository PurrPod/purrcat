# SPEC-016：Harness 主循环与超大工具文件的分层解耦

## 背景

`src/harness/process.py` 的 `Task` 同时承担主循环调度、节点执行包装、端口状态机、级联重置与检查点写盘；多个工具文件把参数校验、纯计算、I/O 与结果格式化混在同一函数里。逻辑难以单测，改动易牵一发动全身。

## 行为

- DAG 调度相关纯逻辑移入独立模块，`Task` 原方法名保留并薄委托：
  - 可运行节点判定与级联 skip（含同轮传播顺序）由纯函数完成；
  - 节点成功后的 COMPLETED 置位与端口点亮顺序不变；
  - 节点重置按 BFS 顺序逐节点处理（重置状态 → 清端口 → 取消协程 → 清理节点目录 → 入队下游）；
  - `state.json` 快照字段与写盘时机（同步写、`_io_lock` 串行、`to_thread` 包装）完全不变。
- 节点执行包装仍按「后台线程组装输入 → 执行节点 → 后台线程落盘输出」顺序进行，异常继续向上抛。
- 工具文件按「参数规范化 → 纯计算/路径处理 → I/O 执行 → 结果格式化」分层，重复的纯逻辑收敛到包内 `_shared`：
  - 文件工具：行尾归一化、主导行尾写回、原子写入、统一 diff、diff 摘要、锁路径生成、忽略规则；
  - Bash：docker exec 命令、shell 包裹载荷、输出清洗与去回显；
  - MCP：配置指纹、环境变量净化、图片载荷解析；
  - Search：混合打分（含 BM25 负分截断差异）、TopK 排序与名次判定；
  - Request：合并目标拆分、拒绝文案与决策回调文案。
- 所有工具的参数、返回结构与错误文案保持不变。

## 验收标准

- [ ] AC-1：READY 节点在 PENDING/HAS_DATA/全 VOID 三种上游状态下的可运行判定与级联 skip 有 L0 用例。
- [ ] AC-2：全 VOID 级联 skip 在同一轮内继续向下游传播的行为有 L0 用例。
- [ ] AC-3：节点成功先置 COMPLETED 再点亮端口的顺序有 L0 用例。
- [ ] AC-4：级联重置的 BFS 顺序、指令注入保留目标目录、彻底重置删除节点目录有 L0 用例。
- [ ] AC-5：state.json 快照字段与序列化结果有 L0 用例。
- [ ] AC-6：节点执行包装的输入/执行/落盘顺序有 L0 用例。
- [ ] AC-7：文本行尾归一化、主导行尾检测、原子写入与统一 diff 有 L0 用例。
- [ ] AC-8：docker exec 命令与 shell 载荷构造、输出去回显与 ANSI 清洗有 L0 用例。
- [ ] AC-9：MCP 配置指纹与环境净化、搜索混合打分的负分处理差异、Request 文案有 L0 用例。
- [ ] AC-10：既有 L0/L1 全绿，`ruff check` 通过。

## 非目标

- 不改变节点执行顺序、并发上限与协程调度方式。
- 不改变检查点文件名、磁盘布局与写盘时机。
- 不改变工具参数校验规则、返回结构、错误文案与截断阈值。
- 不修改已整理的 `src/tool/utils/execution.py`、`media.py`、`output_limit.py`、`route.py`。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_harness_process_flow.py` | AC-1 ~ AC-6 |
| L0 | `tests/l0/test_filesystem_text_ops.py` | AC-7 |
| L0 | `tests/l0/test_bash_docker_env.py` | AC-8 |
| L0 | `tests/l0/test_tool_shared_normalization.py` | AC-9 |
| 全量 | `tests/l0`、`tests/l1` | AC-10 |

## 风险与回滚

- 状态机是 DAG 数据面，级联 skip 的同轮传播与检查点写盘时机最易出错，先用纯函数 characterization 测试锁定，再由 `Task` 薄封装调用。
- 工具层只做等价搬移与纯函数抽取，不改 I/O 顺序与异常类型。
- 回滚方式：将新模块逻辑并回原文件；测试保留。
