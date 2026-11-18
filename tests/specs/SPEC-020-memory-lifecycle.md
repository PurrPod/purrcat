# SPEC-020 记忆生命周期与经验库重构

- **状态**：待实现
- **日期**：2026-11-18
- **范围**：`src/memory/`、`src/tool/memo/`、`src/server/api/memory.py`、`ui/web-minimal/plugins/builtin/builtin-memory/`
- **关联**：SPEC-012（三库拆分）、SPEC-039（最小相似度阈值）

## 1. 目标

把经验库从“只有向量的字符串集合”升级为“SQLite 为事实源、向量为索引、置信度可展示、可强化、可替换、可删除”的记忆库；同时修复事件库的向量孤儿问题，统一中文 BM25 分词，并把经验与图谱的线性衰减改为艾宾浩斯式指数衰减。

核心约束：

1. **置信度只展示，不参与检索得分**，但必须返回给 agent 和 UI。
2. **新经验置信度 0.6**；`reinforce` 提升 0.2（上限 1.0）；`replace` 重置为 1.0；下限 0.3，不自动删除。
3. **硬删除 + 只追加证据日志**：删除后可通过日志快照恢复；不实现软删状态。
4. **删除、替换、强化同步写库**，不进 pending。
5. **SQLite 与 Chroma 不追求跨库事务**，用同库 outbox + 幂等索引器 + 对账保证最终一一对应。
6. **中文检索继续支持中文**，通过 jieba 分词改善 BM25，不要求用户改用英文。

## 2. 现状与问题

- 经验只存在 Chroma（`experiences` collection），没有 SQLite 表、没有 FTS5、没有置信度、没有稳定可操作 ID 的展示。
- 事件清理只删除 SQLite + FTS5，Chroma 中的事件向量不会删除，过期事件仍可能被语义检索召回。
- 事件 FTS5 使用默认 `unicode61` 分词；实测 30 条语料、14 条中文查询，Top1/Top3 均为 0，中文查询基本无法命中。
- 图谱使用 `0.05/天` 线性衰减，且每天回写 `updated_at`。
- `Memo` 只有 `add/search`，无法强化、替换、删除经验。
- agent 看到的检索结果不包含经验 ID 与置信度，即使加了这些能力也无法调用。

## 3. 数据模型

### 3.1 经验库（新文件 `~/.purrcat/data/memory/experiences.db`）

```sql
CREATE TABLE IF NOT EXISTS experiences (
  exp_id TEXT PRIMARY KEY,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL UNIQUE,
  problem TEXT,
  solution TEXT,
  confidence REAL NOT NULL,                   -- 基值，读取时再按锚点惰性衰减
  confidence_updated_at TEXT NOT NULL,        -- 衰减锚点，仅 reinforce/replace/add 刷新
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts
USING fts5(exp_id UNINDEXED, tokens, tokenize='unicode61');

CREATE TABLE IF NOT EXISTS experience_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  exp_id TEXT NOT NULL,
  action TEXT NOT NULL,                       -- add/reinforce/replace/delete/restore
  old_confidence REAL,
  new_confidence REAL,
  snapshot TEXT,                              -- 删除/替换前的完整 JSON 快照
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_outbox (
  memory_id TEXT PRIMARY KEY,
  op TEXT NOT NULL CHECK(op IN ('upsert', 'delete')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
```

- `exp_id` 沿用现有 `exp_<md5>` 内容哈希 ID；`replace` 不改变 `exp_id`，只更新 `content_hash`。
- 重复 `add`（`content_hash` 已存在）视为一次弱 `reinforce`，不重置内容与置信度。
- 不区分经验类型（原 `kind` 字段已移除），画像与工作经验统一作为可复用经验管理。

### 3.2 事件库（现有 `events.db` 增量）

