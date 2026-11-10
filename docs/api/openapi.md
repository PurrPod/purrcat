# PurrCat API 参考（生成物）

> 本文件由 `scripts/gen_api_docs.py` 从 FastAPI 契约自动生成，禁止手动修改。
> 更新：`uv run python scripts/gen_api_docs.py`
> 校验：`uv run python scripts/check_api_docs.py`

## ACP Gateway

### `GET /acp/file`

**标题**：Acp Download File

下载 sandbox 文件（仅允许 /agent_vm 前缀，防任意路径读取）

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | query | string | 是 |  |
| x-purrcat-token | header | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /acp/file`

**标题**：Acp Upload File

multipart 上传：落 agent_vm/sensor/files/acp/，返回 sandbox 路径供 prompt 引用

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session | query | string | 否 |  |
| x-purrcat-token | header | string | 否 |  |

#### 请求体

**Schema**：`Body_acp_upload_file_acp_file_post`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /acp/rpc`

**标题**：Acp Rpc

JSON-RPC 2.0 单条分发（v1 不做 batch）——直调 dispatch

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| x-purrcat-token | header | string | 否 |  |

#### 请求体

**Schema**：`Req`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /acp/stream`

**标题**：Acp Stream

SSE：按 ACP session 订阅对应 purrcat 会话的事件流

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session | query | string | 是 |  |
| x-purrcat-token | header | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## Agent Requests

### `GET /api/requests`

**标题**：List Pending Requests Api

获取前端需要弹窗提示的所有待处理请求

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/requests/resolved`

**标题**：List Resolved Requests Api

获取所有已处理完毕的请求

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `DELETE /api/requests/{req_id}`

**标题**：Delete Request Api

彻底删除某个请求记录

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| req_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/requests/{req_id}/resolve`

**标题**：Resolve Request Api

前端点同意、拒绝或忽略时调用

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| req_id | path | string | 是 |  |

#### 请求体

**Schema**：`ResolveRequestReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| approved | boolean | 否 |  |
| feedback | string | 否 |  |
| ignore | boolean | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## Chat & Sessions

### `GET /api/agent/token`

**标题**：Get Token Status Api

获取上下文 Token 使用进度 + 本会话累计消耗。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/chat`

**标题**：Chat

#### 请求体

**Schema**：`ChatReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| session_id | string | 是 |  |
| message | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/chat/batch`

**标题**：Chat Batch

#### 请求体

**Schema**：`ChatBatchReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| session_id | string | 否 |  |
| events | array[object] | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/chat/compress-memory`

**标题**：Compress Memory Api

🌟 手动触发 Agent 记忆压缩：全局大总结并截断历史上下文
（内部需调用 LLM 生成摘要，耗时较长，放后台任务避免 HTTP 超时）

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/chat/interrupt`

**标题**：Force Interrupt Api

🌟 人类强制打断：物理掐断 Agent 正在执行的工具（子进程 terminate），
隔离旧响应并注入打断提示，Agent 立即回到 idle 状态

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/sessions`

**标题**：Get Sessions

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/sessions/new`

**标题**：Create New Session

#### 请求体

**Schema**：`NewSessionReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| alias | string | 否 |  |
| paradigm | string | 否 |  |
| project_id | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/sessions/{session_id}`

**标题**：Get Session History Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |
| branch_id | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `DELETE /api/sessions/{session_id}`

**标题**：Delete Session Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/sessions/{session_id}/branch`

**标题**：Branch Session Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 请求体

**Schema**：`BranchSessionReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| alias | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/sessions/{session_id}/branches`

**标题**：Get Session Branches Api

🌟 新增：获取当前会话下所有活跃或已完成的子分支元数据

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `DELETE /api/sessions/{session_id}/branches/{branch_id}`

**标题**：Delete Session Branch Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |
| branch_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/sessions/{session_id}/checkout`

**标题**：Checkout Session Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/sessions/{session_id}/paradigm`

**标题**：Get Session Paradigm Api

读取某会话当前绑定的 Agent Loop（paradigm）；空串表示使用默认 PARADIGM。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/sessions/{session_id}/paradigm`

