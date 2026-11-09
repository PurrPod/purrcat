# Sensor 开发指南（感官中枢）

> 落地目录：`~/.purrcat/sensor/<name>.py` ｜ 运行时配置：`~/.purrcat/activate_sensor.json` ｜ 市场仓库：`PurrPod/sensors`

Sensor 把外部事件（飞书/微信消息、RSS 更新、闹钟等）推给 Agent，并可把回复发回外部渠道。每个 Sensor 是**独立常驻 Python 子进程**。

---

## 1. 运行时模型

- 由主进程 `SensorManager` 用 **`uv run <name>.py`** 拉起，依赖通过 **PEP 723 内联元数据**声明（uv 自动建环境）。
- 与主进程通过 **stdin/stdout 的「单行 JSON-RPC（ACP 方言）」**双向通信：stdout 只能输出协议 JSON，调试日志必须走 stderr。
- 是否双向（既收也能发）由**代码行为**决定，不在配置里声明能力字段。
- 子进程崩溃会被守护线程拉起；同名 Sensor 已在运行时，会被先整树击杀再重启，避免双实例抢占外部连接。

---

## 2. 目录与命名约定

```text
sensors/<sensor-name>/          # 市场仓库中的单元
├── <sensor-name>.py            # 单文件脚本，名称 = 文件夹名
└── config.json                 # 市场/配置清单
```

**文件夹名 = `config.json` 的 `name` = 代码文件名（去掉 `.py`）**，三者必须严格一致（CI 校验）。

### `config.json` 字段（市场清单）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `name` | 是 | 安装标识，与文件夹名、代码文件名一致 |
| `description` | 是 | 英文描述，一句话说明用途 |
| `description-zh` | 是 | 中文描述，用于市场中文展示 |
| `enabled` | 是 | 是否启用；registry 占位默认 `false`，安装后由用户在前端启用 |
| `env` | 是 | 环境变量键值对，注入到 Sensor 运行时（`{ "FEISHU_APP_SECRET": "" }` 形式，默认留空占位） |
| `icon` | 否 | 配置页卡片头像的图标链接；留空或加载失败都会回退默认图标 |
| `tool_detail` | 是 | 是否向该 Sensor 推送工具调用细节，默认 `false`（只推回复正文） |

### `env` 与凭证铁律

**代码里 `os.environ.get("X")` 读到的每个键，都必须在 `env` 中声明**。实际值由用户在前端配置中心填写，或在进化工厂沙盒的 `sensor_config.json` 中填好（合并规则见第 6 节）。禁止硬编码密钥。

---

## 3. 专有词汇表

### 3.1 出向（Sensor → 网关，stdout）

| 方法 | 用途 |
| --- | --- |
| `initialize` | 握手第一步（`id=1`） |
| `session/new` | 握手第二步（`id=2`）；响应回传 `sessionId` |
| `session/prompt` | 注入外部事件到当前活跃会话 |
| `session/cancel` | 取消当前轮次（通知，无 `id`，网关不回响应） |
| `_purrcat/launch_task` | 触发后台任务图谱（无需等 Agent 应答；时钟类专用） |
| `_purrcat/upload_file` | 上传文件给 Agent（base64，单文件 ≤ 20MB） |

### 3.2 入向（网关 → Sensor，stdin）

| 方法 / 字段 | 用途 |
| --- | --- |
| `session/update` | Agent 侧更新，`params.update.sessionUpdate` 区分词汇（见下表） |
| `_purrcat/file` | Agent 消息提及本地文件时网关自动追加（base64，解码后发往外部渠道） |
| `_purrcat/turn_end` | 轮次终结标记（`params.stopReason`）；不消费则忽略 |
| `{ "id": ..., "result": ... }` | 对出向请求的响应（按 `id` 匹配） |

### 3.3 `sessionUpdate` 词汇（`update.sessionUpdate` 字段）

| 词汇 | 说明 | `tool_detail=false` 时 |
| --- | --- | --- |
| `agent_message_chunk` | Agent 文本回复。**消息级粒度**：一条事件即一条完整 assistant 消息，每条一个唯一 `messageId`（id 变化即新消息边界）；一轮可能多条。建议同时容忍旧拼写 `agent_message` | ✅ 唯一总是下发 |
| `agent_thought_chunk` | Agent 思考过程文本 | ❌ 过滤 |
| `tool_call` | 工具调用开始（`status=pending`；含 `toolCallId`/`title`/`kind`，文件类带 `locations`，参数对象带 `rawInput`） | ❌ 过滤 |
| `tool_call_update` | 工具状态流转（`in_progress → completed/failed`），`content` 带截断结果文本 | ❌ 过滤 |
| `usage_update` | token 用量（`used`=窗口已用，`size`=模型上限） | ❌ 过滤 |
| `session_info_update` | 会话元数据（`updatedAt`），每轮结束前同步 | ❌ 过滤 |
| `user_message_chunk` | 历史回放专用（编辑器 `session/load`），stdio Sensor 不会收到 | — |

### 3.4 会话规则

