"""
Sensor 指南生成器模块 (evolve/sensor/guide_generator.py)
单文件指南：覆盖 ACP 协议规范、鉴权求助、文件收发与提交全流程。
"""


def generate_sensor_guide(sensor_name: str, goal: str = "") -> str:
    goal_section = f"\n> 🎯 **本次构建目标**：{goal}\n" if goal else ""
    return f"""# {sensor_name} 传感器工厂指南 (GUIDE)

本指南覆盖 ACP 协议规范、鉴权规范、文件收发与提交全流程，动手前请先通读。
{goal_section}
## 1. Sensor 是什么

Sensor 是一个**独立的常驻子进程**，由宿主机 SensorManager 用 `uv run <name>.py` 拉起，
通过 stdin/stdout 的**单行 JSON-RPC（ACP 方言）**与宿主机网关双向通信：

* **session/prompt（你 → Agent）**：外部事件（用户消息、提醒、状态变化）注入当前活跃会话
* **session/update（Agent → 你）**：Agent 的回复通过你转发到外部渠道（群聊、邮件等）

会话规则：stdio sensor **固定当前活跃会话**——宿主 stdio 桥会在你发 session/new 时
无条件改写 `_meta` 注入 follow 标记（网关本身的默认值是"新开会话"，别自己传这个标记），
你无需（也不应）实现任何会话切换逻辑。

铁律：
* stdout **只能**输出协议 JSON-RPC（一行一条）。调试 print 必须走 stderr：`sys.stdout = sys.stderr`
* 严禁退出主进程。连接崩溃要无限重连（带 sleep 缓冲），守护线程只救意外退出
* 配置凭证一律从环境变量读取（由 activate_sensor.json 的 env 注入），禁止硬编码密钥
* 有游标/会话状态的（长轮询 cursor、扫码换的 token 等），持久化到脚本同目录的
  state 文件并随更新落盘——sensor 会被热重启，不落盘就丢消息或丢登录态
* 一切外部网络调用放后台线程，主线程只跑 stdin 读取循环
* 鉴权求助必须**同时**写清凭证名与"去哪获取"（控制台网址 + 步骤），协议体检会校验这两项
* 合并前必须通过协议体检（见第 7 节），体检报告会被宿主复跑核对，无法用自述蒙混

## 2. 协议规范（JSON-RPC 2.0 over stdio）

### 出向（stdout → 网关）

握手（启动后立即顺序发出，id 1/2）：
```json
{{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {{"clientInfo": {{"name": "{sensor_name}"}}}}}}
{{"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {{"clientInfo": {{"name": "{sensor_name}"}}}}}}
```

注入外部事件（sessionId 用 session/new 响应回传的值）：
```json
{{"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {{"sessionId": "<sid>", "prompt": [{{"type": "text", "text": "[{sensor_name} 收到用户消息] 你好"}}]}}}}
```
prompt 响应不会立即返回——Agent 跑完当前轮次后网关才回 `{{"stopReason": "end_turn"}}`。
连发多条 prompt 无需自行排队——网关按序处理，stopReason 也会按 FIFO 逐条回填，
因此**不要在等 stopReason 的同时阻塞你的事件监听**（prompt 全部 fire-and-forget 即可）。

取消当前轮次（用户说"停下"等场景；通知无 id，网关不回响应）：
```json
{{"jsonrpc": "2.0", "method": "session/cancel", "params": {{"sessionId": "<sid>"}}}}
```
被取消的 prompt 会收到 `{{"stopReason": "cancelled"}}`。

触发后台任务图谱（时钟类 sensor 专用，无需等 Agent 应答的自动化触发；
available 检查 initialize 响应的 `agentCapabilities._meta.purrcat.dev.launch_task`）：
```json
{{"jsonrpc": "2.0", "id": 4, "method": "_purrcat/launch_task", "params": {{"graph_name": "my_graph", "inputs": {{"key": "value"}}, "title": "任务标题"}}}}
```

上传文件给 Agent（content_b64 为 base64 编码的原始字节，单文件 ≤ 20MB；
网关落盘到 `/agent_vm/sensor/files/{sensor_name}/` 并在响应中返回沙盒路径，
**拿到路径后请再用 session/prompt 告知 Agent**，如
`[{sensor_name} Sensor 收到文件] {{path}} ({{mime}}, {{size}})`）：
```json
{{"jsonrpc": "2.0", "id": 4, "method": "_purrcat/upload_file", "params": {{"name": "photo.jpg", "mime": "image/jpeg", "content_b64": "..."}}}}
```

### 入向（stdin ← 网关）

Agent 文本回复（agent_message_chunk 逐条到达；消息级粒度——
一条事件即一条完整 assistant 消息，一个轮次可能有多条；
messageId 每条唯一，变化即新消息边界）：
```json
{{"jsonrpc": "2.0", "method": "session/update", "params": {{"sessionId": "<sid>", "update": {{"sessionUpdate": "agent_message_chunk", "messageId": "msg_1", "content": {{"type": "text", "text": "回复内容"}}}}}}}}
```
其他 update 类型见下方词汇总表（受 tool_detail 配置控制是否下发）。

Agent 发的文件（Agent 消息里含本地文件链接时网关自动追加）：
```json
{{"jsonrpc": "2.0", "method": "_purrcat/file", "params": {{"name": "a.png", "mime": "image/png", "size": 11, "content_b64": "..."}}}}
```
你需 base64 解码后自行发送到外部渠道。若渠道 API 是"先上传换 key 再发消息"两段式（如飞书），请在后台线程完成，**严禁阻塞 stdin 读取循环**。

还有 request 的响应（`{{"id": ..., "result": ...}}`）——按 id 匹配你发出的请求。

### 词汇总表

**sessionUpdate 值**（`session/update` 的 `update.sessionUpdate` 字段）——ACP 标准词汇：

| 词汇 | 说明 | tool_detail=false 时 |
|---|---|---|
| `agent_message_chunk` | Agent 文本回复。**消息级粒度**：一条事件即一条完整 assistant 消息，每条一个唯一 messageId（id 变化即新消息边界），一个轮次可能有多条。消费端建议同时容忍旧拼写 `agent_message` | ✅ 下发（唯一总是下发的词汇） |
| `agent_thought_chunk` | Agent 思考过程文本 | ❌ 过滤 |
| `tool_call` | 工具调用开始（status=pending；含 `toolCallId`/`title`/`kind`，文件类工具带 `locations`，参数对象带 `rawInput`） | ❌ 过滤 |
| `tool_call_update` | 工具状态流转（in_progress → completed/failed），content 带截断后的结果文本 | ❌ 过滤 |
| `usage_update` | token 用量（`used`=窗口已用，`size`=模型上限） | ❌ 过滤 |
| `session_info_update` | 会话元数据（updatedAt），每轮结束前同步 | ❌ 过滤 |
| `user_message_chunk` | 历史回放专用（编辑器 session/load 场景），stdio sensor 不会收到 | — |

**PurrCat 扩展词汇**（`_purrcat/` 前缀）：

| 词汇 | 方向 | 说明 |
|---|---|---|
| `_purrcat/upload_file` | sensor → 网关（方法） | 上传文件给 Agent（base64，单文件 ≤ 20MB；见上方出向示例） |
| `_purrcat/launch_task` | sensor → 网关（方法） | 触发后台任务图谱（时钟类 sensor 专用，无需等 Agent 应答） |
| `_purrcat/file` | 网关 → sensor（通知） | Agent 消息提及本地文件时网关自动追加（base64，解码后自行发送到外部渠道） |
| `_purrcat/turn_end` | 网关 → sensor（通知） | 轮次终结标记（params 带 stopReason）；不消费则忽略 |

## 3. 首次启动鉴权规范 ⭐（最重要）

Sensor 首次启动往往需要凭证（App Secret、API Token 等）。**严禁缺凭证时静默退出或空转**，必须：

1. 启动时检测凭证是否为空；
2. 为空则立即用 **session/prompt 发送文字消息向 Agent 求助**，说清四件事：缺哪些凭证、
   **去哪获取**（外部平台控制台的网址与完整步骤，用户不看文档也能照做）、
   去哪配置（前端配置中心 → Sensor 设置 → 填写 env 后启用）、凭证到位后自己会做什么；
3. Agent 会转告用户并协助完成配置（配置保存后系统会热重启 sensor，届时读到新 env 自动恢复）；
4. 主进程保持存活待命，不要退出。

## 4. 单文件骨架

依赖用 PEP 723 内联声明（uv 会自动建环境）。沙盒初始化时已生成可运行的
ACP 骨架（initialize → session/new → prompt 求助 → update 消费循环），
按 TODO 注释替换真实外部服务逻辑即可。

## 5. 测试方法

沙盒根目录已内置**真网关夹具**，它会扮演网关拉起你的 sensor（凭证留空，逼出鉴权路径），
自动核对握手顺序、求助发出、sessionId 回填、stdout 纯净、空转存活：

```bash
cd /agent_vm/sensor_workplace/<uuid>
uv run evals/gateway_probe.py
```

失败项的排查线索在 `evals/probe_stderr.log`（sensor 的 stderr 全量日志）。

需要观察单条下发消息的处理时，也可以直接用 echo 手测：

```bash
echo '{{"jsonrpc":"2.0","method":"session/update","params":{{"update":{{"sessionUpdate":"agent_message_chunk","content":{{"type":"text","text":"hello"}}}}}}}}' | uv run {sensor_name}.py
```

## 6. sensor_config.json（合并注册的唯一依据）

沙盒根目录维护 `sensor_config.json`，合并时系统只认它：

```json
{{
  "name": "{sensor_name}",
  "env": {{ "MY_TOKEN": "" }},
  "tool_detail": false,
  "source": "remote"
}}
```

* `env`：声明全部所需凭证（留空字符串占位，用户配置后注入）。
  代码里 `os.environ.get("X")` 读到的每个键都**必须**在此声明——协议体检会做双向交叉校验，
  漏声明会导致合并后用户无从配置
* `tool_detail`：true 时 Agent 的工具调用细节（工具名/结果片段）也会推送到本 sensor；false（默认）时只推送回复正文
* `source`：`"remote"`（默认，外部源在远程平台）或 `"local"`（外部源是可本地构造的文件/本地服务）。
  标 `local` 的 sensor 有机会把"外部事件 → 注入会话"这一段也纳入自动化闭环

## 7. 验收标准（协议体检）

提交 `Request(request_type="sensor_test", target="<uuid>/{sensor_name}")` 后，宿主会**亲自扮演网关**
实跑你的 sensor（L0 静态契约 + L1 协议夹具），全绿才允许合并。硬性判据：

| # | 判据 | 说明 |
|---|---|---|
| 1 | 协议纯净 | stdout 只有合法 JSON-RPC，日志全在 stderr |
| 2 | 永不退出 | 空转与异常输入下进程都存活 |
| 3 | 契约自述 | sensor_config.json 合法，代码读的 env 键全部已声明 |
| 4 | 依赖可装 | `uv run` 能建成环境并完成握手（PEP 723 有效） |
| 5 | 握手时序 | 先 `initialize`(id=1) 再 `session/new`(id=2) |
| 6 | 鉴权自服务 | 空凭证时主动求助，文本含凭证名与获取入口 |
| 7 | sessionId 回填 | 用 session/new 响应回传的 sessionId 发所有 prompt（回填错会让注入静默失效） |
| 8 | 故障可见 | 异常不崩溃，关键路径日志可读 |

体检产物落在 `iteration-N/`：`protocol_report.md`、`benchmark.json`、`handshake.json`（全量抓包）、
`sensor_stderr.log`。**外部渠道未被 mock**，所以"Agent 回复在渠道里长什么样""幂等去重""游标续传"
这类真实链路行为不在自动体检范围内，报告会显式列在「未覆盖项」里——别把它们当成已验证。

## 8. 提交合并

体检通过后调用 `Request(request_type="sensor_merge", target="{sensor_name}")`，
并在 reason 中简述功能点供用户 Code Review。批准后系统会：

1. 拷贝 `{sensor_name}.py` 至正式目录并写入 activate_sensor.json（enabled=true）
2. Git 提交版本记录
3. 热重启 Sensor 线程池——**若凭证未填，你会立刻收到该 sensor 的鉴权求助消息**，请转告用户协助配置。

⚠️ 合并前系统会复核最近一次协议体检结论，且要求报告**晚于**最后一次代码改动：
改完代码务必重跑 `sensor_test`，拿着过期报告申请合并会被直接拒绝。
"""