**标题**：Switch Session Paradigm Api

会话暂停时热切换 Agent Loop（只换循环逻辑，不动系统提示词，保留 KV Cache）。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 请求体

**Schema**：`ParadigmSwitchReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| paradigm | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `PUT /api/sessions/{session_id}/project`

**标题**：Move Session Project Api

把会话归入某个项目；project_id 为空表示移回「未分类」。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 请求体

**Schema**：`MoveSessionProjectReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| project_id | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `PUT /api/sessions/{session_id}/rename`

**标题**：Rename Session Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 请求体

**Schema**：`RenameSessionReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| alias | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/sessions/{session_id}/status`

**标题**：Get Session Status

轻量级轮询接口：检查当前会话的后台 Agent 是否还在活跃运行

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| session_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## Configuration

### `GET /api/config/acp`

**标题**：Api Get Acp Status

ACP 接入状态：relay 部署情况 / 端口 / uv 可用性

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/config/acp`

**标题**：Api Update Acp Config

更新 ACP 接入设置（目前仅后端端口，写入 settings.json 的 acp_port）

#### 请求体

**Schema**：`Payload`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/config/acp/redeploy`

**标题**：Api Redeploy Acp Relay

重新部署 relay 脚本（文件被误删 / 版本落后时的一键修复）

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/config/acp/reset-token`

**标题**：Api Reset Acp Token

重置 ACP 网关 token（旧令牌立即失效；客户端侧 relay 需重启后重连）

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/config/change-data-root`

**标题**：Api Change Data Root

#### 请求体

**Schema**：`Payload`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/cron`

**标题**：Api Get Cron Config

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/config/cron`

**标题**：Api Update Cron Config

#### 请求体

**Schema**：`Config`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/deploy`

**标题**：Api Get Deploy Overview

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/config/deploy/disk`

**标题**：Api Get Disk Status

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/config/deploy/disk/compact`

**标题**：Api Compact Disk

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/config/deploy/disk/prune`

**标题**：Api Prune Disk

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/config/deploy/disk/rebuild`

**标题**：Api Rebuild Sandbox

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/config/deploy/{item}`

**标题**：Api Deploy Item

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| item | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/file`

**标题**：Api Get File Config

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/config/file`

**标题**：Api Update File Config

#### 请求体

**Schema**：`Config`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/info`

**标题**：Api Get Info Config

读取 .purrcat/core/info.json，提供 skills 和 workshops 列表

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/config/markdown/{filename}`

**标题**：Api Get Markdown File

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| filename | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `PUT /api/config/markdown/{filename}`

**标题**：Api Update Markdown File

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| filename | path | string | 是 |  |

#### 请求体

**Schema**：`Payload`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/mcp`

**标题**：Api Get Mcp Config

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/config/mcp`

**标题**：Api Update Mcp Config

#### 请求体

**Schema**：`Config`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/config/mcp/reload`

**标题**：Api Reload Mcp Runtime

重新握手所有 MCP Server（新增的即时拉起、改配置的自动重启子进程），
重建 schema 缓存并热更新内存检索树

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/config/meta`

**标题**：Api Get Config Meta

返回当前正在生效的路径常量，便于前端显示给用户做参考。

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/config/model`

**标题**：Api Get Model Config

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/config/model`

**标题**：Api Update Model Config

#### 请求体

**Schema**：`Config`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/sandbox-registry`

**标题**：Api Get Sandbox Registry

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/config/sandbox-registry`

**标题**：Api Update Sandbox Registry

#### 请求体

**Schema**：`Payload`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/sensor`

**标题**：Api Get Sensor Config

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/config/sensor`

**标题**：Api Update Sensor Config

#### 请求体

**Schema**：`Config`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/config/sensor/reload`

**标题**：Api Reload Sensor Manager

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/config/sensor/runtime`

**标题**：Api Get Sensor Runtime

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/config/sensor/{name}/purge`

**标题**：Api Purge Sensor

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/config/sensor/{name}/restart`