stdio Sensor **固定当前活跃会话**——网关在你发 `session/new` 时无条件改写 `_meta` 注入 follow 标记。你**无需、也不应**实现任何会话切换逻辑。

---

## 4. 协议规范（JSON-RPC 2.0 over stdio）

### 4.1 握手（启动后立即顺序发出，`id` 1/2）

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "my-sensor"}}}
{"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"clientInfo": {"name": "my-sensor"}}}
```

### 4.2 注入外部事件（`sessionId` 用 `session/new` 响应回传的值）

```json
{"jsonrpc": "2.0", "id": 3, "method": "session/prompt",
 "params": {"sessionId": "<sid>", "prompt": [{"type": "text", "text": "[my-sensor 收到用户消息] 你好"}]}}
```

`session/prompt` 的响应不会立即返回——Agent 跑完当前轮次后网关才回 `{"stopReason": "end_turn"}`。连发多条无需排队（网关按 FIFO 处理），因此**不要阻塞事件监听去等 stopReason**，全部 fire-and-forget 即可；被取消的 prompt 收到 `{"stopReason": "cancelled"}`。

### 4.3 触发后台任务图谱

```json
{"jsonrpc": "2.0", "id": 4, "method": "_purrcat/launch_task",
 "params": {"graph_name": "my_graph", "inputs": {"key": "value"}, "title": "任务标题"}}
```

（可用性：检查 `initialize` 响应的 `agentCapabilities._meta.purrcat.dev.launch_task`。）

### 4.4 上传文件给 Agent

```json
{"jsonrpc": "2.0", "id": 5, "method": "_purrcat/upload_file",
 "params": {"name": "photo.jpg", "mime": "image/jpeg", "content_b64": "<base64>"}}
```

网关落盘到 `/agent_vm/sensor/files/<sensor-name>/` 并返回沙盒路径；**拿到路径后请再用 `session/prompt` 告知 Agent**，如 `[my-sensor Sensor 收到文件] {path} ({mime}, {size})`。

### 4.5 接收 Agent 回复

```json
{"jsonrpc": "2.0", "method": "session/update",
 "params": {"sessionId": "<sid>", "update": {"sessionUpdate": "agent_message_chunk",
            "messageId": "msg_1", "content": {"type": "text", "text": "回复内容"}}}}
```

---

## 5. 开发铁律

1. **stdout 只能输出协议 JSON-RPC**（一行一条）。调试 `print` 必须走 stderr：启动时执行 `sys.stdout = sys.stderr`，并把真实 stdout 另存引用（见骨架）。
2. **严禁退出主进程**。连接崩溃要无限重连（带 sleep 缓冲）；守护线程只救意外退出。
3. **凭证一律从环境变量读取**，禁止硬编码密钥。
4. **有游标/登录态的（长轮询 cursor、扫码 token 等）必须持久化到脚本同目录的 state 文件**并随更新落盘——Sensor 会被热重启，不落盘就丢消息/丢登录态。
5. **一切外部网络调用放后台线程**，主线程只跑 stdin 读取循环。
6. **失败上报**：连接成功保持静默；只有失败（缺凭证、连不上、异常）才用 `session/prompt` 上报失败详情，并带上缺失/出错的凭证名，禁止推送成功调试信息。
7. 提交合并前建议先跑**协议体检**（见第 8 节）；体检不通过不再阻止合并，只会在合并结果里给出提醒。

---

## 6. 凭证与配置 ⭐

凭证在开发阶段一次性配置好，**顺序是"先填好、再申请合并"**（不是"先合并、再让用户去配置中心填"）：

1. Agent 先引导用户到外部平台获取所需凭证（App Secret、API Token 等）；
2. 拿到凭证后，由 Agent（或用户）**直接在沙盒的 `sensor_config.json` 里把 `env` 填成真实值**；
3. 合并时系统会把沙盒里的 `env` 原样写进 `activate_sensor.json` 并注入环境变量——**用户无需再去配置中心重填**；沙盒里留空的键会保留正式配置里已有的旧值，不会把用户之前填好的凭证清空（这条只兜底**升级**已有 Sensor 的情况；新 Sensor 留空即漏配，会一启动就报错）。

---

## 7. 最小可运行骨架

```python
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///

import sys, json, os, threading

# stdout 让给协议，日志走 stderr
_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

SENSOR_NAME = "my-sensor"
MY_TOKEN = os.environ.get("MY_TOKEN", "")   # 必须在 config.json 的 env 里声明

_SID = ""
_SID_READY = threading.Event()
_ID = 2  # 1/2 留给握手


def send(method, params, rid=None):
    global _ID
    if rid is None:
        _ID += 1
        rid = _ID
    _REAL_STDOUT.write(json.dumps(
        {"jsonrpc": "2.0", "id": rid, "method": method, "params": params},
        ensure_ascii=False) + "\n")
    _REAL_STDOUT.flush()


def connect():
    send("initialize", {"clientInfo": {"name": SENSOR_NAME}}, rid=1)
    send("session/new", {"clientInfo": {"name": SENSOR_NAME}}, rid=2)


def prompt(text):
    _SID_READY.wait(timeout=30)
    if _SID:
        send("session/prompt", {"sessionId": _SID,
                                "prompt": [{"type": "text", "text": text}]})


def on_line(line):
    global _SID
    try:
        msg = json.loads(line)
    except Exception:
        return
    if msg.get("id") == 2 and "result" in msg:      # 回填 sessionId
        _SID = (msg["result"] or {}).get("sessionId", "")
        _SID_READY.set()
        return
    upd = (msg.get("params") or {}).get("update") or {}
    if upd.get("sessionUpdate") == "agent_message_chunk":
        text = (upd.get("content") or {}).get("text", "")
        # TODO: 把 Agent 回复转发到外部渠道（放后台线程，别阻塞 stdin）


def external_loop():                                # 后台线程：收外部事件
    if not MY_TOKEN:
        # 只上报失败详情，保持进程存活；成功时保持静默
        prompt("【my-sensor 启动失败】缺少凭证 MY_TOKEN，请补齐后重新加载本 sensor。")
        return
    while True:
        # TODO: 长轮询 / WebSocket 收外部消息
        # 收到后： prompt("[my-sensor 收到用户消息] " + content)
        # 有游标请落盘到脚本同目录的 state 文件
        pass


connect()
threading.Thread(target=external_loop, daemon=True).start()
print("[my-sensor] 已启动")

for line in sys.stdin:                              # 主线程只跑 stdin 读取
    if line.strip():
        on_line(line)
```

---

## 8. 测试与验收

### 8.1 本地手测

```bash
# 观察单条下发消息的处理
echo '{"jsonrpc":"2.0","method":"session/update","params":{"update":{"sessionUpdate":"agent_message_chunk","content":{"type":"text","text":"hello"}}}}' | uv run my-sensor.py
```

沙盒（进化工厂）根目录内置**真网关夹具**，会扮演网关拉起你的 Sensor（凭证留空，逼出失败上报路径），自动核对握手顺序、失败上报、sessionId 回填、stdout 纯净、空转存活：

```bash
cd /agent_vm/sensor_workplace/<uuid>
uv run evals/gateway_probe.py
```

失败排查线索在 `evals/probe_stderr.log`（Sensor 的 stderr 全量日志）。

### 8.2 协议体检（合并前建议项）

| # | 判据 | 说明 |
| --- | --- | --- |
| 1 | 协议纯净 | stdout 只有合法 JSON-RPC，日志全在 stderr |
| 2 | 永不退出 | 空转与异常输入下进程都存活 |
| 3 | 契约自述 | 清单合法，代码读的 env 键全部已声明 |
| 4 | 依赖可装 | `uv run` 能建成环境并完成握手（PEP 723 有效） |
| 5 | 握手时序 | 先 `initialize`(id=1) 再 `session/new`(id=2) |
| 6 | 失败上报 | 缺凭证/连接失败时上报失败详情（含凭证名）；连接成功时静默，不发成功调试信息 |
| 7 | sessionId 回填 | 用 `session/new` 响应回传的 sessionId 发所有 prompt |
| 8 | 故障可见 | 异常不崩溃，关键路径日志可读 |

体检产物落在 `iteration-N/`：`report.html`（瑞士风 HTML 体检报告）、`benchmark.json`、`handshake.json`（全量抓包）、`sensor_stderr.log`。**外部渠道未被 mock**，故「回复在渠道里长什么样」「幂等去重」「游标续传」等真实链路行为不在自动体检范围内，会在报告页的「未覆盖项」中显式列出。

---

## 9. 安装与启用

- 安装：市场接口 `/api/tools/market/sensors/install`（下载 `config.json` + `<name>.py` 到 `~/.purrcat/sensor/`，并把条目合并进 `~/.purrcat/activate_sensor.json`）。
- 启用/禁用与填 `env`：写 `activate_sensor.json` 对应条目的 `enabled` / `env`。
- 重载：`POST /api/config/sensor/reload`（停掉全部旧进程，按配置重新拉起启用项）。
- 运行状态：`GET /api/config/sensor/runtime` 列出运行中的 Sensor（`name` / `pid` / `alive`）。
- 停止单个：`POST /api/config/sensor/{name}/stop` 杀死指定 Sensor 进程，并把它在 `activate_sensor.json` 里置为 `enabled=false`（不会被 watchdog 再拉起）。
- 重启单个：`POST /api/config/sensor/{name}/restart` 用于「启动失败」或「已被停止」的 Sensor——先把它在 `activate_sensor.json` 里置回 `enabled=true`，再整树击杀旧进程并按当前配置重新拉起。配置页卡片仅在该项显示「未运行」时提供「重启」按钮，运行中只显示「停止」。
- 彻底删除：`POST /api/config/sensor/{name}/purge` 从配置移除 + 杀进程 + 删除正式 `<name>.py`（不可恢复）；普通删除只移除注册项，文件与运行中进程都会保留。
- 本地无 `<name>.py` 时，主进程会后台按官方仓库地址自动下载后拉起。

接口细节见 [../api/config.md](../api/config.md)、[../api/tools.md](../api/tools.md)。