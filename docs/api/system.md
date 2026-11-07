# 系统 `/api/system`

> 源码：`src/server/api/system.py` ｜ 前缀：`/api/system` ｜ 端点：10 个

运行环境探测、容器引擎/镜像状态、环境安装进度、文件上传与 Agent 使用统计。

---

## GET `/api/system/env/detect`

探测运行环境：返回操作系统、已安装的容器引擎及推荐引擎与原因。

**请求**

无请求参数。

**响应**

```json
{
  "os": "Windows",
  "installed": { "docker": true },
  "recommend": "docker",
  "recommend_reason": "检测到已安装 Docker。"
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/system/env/detect'
```

---

## GET `/api/system/env-status`

环境状态（完整）：检查容器引擎版本并确认 daemon 是否运行，返回是否就绪及错误信息。

**请求**

无请求参数。

**响应**

```json
{
  "is_ready": true,
  "engine": "docker",
  "engine_version": "Docker version 27.x.x, build xxxxx",
  "error": null
}
```

未就绪时 `is_ready` 为 `false`，`error` 携带原因（如 daemon 未启动）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/system/env-status'
```

---

## GET `/api/system/env/status`

环境状态（简化）：仅按可执行文件是否存在判断。

**请求**

无请求参数。

**响应**

```json
{ "ready": true, "engine": "docker", "has_docker": true }
```

未检测到 docker 时 `ready` 为 `false`、`engine` 为 `null`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/system/env/status'
```

---

## GET `/api/system/image-status`

查询容器镜像是否已存在。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| image_name | query | string | 否 | 镜像名，默认 `my_agent_env:latest` |

**响应**

```json
{ "exists": true, "image_name": "my_agent_env:latest", "error": null }
```

镜像不存在时 `exists` 为 `false`；docker 缺失或连接失败时 `error` 携带原因。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/system/image-status?image_name=my_agent_env:latest'
```

---

## POST `/api/system/image/pull`

后台拉取镜像：立即返回已受理，实际进度通过环境安装进度接口查看。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| image_name | body | string | 是 | 要拉取的镜像名 |

**响应**

```json
{ "status": "started", "message": "已开始后台拉取镜像 my_agent_env:latest，请稍候..." }
```

docker 缺失或连接失败返回 500。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/system/image/pull' \
  -H 'Content-Type: application/json' \
  -d '{"image_name": "my_agent_env:latest"}'
```

---

## POST `/api/system/env/install`

触发环境安装：后台异步执行。若已在安装中，则直接返回当前安装态而不会重复触发。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| engine | body | string | 否 | 目标引擎，默认 `docker` |

**响应**

```json
{ "status": "started", "message": "开始安装 docker 环境...", "progress": 0 }
```

已在安装中时返回 `{"status": "installing", "message": "正在安装中，请稍候...", "progress": <当前进度>}`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/system/env/install' \
  -H 'Content-Type: application/json' \
  -d '{"engine": "docker"}'
```

---

## GET `/api/system/env/install/status`

查询环境安装进度。

**请求**

无请求参数。

**响应**

```json
{ "status": "completed", "message": "安装进行中...", "progress": 100 }
```

`status` 取值 `idle` / `installing` / `completed` / `failed`；失败时 `message` 携带错误原因。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/system/env/install/status'
```

---

## GET `/api/system/container-engine`

获取容器引擎信息：当前引擎、版本、可用引擎与已选引擎。

**请求**

无请求参数。

**响应**

```json
{
  "engine": "docker",
  "version": "Docker version 27.x.x, build xxxxx",
  "available_engines": { "docker": true },
  "selected_engine": "docker"
}
```

获取失败返回 500。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/system/container-engine'
```

---

## POST `/api/system/agent/upload`

上传单个文件到 `agent_vm/.buffer/upload` 目录，供 Agent 读取。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| file | body | file | 是 | 上传的文件（`multipart/form-data`） |
| filename | query | string | 否 | 保存文件名；缺省时使用原始文件名或随机名 |

**响应**

```json
{
  "success": true,
  "saved_path": "D:\\cat-in-cup\\agent_vm\\.buffer\\upload\\demo.txt",
  "size_bytes": 1024,
  "agent_path": "D:\\cat-in-cup\\agent_vm\\.buffer\\upload\\demo.txt"
}
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/system/agent/upload?filename=demo.txt' \
  -F 'file=@./demo.txt'
```

---

## GET `/api/system/agent/stats`

前端首页调用：返回今日调用统计与历史热力图。

**请求**

无请求参数。

**响应**

```json
{
  "today": { "calls": 12, "total_tokens": 34567, "cached_tokens": 8901 },
  "heatmap": { "2026-10-14": 12, "2026-10-13": 8 }
}
```

`heatmap` 的键为日期（`YYYY-MM-DD`），值为当日调用次数；无统计文件时各项为 0 / 空对象。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/system/agent/stats'
```
