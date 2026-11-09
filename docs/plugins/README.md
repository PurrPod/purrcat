# PurrCat 插件体系总览

PurrCat 除通用的 **Skill**（技能包）与 **MCP**（外部工具服务）外，另有四类**专属插件**，分别对应 Agent 的感官、编排、主循环与界面：

| 类型 | Install ID 字段 | 定位 | 形态 | 落地目录 | 开发文档 |
| --- | --- | --- | --- | --- | --- |
| **Sensor** | `sensor` | 感官中枢：把外部世界的事件推给 Agent，并把回复送回外部渠道 | 单文件 Python 常驻子进程 | `~/.purrcat/sensor/` | [sensor.md](sensor.md) |
| **Graph** | `graph` | 任务编排中枢：用节点 + 边描述多步骤工作流 | 文件夹（`graph.json` + `asset/`） | `~/.purrcat/graph/<name>/` | [graph.md](graph.md) |
| **AgentLoop** | `agentloop` | 主循环范式：声明每轮循环在哪些阶段注入什么、检查什么 | 单个 YAML 文件 | `~/.purrcat/paradigms/` | [agentloop.md](agentloop.md) |
| **UI Plugin** | `plugin` | 极简模式（`web-minimal`）的界面插件，以 iframe 入驻宿主各区域 | 文件夹（`plugin.json` + `index.html`） | `~/.purrcat/webmin-plugins/` | [ui-plugin.md](ui-plugin.md) |

## 依赖机制（`dependency`）

除 Sensor 外，其余三类的清单文件都支持 `dependency` 声明数组：

```json
"dependency": [
  { "type": "skill",     "id": "my-skill" },
  { "type": "agentloop", "id": "my-loop" },
  { "type": "graph",     "id": "my-graph" },
  { "type": "sensor",    "id": "my-sensor" },
  { "type": "plugin",    "id": "my-ui-plugin" },
  { "type": "mcp",       "id": "my-mcp" }
]
```

- 元素固定形如 `{ "type": "<类型>", "id": "<安装标识>" }`。
- `type` 白名单：`skill` / `plugin` / `mcp` / `agentloop` / `sensor` / `graph`。
- 无依赖时写 `[]`。
- 从市场安装插件时，`dependency` 中的依赖会被**自动一并安装**；典型用法是 UI 插件依赖配套的 AgentLoop / Graph / Sensor。

> `dependency` 只描述“插件类型依赖”。UI 插件引用宿主共享的前端库（marked / KaTeX / highlight.js 等）用 `requires`，两者互不替代，详见 [ui-plugin.md](ui-plugin.md#31-共享运行时requires)。

## 市场与注册表

官方插件市场仓库按类型拆分，各自维护 `registry.json`（由 CI 自动生成）：

| 类型 | 市场仓库 | 本仓库镜像目录 |
| --- | --- | --- |
| Sensor | `PurrPod/sensors` | `extension/sensors/` |
| Graph | `PurrPod/graphs` | `extension/graphs/` |
| AgentLoop | `PurrPod/agentloops` | `extension/agentloop/` |
| UI Plugin | `PurrPod/ui-plugins` | `extension/ui-plugin/` |

前端通过 `/api/tools/market/<类型>` 拉取 `registry.json`，通过对应的 `install` / `uninstall` 接口安装与卸载。详见 [../api/tools.md](../api/tools.md)。

## 组合关系

```text
Sensor（外部事件）
   │ session/prompt 注入
   ▼
AgentLoop（主循环范式）── 决策/调工具 ──▶ Graph（多步工作流）
   ▲                                        │
   │ 会话事件流                              │ 看板 / 产物
   └──────────── UI Plugin（极简模式界面）◀──┘
```

- Sensor 把外部事件经网关注入当前活跃会话；会话绑定一份 AgentLoop 决定各阶段行为；Graph 可由 Agent 触发后台任务，也可由 Sensor（时钟类）直接触发；UI Plugin 可声明依赖带动上述插件。

## 通用开发约定

- **命名一致性**：安装标识（`id` / `name`）必须与文件夹名或文件名（去掉扩展名）严格一致，CI 会校验。
- **必填元数据**：每个清单文件都要有英文 `description` 与中文 `description-zh`（AgentLoop 为 `description` / `description-en`），供市场中英展示。
- **热更新**：插件安装/更新后一般无需重启——Sensor 走 `/api/config/sensor/reload`；UI 插件与 Graph/范式走内存热更新或前端 `Ctrl+R`（详见各文档）。
