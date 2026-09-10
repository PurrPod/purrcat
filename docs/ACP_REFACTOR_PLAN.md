# ACP 统一网关架构改造计划

> 分支：`refactor/acp-gateway`
> 状态：Phase 1 已完成（含规范核对修正）；sensor 侧全部冻结，先打穿 ACP 线
> 原则：每阶段独立可冒烟，任何时刻 main 行为不受影响

## 1. 背景与目标

### 现状
- **WebUI**（Electron）走原生 `/api/*` 方言，轮询 `/status` + 会话历史渲染
- **Sensor 网关**（`src/sensor/gateway.py`）以 observe/express/launch_task 三词汇
  经 stdio 服务外部频道（飞书、时钟）
- **无编辑器接入能力**：ACP（Agent Client Protocol）生态（Zed / Neovim 等）无法驱动 purrcat

### 目标
1. 后端新增 **ACP 网关**：外部频道的唯一词汇路由器（ACP 标准方法 + `purrcat/` 扩展）
2. **传输与词汇正交**：词汇统一 ACP；传输 sensor 自选 stdio 或 HTTP
   - stdio：Manager 桥接进网关（进程托管、零网络代码，时钟/飞书适用）
   - HTTP：独立客户端（Zed 转接 sensor 适用）
3. Zed 经**转接 sensor**（纯搬运工）接入，在 Zed 眼里它就是 agent 本体
4. 删除旧词汇层（observe/express 路由 / active_channels / `/unbind`）；
   Manager 保留进程托管 + 新增 stdio→网关桥接

### 非目标（明确不做）
- WebUI 不改说 ACP 方言（原生 API 对它是零收益换皮）
- token 级流式输出（v1 为事件粒度，见 §5 开放问题 2）
- MCP 层不动（已是标准，与本次改造正交）

## 2. 终点架构

```
WebUI ──(原生 /api/*，不动)──────────────────┐
                                             ├──► Agent 核心
Zed ──► 转接 sensor ──(HTTP+SSE, 全套 ACP)──┤    (AgentManager)
飞书 ──(stdio 或 HTTP, prompt+回复子集)──────┤        ▲
时钟 ──(stdio 或 HTTP, purrcat/launch_task)──┤        │
                                             └── ACP 网关(新)
```

- 两条方言、一个核心：WebUI 原生；其余外部频道 ACP
- **传输自选、词汇唯一**：stdio 载荷从 `{method:"observe"}` 换成 JSON-RPC
  （`{jsonrpc:"2.0",method:"session/prompt"}`），Manager 收到后调网关函数处理
  （同进程直调，不经 HTTP 环回）；HTTP 客户端直接打网关端点
- Zed 转接 sensor 由 **Zed spawn**（stdio 归 Zed），对后端走 HTTP；飞书/时钟由
  **Manager spawn**（保住 watchdog / kill-tree / 云端下载），传输按配置选 stdio/HTTP
- 会话路由天然化：prompt 的响应按 JSON-RPC id 回到发起方（连接或进程），
  `active_channels` + `/unbind` 绑定机制整体删除

## 3. 决策记录（本次设计对话敲定）

| # | 决策 | 理由 |
|---|------|------|
| D1 | server 对 WebUI 零改动 | 协议适配是边缘活；原生 API 是 WebUI 的贴身方言 |
| D2 | ACP 网关住后端，桥（转接 sensor）零词汇 | 翻译层可 curl/pytest 冒烟，不必开编辑器；策略集中在后端 |
| D3 | 文件走 multipart/GET，不进词汇表 | 文件是传输层能力，词汇表保持最小 |
| D4 | `purrcat/launch_task` 带命名空间扩展 | JSON-RPC 允许自定义方法；时钟的 launch_task 语义 ACP 没有 |
| D5 | 斜杠命令 → `session/set_mode` + 少量扩展 | 复用 ACP 现成模式切换，不发明新词 |
| D6 | 飞书群 = 一个长持 session，每条消息 = 一次 prompt | sensor 端会话管理零决策 |
| D7 | watchdog 重启后 sensor 重新 initialize，网关按 sensor 名清 stale session 映射 | 复用现有守护模型 |
| D8 | 鉴权：本地 token 文件（`~/.purrcat/`），沿 window token 先例 | 本地 HTTP 不裸奔 |
| D9 | 端口发现：SensorHost 拉起的走 env 注入（现有 `cfg["env"]` 机制）；Zed 拉起的读配置文件 | 两条拉起路径不同 |
| D10 | PurrPod/sensors 云端仓库方言作废，evolve 工厂骨架同步更新 | 生态重写是一次性税，已接受 |
| D11 | 传输与词汇正交：词汇统一 ACP，传输 stdio/HTTP 双支持 | stdio 保住零网络体验与时钟类简单 sensor；HTTP 满足 Zed 拉起的转接；stdio 载荷换 JSON-RPC 后 Manager 同进程直调网关，词汇路由器仍唯一 |

