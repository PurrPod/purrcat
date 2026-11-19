# SPEC-041：向量库模型版本标记与重建

## 背景

嵌入模型从 MiniLM 切换到 multilingual-e5-small 后，旧向量与新向量不在同一语义空间，
维度也可能不同。SQLite 与图谱结构是事实源，但 Chroma 中已有向量无法自动迁移，
`index_worker.reconcile` 只会补缺失项，不会重编码已有项。用户需要能判断向量库是否
需要重建，并有一个明确的重建入口。

## 行为

- 重建完成后，三个 Chroma collection 的 metadata 写入 `embedding_model=<MODEL_TAG>`。
- 记忆健康检查返回 `index_version`：`missing / empty / current / stale / unreadable`。
- 有向量但缺少标记或标记与当前模型不一致时判定为 `stale`，健康检查给出
  `vector_index_stale` 问题项。
- 记忆设置页展示向量模型状态；`stale` 时显示原因与「重建向量库」按钮。
- `POST /api/config/memory/reindex` 与 `scripts/reindex_memory.py` 执行同一套重建：
  清空并重编码事件、经验、图谱节点，结束时写入模型标记。

## 验收标准

- [ ] AC-1：无向量的库不判定为 stale。
- [ ] AC-2：无标记或旧标记的向量判定为 stale 且 `needs_rebuild=true`。
- [ ] AC-3：重建先加载编码器再清空集合，避免模型缺失时丢失现有向量。
- [ ] AC-4：重建计数来自事件 / 经验 / 图谱三个事实源，完成后写入模型标记。

## 非目标

- 不修改 SQLite 事件 / 经验内容与图谱结构。
- 不做增量迁移：旧模型向量一律整体重建。
- 不自动在启动时重建（数据量大，需用户确认）。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_index_version.py` | AC-1、AC-2 |
| L1 | `tests/l1/test_memory_reindex.py` | AC-3、AC-4 |

## 风险与回滚

- 重建期间向量检索不可用；后端进程内重建与索引 worker 可能短暂并发写，重建完成后
  下一次对账会补齐遗漏。
- 脚本运行时必须停掉后端，避免两个进程同时写 Chroma。
- 回滚：删除 collection metadata 中的 `embedding_model` 即可回到未标记状态（会再次被判为 stale）。