**标题**：Api Restart Sensor

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/config/sensor/{name}/stop`

**标题**：Api Stop Sensor

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/config/setup-data-root`

**标题**：Api Setup Data Root

#### 请求体

**Schema**：`Payload`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/config/setup-status`

**标题**：Api Setup Status

首启引导用：数据盘是否已配置（配置过就不再弹引导）

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

## DAG Graphs

### `GET /api/graphs`

**标题**：List Graphs Api

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/graphs/nodes`

**标题**：Get All Nodes Api

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/graphs/{name}`

**标题**：Get Graph Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/graphs/{name}`

**标题**：Save Graph Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 请求体

**Schema**：`Graph Data`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/graphs/{name}/schema`

**标题**：Get Graph Schema Api

获取工作流的全局输入参数 Schema，前端可据此动态生成参数填写表单

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## Default

### `GET /api/health`

**标题**：Ping

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

## Evolution Factory

### `GET /api/evolve/diff`

**标题**：Get Diff Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| name | query | string | 是 |  |
| type | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/evolve/file`

**标题**：Get File Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| name | query | string | 是 |  |
| type | query | string | 否 |  |
| filename | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `PUT /api/evolve/file`

**标题**：Update File Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| name | query | string | 是 |  |
| filename | query | string | 是 |  |
| type | query | string | 否 |  |

#### 请求体

**Schema**：`FileUpdateReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| content | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/evolve/handle`

**标题**：Handle Request Api

#### 请求体

**Schema**：`HandleReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| type | string | 否 |  |
| workplace_id | string | 是 |  |
| name | string | 是 |  |
| is_approved | boolean | 是 |  |
| reject_reason | string \| null | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/evolve/init`

**标题**：Init Sandbox Api

#### 请求体

**Schema**：`InitReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| type | string | 否 |  |
| name | string | 是 |  |
| is_upgrade | boolean | 是 |  |
| goal | string | 否 |  |
| trace | boolean | 否 |  |
| session_id | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/evolve/list`

**标题**：List Workplaces

扫描指定加工厂的沙盒列表

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| type | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/evolve/paradigm`

**标题**：Get Sandbox Paradigm Api

读取沙盒内 AgentLoop 范式（YAML）并解析为结构化对象（供面板编辑器加载）。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| name | query | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/evolve/paradigm`

**标题**：Save Sandbox Paradigm Api

把结构化对象序列化回沙盒内 <name>.yaml（面板编辑器的「保存到沙盒」）。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| name | query | string | 是 |  |

#### 请求体

**Schema**：`ParadigmSaveReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| data | object | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/evolve/rollback`

**标题**：Rollback Skill Api

#### 请求体

**Schema**：`RollbackReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| type | string | 否 |  |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/evolve/test/benchmark`

**标题**：Get Benchmark Api

读取某轮体检的结构化结论（benchmark.json），供前端展示逐条判据与未覆盖项

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| type | query | string | 否 |  |
| iteration | query | integer \| null | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/evolve/test/iterations`

**标题**：List Iterations Api

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| type | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/evolve/test/report`

**标题**：Get Eval Report Api

读取某轮评测的 HTML 报告（report.html）。报告即输出物，不再返回文件清单。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | query | string | 是 |  |
| name | query | string | 是 |  |
| type | query | string | 否 |  |
| iteration | query | integer \| null | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/evolve/test/run`

**标题**：Run Evals Api

#### 请求体

**Schema**：`TestRunReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| type | string | 否 |  |
| workplace_id | string | 是 |  |
| name | string | 是 |  |
| session_id | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `DELETE /api/evolve/workplace/{workplace_id}`

**标题**：Delete Workplace Api

前端手动彻底删除工厂沙盒

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| workplace_id | path | string | 是 |  |
| type | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## Memory System

### `GET /api/memory/events`

**标题**：Get Events

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `DELETE /api/memory/events/{event_id}`

**标题**：Delete Event