## 4. 规范核对记录（2026-09-10，对照官方 v1 spec + hermes-agent 参照实现）

来源：`agentclientprotocol.com/protocol/v1/`（overview / extensibility / prompt-turn /
session-setup）、`NousResearch/hermes-agent/acp_adapter`（server/session/events/
permissions/content 模块划分与我们的网关分层一致，作架构参照）。

**方法名修正**（初版凭记忆写错）：

| 我写的 | 规范实际 | 影响 |
|---|---|---|
| `newSession` | **`session/new`** | 网关已实现，Phase 1 代码需改名 |
| `purrcat/launch_task` | **`_purrcat/launch_task`**（扩展方法必须 `_` 前缀） | 网关已实现，需改名 |
| `session/cancel` 当方法 | **是通知**（无 id、不回响应） | 转接脚本不得向编辑器回写响应 |

**结构修正**（之前不知道/搞混的）：

1. **`tool_call` 与 `tool_call_update` 是两个词**：先发 `tool_call`（toolCallId/
   title/kind/status:pending，无内容），状态流转走 `tool_call_update`
   （in_progress → completed+content）。v1 只有完成粒度 → 网关发
   `tool_call(pending)` + `tool_call_update(completed)` 成对补齐。
2. **`session/prompt` 的最终响应必须携带 StopReason**（end_turn/max_tokens/
   max_turn_requests/refusal/cancelled，**无 "error"**）。转接脚本持住请求，
   SSE 收到 turn_end 后回 `{"stopReason": ...}`。断层映射：打断→cancelled，
   故障→end_turn（错误文本已走消息通道）。agent.py 里我发的 `"error"` 需改。
3. **`messageId`**：chunk 可带 messageId，同 id 属同一条消息。agent 每条
   assistant 消息一个 uuid，语义天然正确。
4. **`mcpServers` 是数组** `[{name, command, args, env}]` 不是字典（v1 忽略，
   purrcat 有自己的 MCP 配置；后续增强再桥接）。
5. **扩展能力通告**：`agentCapabilities._meta`（如
   `{"purrcat.dev": {"launch_task": true}}`），自定义数据进各类型 `_meta` 字段。
6. **协议文件路径必须绝对路径**；camelCase 键名 + snake_case 判别值（已符合）。
7. 可选项：`usage_update`（window_token 现成，v1.1 加）、`authenticate`/
   `logout`（不需要）、`session/load`（loadSession=false 已如实通告）。
8. 取消契约细节：客户端取消后，未决的 `request_permission` 必须以 cancelled
   收场；取消后仍可继续发 update，但都必须在 prompt 响应之前。

## 5. 阶段计划

### Phase 1 — ACP 网关（纯 HTTP，可独立冒烟）✅ 已完成
新增 `src/server/api/acp.py`（router prefix `/acp`）+ `src/server/acp/`
（bus.py 事件总线 / sessions.py 会话映射）：

1. **事件总线**：agent 钩子点（消息/思考/工具完成/phase/turn_end）→ pub/sub，
   `call_soon_threadsafe` 桥到 asyncio 消费者，回调异常全吞
2. **会话映射**：ACP sessionId → purrcat session；`session/new` 建会话；
   prompt 排队等 idle（复用 chat.py 语义）
