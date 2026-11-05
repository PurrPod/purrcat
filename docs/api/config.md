# 配置 `/api/config`

> 源码：`src/server/api/config.py` ｜ 前缀：`/api/config` ｜ 端点：29 个

配置文件均落盘在 `~/.purrcat` 下（`settings.json` 为内部全局设置，其余为各模块 JSON）。除 ACP 令牌重置、数据根目录迁移等接口外，均为无鉴权本地接口。

## GET `/api/config/model`

读取模型配置（`~/.purrcat/model.json`）。

**请求**

无参数。

**响应**

```json
{
  "main": {
    "openai:deepseek-flash": {
      "api_keys": [""],
      "base_url": "https://api.deepseek.com",
      "max_token": 500000
    }
  },
  "task": {},
  "vision": {}
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/model'
```

---

## PUT `/api/config/model`

更新模型配置（`~/.purrcat/model.json`），整体覆盖写入后立即热重载内存中的 Agent。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `config` | body | object | 是 | 完整模型配置对象，整体覆盖写入，含 `main` / `task` / `vision` 等分段 |

**响应**

```json
{ "status": "ok", "message": "Model config updated and reloaded successfully" }
```

保存失败返回 `500`：`{ "detail": "Failed to save model config" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/model' \
  -H 'Content-Type: application/json' \
  -d '{"main":{"openai:deepseek-v4-flash":{"base_url":"https://api.deepseek.com","max_token":500000}}}'
```

---

## GET `/api/config/sensor`

读取传感器配置（`~/.purrcat/activate_sensor.json`）。结构为「Sensor 名称 → 配置对象」，`enabled=false` 的项不会拉起。

**请求**

无参数。

**响应**

```json
{
  "my_sensor": { "enabled": true }
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/sensor'
```

---

## PUT `/api/config/sensor`

更新传感器配置（`~/.purrcat/activate_sensor.json`），整体覆盖写入。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `config` | body | object | 是 | 完整传感器配置对象，整体覆盖写入 |

**响应**

```json
{ "status": "ok", "message": "Sensor config updated successfully" }
```

保存失败返回 `500`：`{ "detail": "Failed to save sensor config" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/sensor' \
  -H 'Content-Type: application/json' \
  -d '{"my_sensor":{"enabled":true}}'
```

---

## POST `/api/config/sensor/reload`

停止所有运行中的 Sensor 进程，并按 `activate_sensor.json` 重新拉起启用项（热重启）。

**请求**

无参数。

**响应**

```json
{ "status": "ok", "message": "Sensors reloaded successfully" }
```

失败返回 `500`：`{ "detail": "热重启失败: <原因>" }`

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/sensor/reload'
```

---

## GET `/api/config/sensor/runtime`

列出当前由 SensorManager 托管的运行中 Sensor 进程（配置页「后台进程」展示用）。

**请求**

无参数。

**响应**

```json
{
  "running": [
    { "name": "feishu", "pid": 4321, "alive": true },
    { "name": "wechat-clawbot", "pid": 4380, "alive": false }
  ]
}
```

`alive=false` 表示进程引用尚存但进程已退出（下一次 watchdog 巡检会重启它）。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/sensor/runtime'
```

---

## POST `/api/config/sensor/{name}/stop`

停止指定 Sensor：先把 `activate_sensor.json` 里该项置为 `enabled=false`（避免 watchdog 按配置复拉），再整树击杀其进程。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | path | string | 是 | Sensor 名称（对应 `<name>.py`） |

**响应**

```json
{ "status": "ok", "stopped": true, "message": "已停止 Sensor 'feishu' 并置为 enabled=false" }
```

无运行中进程时 `stopped=false`，仍会完成 `enabled=false` 的落盘。禁用配置写入失败返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/sensor/feishu/stop'
```

---

## POST `/api/config/sensor/{name}/purge`

**彻底删除**指定 Sensor（不可恢复）。与普通删除（`PUT /api/config/sensor` 只移除注册项）不同，这里连正式文件一起删。执行顺序：① 从 `activate_sensor.json` 移除该项（先消失，watchdog 才不会在杀进程后的窗口里把它拉起来）→ ② 整树击杀运行中的进程 → ③ 删除 `~/.purrcat/sensor/<name>.py`（优先 `git rm -f` 并提交，非 Git 仓库或未跟踪时退化为直接删文件）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | path | string | 是 | Sensor 名称（对应 `<name>.py`） |

**响应**

```json
{
  "status": "ok",
  "stopped": true,
  "file_deleted": true,
  "message": "已彻底删除 Sensor 'feishu'（进程已停止，文件已删除，配置已移除）"
}
```

文件删除失败返回 `500`（配置此时已被移除）。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/sensor/feishu/purge'
```