删除事件 (SQLite + FTS5)

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| event_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/memory/experiences`

**标题**：Get Experiences

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `DELETE /api/memory/experiences/{exp_id}`

**标题**：Delete Experience

删除工作经验 (VectorDB)

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| exp_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/memory/graph`

**标题**：Get Graph

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `DELETE /api/memory/graph/relation`

**标题**：Delete Relation

物理删除图谱关系边

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| source_node_id | query | string | 是 |  |
| target_node_id | query | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/memory/markdown`

**标题**：Get Memory Markdown Api

读取 .purrcat/core/MEMORY.md 文件内容

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/memory/markdown`

**标题**：Update Memory Markdown Api

保存并覆盖写入 .purrcat/core/MEMORY.md 文件

#### 请求体

**Schema**：`Payload`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/memory/search`

**标题**：Search

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| q | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## Paradigms

### `GET /api/paradigms`

**标题**：List Paradigms Api

列出 paradigms 目录下所有可编辑文件。

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | object |

### `GET /api/paradigms/{name}`

**标题**：Get Paradigm Api

读取某个 paradigm 的完整结构化内容（含 hooks）。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/paradigms/{name}`

**标题**：Save Paradigm Api

整体写回（新建/保存同一接口）。body: { "data": {...} }

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 请求体

**Schema**：`Body`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

### `DELETE /api/paradigms/{name}`

**标题**：Delete Paradigm Api

删除指定 paradigm（默认 PARADIGM.yaml 除外）。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | object |
| 422 | Validation Error | HTTPValidationError |

## Projects

### `GET /api/projects`

**标题**：List Projects Api

列出全部项目（按创建时间升序），附带各自的会话数量。

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/projects`

**标题**：Create Project Api

新建项目：创建项目文件夹与 MEMORY.md（仅写入自身位置），并写入索引。

#### 请求体

**Schema**：`ProjectCreateReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `PUT /api/projects/{project_id}`

**标题**：Update Project Api

更新项目名称。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| project_id | path | string | 是 |  |

#### 请求体

**Schema**：`ProjectUpdateReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string \| null | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `DELETE /api/projects/{project_id}`

**标题**：Delete Project Api

删除项目。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| project_id | path | string | 是 |  |
| delete_sessions | query | boolean | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## System Environment

### `GET /api/system/agent/stats`

**标题**：Get Agent Stats

前端首页调用：返回今日调用统计 + 热力图

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/system/agent/upload`

**标题**：Upload Buffer File

上传单个文件到 agent_vm/.buffer/upload 目录，供 Agent 读取。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| filename | query | string \| null | 否 |  |

#### 请求体

**Schema**：`Body_upload_buffer_file_api_system_agent_upload_post`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/system/container-engine`

**标题**：Get Container Engine Info

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/system/env-status`

**标题**：Get Environment Status

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | EnvStatusResponse |

### `GET /api/system/env/detect`

**标题**：Detect Environment

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | DetectResponse |

### `POST /api/system/env/install`

**标题**：Trigger Install

#### 请求体

**Schema**：`InstallRequest`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| engine | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | InstallStatusResponse |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/system/env/install/status`

**标题**：Get Install Status

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | InstallStatusResponse |

### `GET /api/system/env/status`

**标题**：Get Env Status Simple

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/system/image-status`

**标题**：Get Image Status

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| image_name | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | ImageStatusResponse |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/system/image/pull`

**标题**：Pull Image

#### 请求体

**Schema**：`PullImageRequest`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| image_name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | PullImageResponse |
| 422 | Validation Error | HTTPValidationError |

## Tasks

### `GET /api/tasks`

**标题**：List Tasks Api

获取任务列表：正确使用重构后的 API，合并磁盘与内存

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tasks/run`

**标题**：Run Task Api

创建并启动新任务：接收工作流名称和初始输入参数，抛入后台异步执行

#### 请求体

**Schema**：`RunTaskRequest`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| task_name | string | 是 |  |
| graph_name | string | 是 |  |
| inputs | object | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `DELETE /api/tasks/{task_id}`