```sql
CREATE TABLE IF NOT EXISTS index_outbox (
  memory_id TEXT PRIMARY KEY,
  op TEXT NOT NULL CHECK(op IN ('upsert', 'delete')),
  attempts INTEGER NOT NULL DEFAULT 0,
  next_retry_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

- `events_fts.content` 改存 jieba 分词后的 token 串；事件原文仍从 `events.content` 读取。
- 事件插入：同一个 SQLite 事务内写 `events` + `events_fts` + `index_outbox(upsert)`。
- 事件删除/90 天清理：同一个事务内删 `events` + `events_fts` + 写 `index_outbox(delete)`。

## 4. 行为

### 4.1 置信度

```python
def effective_confidence(base: float, updated_at: str, now: datetime) -> float:
    days = max(0.0, (now - parse_iso(updated_at)).total_seconds() / 86400)
    return max(0.3, base * (0.5 ** (days / 90)))
```

- 新经验：`base=0.6`，锚点=当前时间。
- `reinforce`：先算有效值，再 `base = min(1.0, effective + 0.2)`，锚点=当前时间。
- `replace`：`base=1.0`，锚点=当前时间。
- 检索、UI 展示、agent 格式化均使用有效值（保留两位小数）。
- 经验检索**不做**置信度过滤或加权。

### 4.2 删除与恢复

- `delete` 硬删 `experiences` 行与 FTS 行，并写入 `experience_events(action='delete', snapshot=<完整 JSON>)`。
- 同一事务写 `index_outbox(delete)`；向量删除由索引器异步完成。
- 读取路径必须回 SQLite join；SQLite 不存在的 id 直接丢弃，因此向量删除延迟不会暴露已删数据。
- 提供 `ExperienceEngine.restore(event_id)`：从 `snapshot` 重建行、重建 FTS、写 `index_outbox(upsert)`、记录 `restore`。
- 不要求 UI 提供恢复入口；恢复能力需有单元测试。

### 4.3 检索

- 事件：向量 + BM25 并发，RRF 融合；BM25 使用 jieba 分词。
- 经验：向量 + BM25 并发，RRF 融合；BM25 使用 jieba 分词；融合后按 `exp_id` 回 SQLite 取 `content/confidence`。
- `min_score` 只过滤向量候选，不得丢弃 BM25-only 候选。
- 经验结果格式化：

```text
- [exp_xxx] [置信度 0.42] 遇到……时，应该……
```

- 事件结果格式不变。

### 4.4 中文分词

- 新增 `filters.tokenize_for_fts(text)`：`jieba.cut_for_search`，过滤空白与纯标点，空格连接。
- `events_fts` 与 `experiences_fts` 都索引 token 串。
- `build_fts_query(query)` 先用 jieba 分词，再拼 `"token"* AND ...`。
- BM25 查询零结果时，用 OR 形式重试一次。
- 不要求用户使用英文；`jieba>=0.42.1` 已是项目依赖。

### 4.5 图谱

- `GraphEngine.decay_edges` 改用 `max(0.3, confidence * 0.5 ** (days / 90))`。
- 保留每日调度；`days < 1` 的边跳过。
- 其余图谱行为不变。

### 4.6 Memo 工具

`action` 扩展为：

| action | 参数 | 行为 |
|---|---|---|
| `add` | `memory_data` | 原有 pending 流程不变 |
| `search` | `query` | 返回含 `exp_id` 与置信度的结果 |
| `reinforce` | `experience_id` | 同步 +0.2，返回旧/新有效置信度 |
| `replace` | `experience_id`, `content` | 同步覆盖内容，置信度=1.0，记录快照 |
| `delete` | `experience_id` | 同步硬删，写证据日志 |

- `reinforce/replace/delete` 不要求 `reason` 字段；证据日志自动记录 action 与时间。
- 非法/不存在的 `experience_id` 返回明确错误，不静默成功。

### 4.7 索引器与对账

- 新增 `core/index_worker.py`：轮询两个库的 `index_outbox`，调用 `VectorEngine` 完成 Chroma upsert/delete。
- 失败：`attempts += 1`，指数退避（上限 300 秒）；成功后删除 outbox 行。
- 启动时与每日执行一次对账：
  - 删除 Chroma 中 SQLite 已不存在的事件/经验向量；
  - 为 SQLite 中存在但 Chroma 缺失的记录补投 `upsert`。
- `VectorEngine` 新增 `list_event_ids()`、`list_experience_ids()`、`delete_event_vectors(ids)`。

## 5. 验收标准

- **AC-1** 新经验写入 SQLite 后，`confidence=0.6`；读取 90 天后有效置信度约为 0.3。
- **AC-2** `reinforce` 先按锚点计算有效值再加 0.2；连续调用不超过 1.0。
- **AC-3** `replace` 保持 `exp_id` 不变、更新内容与 `content_hash`、置信度=1.0、写快照。
- **AC-4** `delete` 后 SQLite/FTS 均查不到；证据日志保留完整快照；`restore` 可恢复并可被检索。
- **AC-5** 事件与经验的插入/删除均在同一个 SQLite 事务内写对应 `index_outbox`；索引器处理后 Chroma 与 SQLite ID 集合一致。
- **AC-6** 删除后即使 Chroma 向量尚未删除，检索也不会返回该记录。
- **AC-7** 中文查询“路径 空格 启动失败”能通过 BM25 命中含“路径包含空格导致启动失败”的事件；英文查询行为不退化。
- **AC-8** 经验检索返回 `exp_id` 与有效置信度；置信度不参与排序。
- **AC-9** `Memo` 的 `reinforce/replace/delete` 同步生效，不需要等待 worker。
- **AC-10** 图谱边 90 天衰减到约 0.3，且不低于 0.3；`days < 1` 不写入。
- **AC-11** 迁移脚本 `--dry-run` 输出待迁移经验数、画像数、事件 FTS 行数、孤儿向量数；正式执行可重复运行且不产生重复数据。
- **AC-12** 现有 SPEC-012/SPEC-039 中未被本 Spec 修改的行为仍然通过测试。

## 6. 迁移

入口：`python -m src.memory.migrate_v2 [--dry-run]`

1. 停 worker；备份 `~/.purrcat/data/memory/`（chromadb、events.db、graph.pkl）。
2. 创建 `experiences.db` 及表；写入 `schema_meta(version='2')`。
3. 分页读取 Chroma `experiences` collection，回填：
   - `exp_id` 保留原 ID；
   - `content`=document；
   - `confidence=0.6`，`confidence_updated_at=迁移时间`（不得用历史 timestamp）；
   - `created_at` 取 metadata.timestamp，缺失用迁移时间。
4. 用 `tokenize_for_fts` 重建 `experiences_fts`。
5. 用 `tokenize_for_fts` 重建 `events_fts`。
6. 对账事件向量：统计并删除 SQLite 中不存在的事件向量。
7. 统计并输出：Chroma 经验数、SQLite 经验数、FTS 行数、孤儿向量数。
8. 恢复 worker；索引器接管后续增量。

## 7. 非目标

- 不做跨库强事务；不引入 `sqlite-vec`。
- 不做 `problem/solution` 的 LLM 自动抽取；字段先保留为可空。
- 不改 `MEMORY.md` 的生成来源与语义。
- 不要求用户改用英文检索。
- 不重做 builtin-memory 页面布局，只增加置信度/ID 展示。

## 8. 测试矩阵

| 层级 | 文件 | 覆盖 |
|---|---|---|
| L0 | `test_memory_scoring.py`（增补） | 指数衰减、边界、jieba 查询构造 |
| L0 | `test_memory_formatting.py`（更新） | 经验行包含 ID/置信度；事件格式不变 |
| L1 | `test_experience_engine.py`（新增） | add/reinforce/replace/delete/restore、证据、FTS、outbox |
| L1 | `test_event_index_consistency.py`（新增） | 事件插入/删除 outbox、孤儿清理 |
| L1 | `test_memo_experience_actions.py`（新增） | reinforce/replace/delete 同步语义与错误路径 |
| L1 | `test_memory_migration.py`（新增） | dry-run、幂等、回填字段 |

## 9. 风险与回滚

- **FTS 重建失败**：先备份 `events.db`；重建在事务中执行，失败回滚。
- **迁移重复执行**：以 `schema_meta.version` 与 `content_hash` 唯一约束保证幂等。
- **索引器与 worker 并发**：outbox 用 SQLite 事务与单行 upsert；经验写操作加进程内锁。
- **回滚**：恢复备份目录即可；硬删记录只能靠 `experience_events` 快照恢复。
