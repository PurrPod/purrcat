# 后端 API 总览

> [!IMPORTANT]
> [`openapi.md`](openapi.md) 与 [`openapi.json`](openapi.json) 是**生成物**，禁止手动修改。
> 更新：`uv run python scripts/gen_api_docs.py`
> 校验（CI 同款）：`uv run python scripts/check_api_docs.py`

## 契约生成物

生成器直接调用 `src/server/app.py` 的 `create_app().openapi()`，因此代码即契约：

- `openapi.json`：FastAPI 契约的稳定序列化（key 排序、无时间戳、末尾换行）。
- `openapi.md`：按 tag → path → 方法（GET/POST/PUT/PATCH/DELETE）排序的可读参考，包含参数、请求体字段与响应 Schema。

`scripts/check_api_docs.py` 只比较生成物与当前代码，不落盘；有差异时退出码为 1。

## 历史文档

本目录下按模块手写的 `chat.md`、`config.md` 等为**历史文档，逐步迁移**，不再作为契约校验依据，请勿删除。新增或修改接口以生成物为准。

## 通用约定

- **基地址**：默认 `http://127.0.0.1:8000`（端口可用环境变量 `PURRCAT_API_PORT` 或 `main.py --api-port` 指定）。
- **数据格式**：除文件上传（`multipart/form-data`）与静态托管外，请求与响应均为 `application/json`。
- **鉴权**：仅 ACP 网关（`/acp/*`）需要，通过请求头 `X-PurrCat-Token` 携带 `~/.purrcat/acp_token` 内容；其余接口无鉴权（本地优先）。
- **错误**：HTTP 状态码 + `{ "detail": "<reason>" }`（FastAPI 默认错误体）。
- **异步语义**：`/api/chat`、`/api/chat/batch`、`/api/chat/compress-memory`、`/api/config/deploy/{item}` 等为**后台异步**接口，立即返回受理态，实际进度走对应轮询/SSE 接口。

## 模块索引

| 模块 | 前缀 | 端点数 | 文档 |
| --- | --- | --- | --- |
| 极简模式插件系统 | `/api/webmin` | 10 | [webmin.md](webmin.md) |
| 会话与对话 | `/api` | 18 | [chat.md](chat.md) |
| 项目（会话分类器） | `/api/projects` | 4 | [projects.md](projects.md) |
| 配置 | `/api/config` | 29 | [config.md](config.md) |
| 工具 | `/api/tools` | 31 | [tools.md](tools.md) |
| 文件系统 | `/api/filesystem` | 12 | [filesystem.md](filesystem.md) |
| 进化工厂 | `/api/evolve` | 12 | [evolve.md](evolve.md) |
| 系统 | `/api/system` | 10 | [system.md](system.md) |
| 任务 | `/api/tasks` | 10 | [task.md](task.md) |
| 记忆 | `/api/memory` | 9 | [memory.md](memory.md) |
| 图谱 | `/api/graphs` | 5 | [graph.md](graph.md) |
| 范式 | `/api/paradigms` | 4 | [paradigms.md](paradigms.md) |
| 待办请求 | `/api/requests` | 4 | [request.md](request.md) |
| ACP 网关 | `/acp` | 4 | [acp.md](acp.md) |
| 终端 WebSocket | `/api/terminal` | 1（WS） | [terminal.md](terminal.md) |
| 通用 | — | 1 | [misc.md](misc.md) |

> 接口按“一接口一小节”给出，标题形如 `## GET \`/api/xxx\``。极简模式宿主与 UI 插件的接入方式见 [webmin.md](webmin.md) 与 [插件开发文档](../plugins/README.md)。