**标题**：Delete Task Endpoint

删除任务：使用安全的物理删除 API，同时支持清理休眠和活跃任务

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tasks/{task_id}/artifact`

**标题**：Get Task Artifact

按 purrcat:// URI（或绝对路径兜底）返回任务产物文件，供前端 preview 渲染

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |
| uri | query | string | 是 |  |
| mime | query | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tasks/{task_id}/log`

**标题**：Get Task Log Endpoint

统一日志读取（直接读纯文本盘，绝不瞎唤醒休眠引擎）

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/tasks/{task_id}/nodes/{node_id}/reset`

**标题**：Reset Node Api

供前端点击重置节点后调用，触发级联清理及引擎重启。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |
| node_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/tasks/{task_id}/push`

**标题**：Push To Task

精确注入：只向指定 Agent 节点注入（任务必须在内存中处于活跃状态）

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |

#### 请求体

**Schema**：`TaskPushReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| message | string | 是 |  |
| node_id | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tasks/{task_id}/state`

**标题**：Get Task State Endpoint

获取极简的统一状态，并拼装出前端气泡需要的 memory (支持活跃与休眠任务)

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/tasks/{task_id}/stop`

**标题**：Stop Task Api

优雅终止运行中的任务：与 DELETE 不同，这里只杀死进程但保留 checkpoint 供后续查看

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/tasks/{task_id}/submit`

**标题**：Submit Instruction Api

注入人工指令（任务必须在内存中处于活跃状态）

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| task_id | path | string | 是 |  |

#### 请求体

**Schema**：`SubmitInstructionRequest`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| node_id | string | 是 |  |
| content | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## Tools Management

### `GET /api/tools/cron`

**标题**：Get Crons Api

读取 cron.json 返回现有闹钟列表

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/cron`

**标题**：Add Cron Api

添加闹钟

#### 请求体

**Schema**：`AddCronReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| title | string | 是 |  |
| trigger_time | string | 是 |  |
| repeat_rule | string | 否 |  |
| task_hook | string | 否 |  |
| task_inputs | object | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `DELETE /api/tools/cron/{identifier}`

**标题**：Delete Cron Api

删除闹钟 (支持传 id 或 title)

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| identifier | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/heartbeat`

**标题**：Get Heartbeat Api

获取心跳配置 + GOAL.md 当前内容

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/heartbeat`

**标题**：Save Heartbeat Api

保存心跳配置；开启心跳时必须提交非空 GOAL.md 内容

#### 请求体

**Schema**：`HeartbeatReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| interval | integer | 是 |  |
| active | boolean | 是 |  |
| goal | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/agentloops`

**标题**：Get Agentloop Registry Api

从官方 PurrPod/agentloops 仓库拉取 registry.json 返回前端市场

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/agentloops/install`

**标题**：Install Agentloop Api

安装 AgentLoop（范式 YAML）到 ~/.purrcat/paradigms 并校验 hooks。

#### 请求体

**Schema**：`InstallAgentloopReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/agentloops/installed`

**标题**：List Installed Agentloops Api

返回 paradigms 目录（~/.purrcat/paradigms）下已安装的 AgentLoop 名字列表

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/agentloops/uninstall`

**标题**：Uninstall Agentloop Api

卸载 AgentLoop：删除 paradigms 目录下对应的 YAML（默认 PARADIGM 除外）。

#### 请求体

**Schema**：`UninstallAgentloopReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/graphs`

**标题**：Get Graph Registry Api

从官方 PurrPod/graphs 仓库拉取 registry.json 返回前端市场

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/graphs/install`

**标题**：Install Graph Api

安装 Graph（文件夹结构）并补齐其声明的 mcp/skill 依赖。

#### 请求体

**Schema**：`InstallGraphReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/graphs/installed`

**标题**：List Installed Graphs Api

返回 ~/.purrcat/graph 目录下已安装的 graph（文件夹结构）名字列表

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/graphs/uninstall`

**标题**：Uninstall Graph Api

删除 {GRAPHS_DIR}/{name} 文件夹（新目录结构）