3. **HTTP 端点**：`POST /acp/rpc`（JSON-RPC 分发）、`GET /acp/stream`（SSE
   + 词汇翻译 + 15s 心跳）、`POST /acp/file` / `GET /acp/file`（multipart，
   sandbox 防穿越）
4. **鉴权**：`X-PurrCat-Token`（`~/.purrcat/acp_token` 自动生成）

已完成冒烟（16 项全过）：401 / 全方法分发（-32601/-32602）/ 文件回环 + 名字
清洗 + 越权拦截 / bus→SSE 端到端（真 uvicorn）。

**规范核对修正（§4）已全部落码**：`session/new` / `_purrcat/launch_task` /
cancel 通知化 / tool_call(pending)+tool_call_update(completed) 成对 /
stopReason error→end_turn / initialize 通告 `_meta` 扩展 / messageId。
复验冒烟 8 项全过（含 SSE 词汇顺序：thought → tool_call → tool_call_update →
message → turn_end）。

**踩坑记录（Phase 2 relay 必须吸收）**：httpx 默认 `trust_env=True` 会吃系统
代理，localhost 请求被代理劫持返回 502 —— relay 访问后端必须
`trust_env=False`（或 NO_PROXY=127.0.0.1）。

### Phase 2 — Zed 转接 sensor（纯搬运，接通即用）⬅ 当前阶段
`scripts/acp_relay.py`（仓库内，PEP 723 单文件，stdlib-only）：

- stdio 侧：读编辑器的 JSON-RPC 行 → 转发网关 HTTP
- SSE → stdout：`session/update` 通知逐行写；**turn_end → 回写持住的
  `session/prompt` 响应**（stopReason）；通知类请求（cancel）的 HTTP 响应丢弃
- 零词汇：翻译全在网关，转接只做 id 配对与搬运
- 端口/token 发现：读 `~/.purrcat/` 配置文件（D9）
- Zed settings.json 一行：`"agent": {"command": "uv", "args": ["run", "<abs>/scripts/acp_relay.py"]}`

验收：Zed 里对话、看 thinking/工具气泡、中断（cancelled 收尾）。

### Phase 3 — 存量 sensor 改造（🧊 冻结，等 ACP 线验收后再启动）
飞书、时钟改说 ACP 方言，传输保持 stdio（零网络代码）：飞书
`session/prompt` 攒齐回群；时钟 `_purrcat/launch_task`；Manager 识别
JSON-RPC 载荷直调网关，旧 observe/express 走 SensorGateway 共存。

验收：飞书全功能回归（消息/文件/斜杠命令）；时钟任务照常触发。

### Phase 4 — 删旧与瘦身（🧊 冻结，最后执行）
删 `src/sensor/gateway.py`；Manager 删旧词汇路由保留进程托管 + stdio→网关
桥接；evolve 骨架换 ACP 方言模板；`send_to_sensors` 改只发总线。
验收：全仓 grep 无 observe/express 残留；历史数据冒烟。

## 6. 开放问题

1. **单活跃会话 vs 多 ACP session 并发**：AgentManager 是单活跃会话
   （webui 靠排队等 idle 再 switch）。ACP 侧编辑器每开一个 chat tab 就
   `session/new`。候选：a) ACP 会话同样串行排队（最省，**v1 已按此实现**）；
   b) 每个 ACP 会话映射 branch session 并发（动核心，贵）。Zed 实测体验不佳
   再升 b。
2. **流式粒度**：v1 事件级（消息完成时一次性发 chunk + messageId 分组，编辑器
   渲染正常）；token 级需要 hook LLM 流，另立后续任务。
3. **后端启动依赖**：纯编辑器场景下后端谁拉起？relay 连不上时给出可读报错
   （提示先启动 purrcat 桌面端）。自动拉起后端列为后续增强，不入本期。
4. **PurrPod 仓库迁移**：云端 sensor 重写节奏与本改造解耦，D10 只锁方向。
   （Phase 3/4 已冻结，此项无排期。）

## 7. 顺序总结

```
Phase 1 网关 ✅ ──► 规范修正 ⬅ 当前 ──► Phase 2 转接 ──► (Zed 可用)
                                    ──► Phase 3/4 🧊 冻结，等 ACP 线验收
```
