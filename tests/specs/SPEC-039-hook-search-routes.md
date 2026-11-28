# SPEC-039 Hook search 的路由合并、返回条数与置信度过滤

## 目标

让 `search` hook 支持按路由限制返回条数，并新增 `all` 路由（并行检索 `local` 与 `memory` 后合并注入）；
`skill` / `mcp` / `local` 统一按置信度阈值过滤（默认 0.30，可由 `min_score` 覆盖）。
默认范式在 `on_input_received` 阶段只检索 `memory`。

## 验收标准

- [ ] AC-1：`search` 的 `limit` 映射到 `Search(topk=...)` 与 `Memo(query.top_k=...)`；非法值回退 5。
- [ ] AC-2：`limit` 夹紧到 1–15。
- [ ] AC-3：`route: all` 并行调用 `local` 与 `memory`，两段结果以空行拼接注入。
- [ ] AC-4：`route: all` 下单路失败不影响另一路注入，失败信息带路由名。
- [ ] AC-5：默认范式 `on_input_received` 用 `@USERQUERY` 只检索 `memory`。
- [ ] AC-6：`Search` / `raw_search` 的 `skill` / `mcp` / `local` 结果按 `min_score`（默认 0.30）过滤，非法值回退默认并夹紧到 0–1。
- [ ] AC-7：`web` 路由无相似度分数，不参与置信度过滤。
- [ ] AC-8：`search` hook 支持 `min_score`，默认 0.30 且与 `Search` 一致；`memory` 路由用它过滤事件向量相似度、经验向量相似度与图谱节点相似度（含边界），不过滤关系置信度。
- [ ] AC-9：`Search(route='web')` 返回结构化 JSON（`query` / `results[title,url,snippet]` / `hint`），供前端渲染链接卡片。

## 非目标

- 不改变 `local` / `skill` / `mcp` / `web` 原有的检索实现。
- 不改变记忆检索（事件/经验/图谱）的排序与召回逻辑，只在输出前按 `min_score` 过滤；事件分数语义由 SPEC-020 AC-13 定义。
- 不新增 hook 阶段。