#### 请求体

**Schema**：`UninstallGraphReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/sensors`

**标题**：Get Sensor Registry Api

从官方 PurrPod/sensors 仓库拉取 registry.json 返回给前端市场

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/sensors/install`

**标题**：Install Sensor Api

安装 Sensor：合并配置落盘并下载代码（支持覆盖式重新下载）。

#### 请求体

**Schema**：`InstallSensorReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| sensor | object | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/sensors/installed`

**标题**：List Installed Sensors Api

返回 activate_sensor.json 中已配置（不管 enabled）的传感器名列表

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/sensors/uninstall`

**标题**：Uninstall Sensor Api

从 activate_sensor.json 移除该 Sensor 并删除本地代码文件

#### 请求体

**Schema**：`UninstallSensorReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/ui-plugins`

**标题**：Get Ui Plugin Registry Api

从官方 PurrPod/ui-plugins 仓库拉取 registry.json 返回前端市场

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/ui-plugins/install`

**标题**：Install Ui Plugin Api

安装 UI 插件到其注册表条目声明的 root，并递归补齐依赖。

#### 请求体

**Schema**：`InstallUiPluginReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/market/ui-plugins/installed`

**标题**：List Installed Ui Plugins Api

返回已安装的 UI 插件名字列表（用户根 + 沙盒根两个可写根合并去重）

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/market/ui-plugins/uninstall`

**标题**：Uninstall Ui Plugin Api

卸载 UI 插件：在用户根 / 沙盒根中找到该插件目录，移动为同根下的 <name>.trash（可恢复）。

#### 请求体

**Schema**：`UninstallUiPluginReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/mcp`

**标题**：Get Mcp Tools Api

获取内存/缓存里的 MCP 服务器及其包含的工具名称和描述

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/mcp/install`

**标题**：Install Mcp Api

解析并合并用户传入的 MCP Server JSON 配置，落盘并热更新；官方 MCP 额外下载源码

#### 请求体

**Schema**：`InstallMCPReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| config_json | string | 是 |  |
| repo | string | 否 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/mcp/list`

**标题**：List Configured Mcps Api

返回 mcp_config.json 中已配置的 MCP Server 名称列表

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/mcp/refresh`

**标题**：Refresh Mcp Api

手动刷新 MCP Schema 并更新内存检索树

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/mcp/uninstall`

**标题**：Uninstall Mcp Api

从 mcp_config.json 移除该 Server，清理本地源码并热更新 Schema

#### 请求体

**Schema**：`UninstallMCPReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/tools/skills`

**标题**：Get Skills Api

获取内存里的 Skill 名称和描述

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/skills/install`

**标题**：Install Skill Api

根据 GitHub URL 下载第三方 Skill 并热更新内存

#### 请求体

**Schema**：`InstallSkillReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| url | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/tools/skills/install-batch`

**标题**：Install Skills Batch Api

批量下载多个第三方 Skill 并热更新内存（同一仓库 zip 只下载一次）

#### 请求体

**Schema**：`InstallSkillsBatchReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| urls | array[object] | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/tools/skills/refresh`

**标题**：Refresh Skills Api

手动扫描本地 Skill 文件夹并更新内存检索树

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/tools/skills/uninstall`

**标题**：Uninstall Skill Api

删除本地已安装的 Skill（目录名或 SKILL.md 的 name 匹配），并热更新内存

#### 请求体

**Schema**：`UninstallSkillReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| name | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## UI Direct File Access

### `POST /api/filesystem/ack`

**标题**：Ui Ack Action

用户确认更改，删除磁盘备份，解决空间膨胀

#### 请求体

**Schema**：`UIRollbackReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| path | string | 是 |  |
| backup_id | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/filesystem/ack_all`

**标题**：Ui Ack All Action

一键接受全部更改：对所有未确认变更执行 ack，清理全部备份

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/filesystem/backups`

**标题**：Api Get Valid Backups

提供给前端：校验哪些快照还在硬盘上存活

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/filesystem/diffs`

