# 后端 API 总览

覆盖 `src/server` 下的全部接口。**只描述当前接口，不含历史/兼容别名。**

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
| 会话与对话 | `/api` | 17 | [chat.md](chat.md) |
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

> 每种接口的**参数 / 响应 / 调用示例**以“一接口一小节”的形式给出，标题形如 `## GET \`/api/xxx\``。极简模式宿主与 UI 插件的接入方式见 [webmin.md](webmin.md) 与 [插件开发文档](../plugins/README.md)。