---

## POST `/api/config/sensor/{name}/restart`

重启指定 Sensor（配置页「重启」按钮，仅在卡片显示「未运行」时提供）。执行顺序：① 若该项在 `activate_sensor.json` 里为 `enabled=false` 则置回 `true` 并落盘（否则 watchdog 不会复拉）→ ② 整树击杀同名旧进程 → ③ 按当前配置重新 `uv run` 拉起。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `name` | path | string | 是 | Sensor 名称（对应 `<name>.py`） |

**响应**

```json
{ "status": "ok", "started": true, "message": "已重启 Sensor 'feishu'（新进程已拉起）" }
```

- 配置里不存在该 Sensor 时返回 `404`：`{ "detail": "未配置 Sensor 'feishu'，无法重启" }`
- `started=false` 表示新进程未登记成功（本地缺 `<name>.py` 或 `uv` 不可用），此时配置已置为 `enabled=true`，watchdog 会在后续巡检中继续尝试。
- 启用配置写入失败返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/sensor/feishu/restart'
```

---

## GET `/api/config/file`

读取文件权限配置（`~/.purrcat/file.json`），定义 `blocked` / `readonly` / `writable` 三类路径规则与默认权限。

**请求**

无参数。

**响应**

```json
{
  "default_permission": "readonly",
  "permissions": {
    "blocked": [".git", "src", "node_modules", "miniconda3", ".env"],
    "readonly": [],
    "writable": []
  }
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/file'
```

---

## PUT `/api/config/file`

更新文件权限配置（`~/.purrcat/file.json`），整体覆盖写入。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `config` | body | object | 是 | 完整文件配置对象，整体覆盖写入 |

**响应**

```json
{ "status": "ok", "message": "File config updated successfully" }
```

保存失败返回 `500`：`{ "detail": "Failed to save file config" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/file' \
  -H 'Content-Type: application/json' \
  -d '{"default_permission":"readonly","permissions":{"blocked":[".git"],"readonly":[],"writable":[]}}'
```

---

## GET `/api/config/mcp`

读取 MCP 配置（`~/.purrcat/mcp_config.json`），标准 `mcpServers` 结构。

**请求**

无参数。

**响应**

```json
{ "mcpServers": {} }
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/mcp'
```

---

## PUT `/api/config/mcp`

更新 MCP 配置（`~/.purrcat/mcp_config.json`），整体覆盖写入；改配置后需调用 `/mcp/reload` 使其生效。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `config` | body | object | 是 | 完整 MCP 配置对象，整体覆盖写入 |

**响应**

```json
{ "status": "ok", "message": "MCP config updated successfully" }
```

保存失败返回 `500`：`{ "detail": "Failed to save MCP config" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/mcp' \
  -H 'Content-Type: application/json' \
  -d '{"mcpServers":{}}'
```

---

## POST `/api/config/mcp/reload`

重新握手所有 MCP Server（新增项即时拉起、改配置的自动重启子进程），重建 schema 缓存并热更新内存检索树。

**请求**

无参数。

**响应**

```json
{ "status": "ok", "message": "MCP 已重载到内存：检索树已热更新，共 12 个工具" }
```

失败返回 `500`：`{ "detail": "MCP 重载失败: <原因>" }`

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/mcp/reload'
```

---

## GET `/api/config/acp`

读取 ACP 接入状态：relay 部署情况、端口与 `uv` 可用性。

`port` 是 `settings.json` 里的用户期望端口；`actual_port` 是本次运行后端真实 bind 的端口
（写在 `~/.purrcat/runtime.json`）。后端端口自动 fallback 时两者会不一致，此时 ACP relay
按 `actual_port` 连接，`port_mismatch` 为 `true`。

**请求**

无参数。

**响应**

```json
{
  "relay_path": "C:\\Users\\<user>\\.purrcat\\bin\\acp_relay.py",
  "relay_deployed": true,
  "relay_source_found": true,
  "relay_matches_source": true,
  "port": 8000,
  "actual_port": 8001,
  "port_mismatch": true,
  "uv_found": true
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `port` | int | 用户期望端口（`settings.json` 的 `acp_port`，未设置时 8000） |
| `actual_port` | int \| null | 本次运行实际端口；后端未在跑或状态文件非法时为 `null` |
| `port_mismatch` | bool | 期望端口与实际端口不一致（`actual_port` 为 `null` 时为 `false`） |

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/acp'
```

---

## PUT `/api/config/acp`

更新 ACP 接入设置（目前仅后端端口，写入 `settings.json` 的 `acp_port`）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `port` | body | int | 否 | 后端端口，取值 1–65536；缺省则不修改。非法端口返回 `400` |

**响应**

```json
{ "status": "ok", "message": "ACP settings updated" }
```

保存失败返回 `500`：`{ "detail": "保存 acp_port 失败" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/acp' \
  -H 'Content-Type: application/json' \
  -d '{"port":8000}'
```

---

## POST `/api/config/acp/redeploy`

重新部署 relay 脚本（文件被误删 / 版本落后时的一键修复，强制覆盖写入 `~/.purrcat/bin/acp_relay.py`）。

**请求**

无参数。

**响应**

返回当前 ACP 状态并附加 `status`：

```json
{
  "relay_path": "C:\\Users\\<user>\\.purrcat\\bin\\acp_relay.py",
  "relay_deployed": true,
  "relay_source_found": true,
  "relay_matches_source": true,
  "port": 8000,
  "uv_found": true,
  "status": "ok"
}
```

失败返回 `500`：`{ "detail": "部署失败：内置源缺失或写入错误" }`

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/acp/redeploy'
```

---

## POST `/api/config/acp/reset-token`

重置 ACP 网关 token：删除 `~/.purrcat/acp_token` 并立即重新生成。

> ⚠️ 副作用：旧令牌立即失效，客户端侧 relay 需重启后才能用新令牌重连。

**请求**

无参数。

**响应**

```json
{ "status": "ok" }
```

失败返回 `500`：`{ "detail": "token 重置失败: <原因>" }`

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/acp/reset-token'
```

---

## GET `/api/config/deploy`

获取各依赖项就绪状态 + 部署任务进度与日志，供前端轮询。

**请求**

无参数。

**响应**

```json
{
  "items": {
    "uv": { "ready": true, "detail": "uv x.y.z (C:\\...\\uv.exe)" },
    "node": { "ready": false, "detail": "未检测到 node 命令" },
    "sandbox": { "ready": true, "detail": "..." },
    "embedding": { "ready": false, "detail": "嵌入模型未下载（约 120MB）" }
  },
  "tasks": {
    "uv": { "state": "idle", "log": [], "finished_at": null }
  }
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/deploy'
```

---

## POST `/api/config/deploy/{item}`

一键部署指定依赖项，后台线程执行，进度通过 `GET /api/config/deploy` 轮询。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `item` | path | string | 是 | 依赖项标识，取值 `uv` / `node` / `sandbox` / `embedding` |

**响应**

```json
{ "status": "ok", "message": "已开始部署 uv" }
```

未知项或已在部署中返回 `409`：`{ "detail": "<reason>" }`

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/deploy/uv'
```

---

## GET `/api/config/deploy/disk`

只读返回 Docker 数据盘（WSL2 vhdx）的实际占盘、有效数据估算与空洞占比，供部署页轮询。不阻塞、不提权；非 Windows 或未安装 Docker Desktop 时返回 `supported: false`。

**请求**

无参数。

**响应**

```json
{
  "supported": true,
  "vhdx_path": "C:\\Users\\<user>\\AppData\\Local\\Docker\\wsl\\disk\\docker_data.vhdx",
  "allocated": 40380727296,
  "logical": 139586437120,
  "live_estimate": 3120000000,
  "dead_bytes": 37260727296,
  "dead_ratio": 0.9227,
  "threshold": 0.3,
  "needs_compact": true,
  "docker_running": true,
  "sandbox": {
    "image": "my_agent_env:latest",
    "created_at": 1761200000.0,
    "age_days": 3.2
  },
  "last_prune_at": null,
  "last_compact_at": 1761234000.0,
  "detail": "实际占盘 37.6 GB · 有效数据约 3.1 GB · 空洞约 34.8 GB（92%）",
  "task": { "state": "idle", "kind": null, "log": [], "finished_at": null }
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `supported` | boolean | 当前平台是否支持观测与压缩（Windows + Docker Desktop） |
| `vhdx_path` | string / `null` | vhdx 路径；可在 `settings.json` 用 `docker_vhdx_path` 覆盖 |
| `allocated` | integer | 实际占盘字节数（vhdx 为稀疏文件，逻辑大小不等于占盘） |
| `logical` | integer | 文件逻辑大小（字节） |
| `live_estimate` | integer / `null` | 有效数据估算，来自 `docker system df` 各行 Size 合计，会略高估 |
| `dead_bytes` | integer | 空洞字节数 = `allocated - live_estimate`，下限为 0 |
| `dead_ratio` | number / `null` | 空洞占比（0-1） |
| `threshold` | number | 提示阈值，固定 `0.3` |
| `needs_compact` | boolean | 占比 ≥ 阈值且空洞 ≥ 1GB 时为 `true` |
| `docker_running` | boolean | Docker 引擎是否运行；未运行时无法估算有效数据 |
| `sandbox` | object / `null` | 沙盒容器信息：`image` / `created_at`（Unix 秒）/ `age_days` |
| `last_prune_at` | number / `null` | 上次构建缓存清理时间（Unix 秒） |
| `last_compact_at` | number / `null` | 上次压缩时间（Unix 秒） |
| `task` | object | 最近一次维护任务：`state`（`idle` / `running` / `success` / `failed`）、`kind`（`compact` / `prune`）、`log`、`finished_at` |

`GET /api/config/deploy` 的响应中也会附带同一个 `disk` 字段。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/deploy/disk'
```

---

## POST `/api/config/deploy/disk/compact`

一键回收 vhdx 空洞。后台线程依次停止沙盒容器、停止 Docker Desktop、执行 `wsl --shutdown`，再提权（一次 UAC）执行 `diskpart compact vdisk`，完成后按需重新拉起 Docker。进度通过 `GET /api/config/deploy/disk` 的 `task` 字段查看。

**请求**

无参数（无请求体）。

**响应**

```json
{ "status": "ok", "message": "压缩已开始，Docker 会短暂停止" }
```

已有维护任务在执行时返回 `409`：`{ "detail": "磁盘维护任务正在执行中，请稍候" }`；非 Windows 返回 `409`：`{ "detail": "仅支持 Windows 下的 Docker Desktop" }`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/deploy/disk/compact'
```

---

## POST `/api/config/deploy/disk/prune`

清理 Docker 构建缓存（`docker builder prune -af`），后台线程执行，用于从源头降低 vhdx 增长速度。

**请求**

无参数（无请求体）。

**响应**

```json
{ "status": "ok", "message": "已开始清理构建缓存" }
```

已有维护任务在执行时返回 `409`；Docker 未运行时不执行清理，结果记录在 `task.log`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/deploy/disk/prune'
```

---

## POST `/api/config/deploy/disk/rebuild`

删除沙盒容器 `agent_computer`。容器可写层（apt/pip 安装与缓存）随容器销毁，`/agent_vm` 的 bind mount 工作目录不受影响；下次工具调用会自动基于镜像重建。若工作目录存在 `.agent_env/setup.sh`，重建后会自动执行一次以恢复容器内环境。

**请求**

无参数（无请求体）。

**响应**

```json
{ "status": "ok", "message": "沙盒容器已删除，下次工具调用会自动重建（工作目录文件不受影响）" }
```

未检测到 docker 命令或 Docker 未运行时返回 `409`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/deploy/disk/rebuild'
```

---

## GET `/api/config/sandbox-registry`

读取沙箱镜像 registry 前缀（`settings.json` 的 `sandbox_registry`）。

**请求**

无参数。

**响应**

```json
{ "sandbox_registry": "" }
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/sandbox-registry'
```

---

## PUT `/api/config/sandbox-registry`

更新沙箱镜像 registry 前缀（写入 `settings.json` 的 `sandbox_registry`）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `sandbox_registry` | body | string | 否 | registry 前缀，如 `ghcr.m.daocloud.io`；留空 = 自动依次尝试官方与公共源 |

**响应**

```json
{ "status": "ok" }
```

保存失败返回 `500`：`{ "detail": "保存 sandbox_registry 失败" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/sandbox-registry' \
  -H 'Content-Type: application/json' \
  -d '{"sandbox_registry":"ghcr.m.daocloud.io"}'
```

---

## GET `/api/config/markdown/{filename}`

读取 `~/.purrcat/core/` 下的 `SOUL.md` 或 `GOAL.md`。`filename` 仅允许 `SOUL`、`GOAL`，其余返回 `400`（防路径穿越）；文件不存在时返回空内容。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `filename` | path | string | 是 | 仅允许 `SOUL` 或 `GOAL` |

**响应**

```json
{ "content": "## 性格\n\n你是一个内向的程序员……" }
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/markdown/SOUL'
```

---

## PUT `/api/config/markdown/{filename}`

保存 `~/.purrcat/core/` 下的 `SOUL.md` 或 `GOAL.md`。`filename` 仅允许 `SOUL`、`GOAL`，其余返回 `400`。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `filename` | path | string | 是 | 仅允许 `SOUL` 或 `GOAL` |
| `content` | body | string | 否 | Markdown 全文内容，缺省为空串 |

**响应**

```json
{ "status": "ok", "message": "SOUL.md saved successfully" }
```

写入失败返回 `500`：`{ "detail": "Failed to save SOUL.md" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/markdown/SOUL' \
  -H 'Content-Type: application/json' \
  -d '{"content":"## 性格\n\n你是一个内向的程序员……"}'
```

---

## GET `/api/config/info`

读取 `~/.purrcat/core/info.json`，提供 `skills` 与 `workshops` 列表（文件缺失或解析失败时均返回空列表）。

**请求**

无参数。

**响应**

```json
{ "skills": [], "workshops": [] }
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/info'
```

---

## GET `/api/config/setup-status`

首次启动引导用：数据盘是否已配置（配置过就不再弹引导）。

**请求**

无参数。

**响应**

未配置时：

```json
{ "configured": false, "data_root": "" }
```

已配置时：

```json
{ "configured": true, "data_root": "D:\\purrcat_data" }
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/setup-status'
```

---

## POST `/api/config/setup-data-root`

首次启动设置数据盘（仅首启引导使用；后续变更走 `/change-data-root`）。写入 `settings.json` 的 `data_root`，**重启后生效**。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `data_root` | body | string | 是 | 绝对路径，且不能是磁盘根目录；为空 / 相对路径 / 盘符根均返回 `400` |

**响应**

```json
{ "status": "ok", "data_root": "D:\\purrcat_data", "message": "数据盘设置成功，重启后生效" }
```

已配置过返回 `409`：`{ "detail": "数据盘已配置，变更请使用配置中心的数据根目录入口" }`

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/setup-data-root' \
  -H 'Content-Type: application/json' \
  -d '{"data_root":"D:\\purrcat_data"}'
```

---

## POST `/api/config/change-data-root`

随时更改数据根目录：搬迁可迁移的大型数据子目录到新位置、落盘 `settings.json`、销毁旧沙盒容器；前端随后重启生效。

> ⚠️ 副作用：`embedding` 等大型子目录被整体搬迁；`agent_vm` **不搬迁**（旧盘数据保留在旧位置由用户处置，新位置创建全新空目录）；旧沙盒容器 `agent_computer` 会被销毁（容器内系统变更随之丢失），重启后按新根重建。搬迁中途失败会回滚已移动目录。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `data_root` | body | string | 是 | 新的绝对路径；需与当前根不同、且两者不能互为父子目录，否则返回 `400` |

**响应**

```json
{
  "status": "ok",
  "data_root": "E:\\purrcat_data",
  "moved": ["embedding"],
  "message": "数据已就绪（agent_vm 已在新位置全新初始化，沙盒容器已销毁，重启后自动重建）"
}
```

目标位置已存在同名子目录返回 `409`；搬迁或落盘失败返回 `500`。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/change-data-root' \
  -H 'Content-Type: application/json' \
  -d '{"data_root":"E:\\purrcat_data"}'
```

---

## GET `/api/config/cron`

读取定时任务配置（`~/.purrcat/core/cron.json`）。文件缺失或解析失败时返回空任务列表。

**请求**

无参数。

**响应**

```json
{ "jobs": [] }
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/cron'
```

---

## PUT `/api/config/cron`

更新定时任务配置（`~/.purrcat/core/cron.json`），整体覆盖写入。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `config` | body | object | 是 | 完整定时配置对象，整体覆盖写入 |

**响应**

```json
{ "status": "ok", "message": "Cron config updated successfully" }
```

保存失败返回 `500`：`{ "detail": "Failed to save cron config" }`

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/config/cron' \
  -H 'Content-Type: application/json' \
  -d '{"jobs":[]}'
```

---

## GET `/api/config/meta`

返回当前正在生效的路径常量，便于前端展示给用户参考。

**请求**

无参数。

**响应**

```json
{
  "PURRCAT_DIR": "C:\\Users\\<user>\\.purrcat",
  "DATA_ROOT": "D:\\purrcat_data",
  "BASE_DIR": "D:\\cat-in-cup",
  "settings_path": "C:\\Users\\<user>\\.purrcat\\settings.json",
  "cron_path": "C:\\Users\\<user>\\.purrcat\\core\\cron.json"
}
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/config/meta'
```