**标题**：Api Get Global Diffs

🌟 新增：提供给前端全局读取所有未确认的代码变更 (DiffView)

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/filesystem/history_list`

**标题**：Get History List

直接读取 .agent_history 目录，返回真实存在的备份文件列表

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `GET /api/filesystem/list`

**标题**：List Directory

列出目录内容，返回 { name, isDir, path }[]

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | query | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/filesystem/preview`

**标题**：Preview File

接收绝对路径，返回文件流给前端预览。
用于绕过浏览器对 file:// 协议的同源与安全限制。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | query | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/filesystem/read`

**标题**：Read File

读取文件文本内容（/agent_vm 沙盒路径自动转换，含 agent_vm 层缺失回退）

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | query | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/filesystem/resolve`

**标题**：Resolve Path

返回沙盒/相对路径对应的宿主机真实绝对路径。
供前端构造 file:// URL，在内置浏览器中打开本地 HTML/SVG
（复用内置浏览器的元素 pick + 评论能力）。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | query | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/filesystem/stat`

**标题**：Stat File

文件元信息（大小），IDE 大文件拦截用

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| path | query | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/filesystem/undo`

**标题**：Ui Undo Action

提供给前端 UI 的一键回滚（最高权限）

#### 请求体

**Schema**：`UIRollbackReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| path | string | 是 |  |
| backup_id | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/filesystem/write`

**标题**：Write File

写入文件文本内容（自动创建父目录，/agent_vm 沙盒路径自动转换）

#### 请求体

**Schema**：`UIWriteReq`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| path | string | 是 |  |
| content | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

## WebMinimal

### `GET /api/webmin/config`

**标题**：Api Webmin Get Config

读取插件配置：{ "plugins": { plugin_id: config } }。

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `PUT /api/webmin/config`

**标题**：Api Webmin Put Config

按分节更新宿主配置（plugins / rail / active），未提供的分节保持原值。

#### 请求体

**Schema**：`Body`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/webmin/manifest`

**标题**：Api Webmin Manifest

返回当前已扫描到的全部插件列表（未新增插件即热插拔可感知）。

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |

### `POST /api/webmin/plugin-backend/{plugin_id}/{action}`

**标题**：Api Webmin Plugin Backend

插件后端子进程生命周期：start / stop / restart / status。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 |  |
| action | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/webmin/plugin-dir/{plugin_id}/{path}`

**标题**：Api Webmin Plugin Dir

列出插件目录内某一层的子项（仅名字与是否目录），供插件自动扫描自身数据目录。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 |  |
| path | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/webmin/plugin-rpc/{plugin_id}/{handler}`

**标题**：Api Webmin Plugin Rpc

调用插件自带的后端子进程 handler（RPC）。body: { payload?, timeout? }。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 |  |
| handler | path | string | 是 |  |

#### 请求体

**Schema**：`Body`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/webmin/plugin/{plugin_id}/delete`

**标题**：Api Webmin Delete Plugin

删除插件：用户/沙盒插件移动为各自根目录下的 <id>.trash（可恢复），内置拒绝。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/webmin/plugin/{plugin_id}/{path}`

**标题**：Api Webmin Plugin

按路径读取插件目录内静态文件；未指定路径时回退到 descriptor 的 entry。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| plugin_id | path | string | 是 |  |
| path | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `POST /api/webmin/wallpaper`

**标题**：Api Webmin Import Wallpaper

把用户选择的本地壁纸复制进托管目录，返回可访问的 URL。body: { path }。

#### 请求体

**Schema**：`Body`

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |

### `GET /api/webmin/wallpaper/{filename}`

**标题**：Api Webmin Serve Wallpaper

静态托管壁纸文件（沙箱到 WALLPAPER_DIR 防穿越）。

#### 参数

| 名称 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| filename | path | string | 是 |  |

#### 响应

| 状态码 | 描述 | Schema |
| --- | --- | --- |
| 200 | Successful Response | - |
| 422 | Validation Error | HTTPValidationError |
