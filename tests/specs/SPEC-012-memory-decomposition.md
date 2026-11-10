# SPEC-012：记忆包（src/memory）职责拆分与依赖注入

## 背景

`src/memory/` 的检索、存储与后台工人代码混在一起：`search_tool.py` 同时承担 RRF 排序、Top-K 过滤、Markdown 拼装、遗忘衰减；三个存储引擎各自重复实现向量归一化、余弦相似度、集合条数夹紧、时间戳与 ID 生成、pickle 读写；`worker_agent.py` 把 LLM 工具 schema、提示词、pending 数据解析与文件编排写在一个方法里。这些逻辑无法在不启动 ChromaDB、不加载嵌入模型、不读写真实 `~/.purrcat` 的情况下单测。

## 行为

- 纯逻辑抽到 `src/memory/purrmemo/core/` 下的独立模块，原模块保留同名入口并委托，外部 import 路径不变：
  - `schema.py`：默认 Top-K、候选池大小、经验阈值、图谱节点召回与加权常量。
  - `scoring.py`：`reciprocal_rank_fusion`、`similarity_from_distance`、`graph_node_boost`、`decayed_confidence`。
  - `filters.py`：`clamp_top_k`、`filter_by_time_range`、`filter_experiences_by_score`、`build_fts_query`、`date_range_for`。
  - `formatting.py`：搜索结果 Markdown、关系字典、图谱 nodes/edges、最近经验整形、图谱边样式。
  - `clock.py` / `ids.py`：统一时间戳与事件/经验/边/节点 ID 生成。
  - `storage/graph_io.py`：图谱 pickle 读写。
  - `memory_worker/schema.py`、`prompts.py`、`payload.py`：工具定义、提示词拼装、pending 数据解析。
- 重复实现合并为单一来源：`1.0 - distance`、`min(top_k, count)`、`get(ids=...)` 记录读取、`datetime.now().isoformat()`、`evt_/exp_/node_/edge` ID、pickle load/save。
- 存储引擎、检索工具、客户端与后台工人新增可选依赖注入参数（`client`、`embedding_model`、路径、子引擎、`model_factory`）；不传时保持原有默认构造与懒加载行为。
- 所有日志文案、返回结构、排序顺序、阈值与默认 Top-K 保持不变。

## 验收标准

- [x] AC-1：RRF 融合、余弦相似度、图谱节点加权、遗忘衰减的输入输出与改造前一致。
- [x] AC-2：Top-K 夹紧、时间区间过滤、经验阈值过滤、FTS 查询构造、日期区间解析有参数化用例。
- [x] AC-3：Markdown 格式化、图谱 payload、最近经验整形、提示词拼装、pending 解析输出逐字稳定。
- [x] AC-4：`EventEngine`/`GraphEngine`/`VectorEngine` 用 `tmp_path` 与假 ChromaDB/嵌入模型即可验证 CRUD、检索、衰减与持久化契约。
- [x] AC-5：`RAGSearchTool`、`PurrMemoClient`、`MemoryAgent` 可注入替身，公开方法契约不变。
- [x] AC-6：原 import 路径（`search_tool.reciprocal_rank_fusion`、`tools.get_node_id`、`storage.*` 等）继续可用。

## 非目标

- 不改 SQLite/ChromaDB 表结构、集合名、检索阈值与默认条数。
- 不改 LLM 工具名、提示词内容、daemon 轮询周期与遗忘调度周期。
- 不新增运行时抽象层，不重写存储实现，不调整线程模型。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_memory_scoring.py` | AC-1、AC-2 |
| L0 | `tests/l0/test_memory_formatting.py` | AC-3 |
| L1 | `tests/l1/test_memory_engine_contract.py` | AC-4、AC-5、AC-6 |
| L0/L1 | 现有全套 | 回归 |

## 风险与回滚

- 拆分采用「纯函数搬运 + 原入口薄委托」，若某引擎行为异常，可将对应模块函数并回原文件。
- 单例元类会缓存首个实例，测试通过重置 `SingletonMeta._instances` 隔离；生产路径的构造参数与顺序未变。
- 需重点回归：混合检索排序、图谱关系置信度、遗忘衰减、pending 文件归档与嵌入模型未就绪时的重试。
