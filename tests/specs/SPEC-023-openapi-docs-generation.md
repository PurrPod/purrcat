# SPEC-023：API 文档由 FastAPI 契约生成

## 背景

`docs/api/` 一直靠手写 Markdown 维护，`scripts/check_api_docs.py` 用正则从手写文档里抓 `METHOD /path` 与源码路由字符串比对。它只能证明“路径出现过”，无法校验参数、请求体、响应与路由声明是否真的同源，且每加一个接口都要手工补一节文档。

## 行为

- 新增 `src/server/app.py::create_app(port: int | None = None)`：只组装 FastAPI 实例、CORS、15 个 router、健康检查、静态挂载与生命周期钩子，不绑定端口、不起线程、不写运行时状态。
- `main.py` 的 `run_api` 改为 `app = create_app(port)` 后交给 uvicorn；真实服务与离线生成共用同一份路由表。
- 新增 `scripts/gen_api_docs.py`：
  - 默认从 `create_app().openapi()` 生成 `docs/api/openapi.json` 与 `docs/api/openapi.md`；
  - `--check` 只比较不落盘，存在缺失或内容差异时退出码为 1；
  - 输出稳定：JSON key 排序、Markdown 按 tag/path/方法排序，无时间戳与绝对路径。
- `scripts/check_api_docs.py` 保留原命令入口与退出语义，内部改为调用生成器的 check 逻辑。
- `docs/api/README.md` 标注两个生成物禁止手改，旧手写 md 保留并标记为历史文档。

## 验收标准

- [ ] AC-1：`create_app(None)` 不写运行时端口状态，路由集合与 `create_app(8000)` 完全一致。
- [ ] AC-2：`openapi.json` 为 `sort_keys=True` 的稳定 JSON 且末尾换行；二次生成不产生 diff。
- [ ] AC-3：`openapi.md` 按 tag/path/方法排序，包含参数表、请求体字段表（`$ref` 展开一层）与响应 Schema。
- [ ] AC-4：缺失 `summary` 时用 `operationId` 转 Title Case 兜底；空章节不输出。
- [ ] AC-5：`check_api_docs.py` 在生成物一致时退出 0，篡改或缺失时退出 1 并提示更新命令。
- [ ] AC-6：真实应用的 OpenAPI 覆盖 `app.routes` 中全部 `/api` 与 `/acp` HTTP 路由。

## 非目标

- 不给 172 个路由批量补 `summary` / docstring。
- 不删除或改写既有的手写模块文档。
- 不修改任何 `src/server/api/**` 业务路由的行为、路径、方法与注册顺序。
- 不引入 AST 解析或第三方向文档工具。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_api_docs_generator.py` | AC-2、AC-3、AC-4、AC-5、AC-6 |
| L3 | `tests/l3/test_red_lines.py::test_api_docs_match_real_routes` | AC-5 |

## 风险与回滚

- 风险：`create_app()` 会导入全部 router，离线生成因此继承这些模块的导入副作用（如配置目录初始化），但不会启动服务或联网。
- 风险：CI 工作流 `.github/workflows/api-docs.yml` 目前未安装 Python 依赖；生成式校验需要 `fastapi` 等运行依赖，需在 CI 中补充依赖安装。
- 回滚：恢复手写文档校验脚本与 `main.py` 内联构造；生成物可整体删除，`create_app` 不影响线上行为。
