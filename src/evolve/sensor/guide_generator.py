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

会话规则：stdio sensor **固定当前活跃会话**——网关会在 session/new 时自动注入
follow 标记，你无需（也不应）实现任何会话切换逻辑。

铁律：
* stdout **只能**输出协议 JSON-RPC（一行一条）。调试 print 必须走 stderr：`sys.stdout = sys.stderr`
* 严禁退出主进程。连接崩溃要无限重连（带 sleep 缓冲），守护线程只救意外退出
* 配置凭证一律从环境变量读取（由 activate_sensor.json 的 env 注入），禁止硬编码密钥
* 有游标/会话状态的（长轮询 cursor、扫码换的 token 等），持久化到脚本同目录的
  state 文件并随更新落盘——sensor 会被热重启，不落盘就丢消息或丢登录态
* 一切外部网络调用放后台线程，主线程只跑 stdin 读取循环

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

Agent 文本回复（agent_message 逐条到达；消息级粒度——
一条事件即一条完整 assistant 消息，一个轮次可能有多条）：
```json
{{"jsonrpc": "2.0", "method": "session/update", "params": {{"sessionId": "<sid>", "update": {{"sessionUpdate": "agent_message", "messageId": "msg_1", "content": {{"type": "text", "text": "回复内容"}}}}}}}}
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
| `agent_message` | Agent 文本回复。**消息级粒度**：一条事件即一条完整 assistant 消息（非流式分片），一个轮次可能有多条 | ✅ 下发（唯一总是下发的词汇） |
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

沙盒内可以直接手测（不经过宿主机）：

```bash
cd /agent_vm/sensor_workplace/<uuid>
echo '{{"jsonrpc":"2.0","method":"session/update","params":{{"update":{{"sessionUpdate":"agent_message","content":{{"type":"text","text":"hello"}}}}}}}}' | uv run {sensor_name}.py
```

观察 stderr 日志与外部渠道是否收到消息；鉴权求助与握手会打到 stdout。

## 6. sensor_config.json（合并注册的唯一依据）

沙盒根目录维护 `sensor_config.json`，合并时系统只认它：

```json
{{
  "name": "{sensor_name}",
  "env": {{ "MY_TOKEN": "" }},
  "tool_detail": false
}}
```

* `env`：声明全部所需凭证（留空字符串占位，用户配置后注入）
* `tool_detail`：true 时 Agent 的工具调用细节（工具名/结果片段）也会推送到本 sensor；false（默认）时只推送回复正文

## 7. 提交合并

测试通过后调用 `Request(request_type="sensor_merge", target="{sensor_name}")`，
并在 reason 中简述功能点供用户 Code Review。批准后系统会：

1. 拷贝 `{sensor_name}.py` 至正式目录并写入 activate_sensor.json（enabled=true）
2. Git 提交版本记录
3. 热重启 Sensor 线程池——**若凭证未填，你会立刻收到该 sensor 的鉴权求助消息**，请转告用户协助配置。
"""
