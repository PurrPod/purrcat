# 后端开发

FastAPI 应用，入口 `main.py`，代码在 `src/`。

## 启动顺序

`main.py` 的初始化顺序不可调整：

```text
multiprocessing.freeze_support()
  → 端口预检（必须带 __name__ != "__main__" 守卫）
  → ensure_initialized()（必须在业务 import 之前）
  → init_agent()
  → 注册路由
  → /api/health
  → 挂载 /minimal 静态目录
  → uvicorn
```

- 健康检查路由必须先于静态挂载注册。
- `_bg_heavy_init()` 异步预热重依赖，不阻塞首屏。
- 端口由 `scripts/dev.mjs` 或启动参数决定，`--api-port` 缺省时按 `electron/api-port.cjs` 的规则挑选。

## Agent 主循环

```text
on_loop_start → while: on_loop_epoch → 调模型
  ├─ 有 tool_calls → 执行 → on_tool_calling
  └─ 无 → on_loop_end → 通过则结束；否则注入 workflow_hint 重试
```

Hook 阶段固定为 `on_build_system_prompt / on_loop_start / on_loop_epoch / on_tool_calling / on_loop_end / on_input_received`，由范式（AgentLoop）声明。范式存于 `~/.purrcat/paradigms/*.yaml`，会话可在 `meta.json` 绑定并热切换（不重建系统提示，保 KV Cache）。细节见 [AgentLoop 开发](../plugins/agentloop.md)。

## 会话存储

```text
~/.purrcat/data/checkpoints/agent/<session_id>/
├─ meta.json        # token 权威
├─ main.json        # 主干历史
├─ sub_<branch>.json# 子代理分支
├─ plan.md
└─ attachment/
```

列表索引 `index.json` **不含 token**，任何统计或展示 token 都必须读 `meta.json`。

## 工具路由

- 统一入口 `dispatch_tool`（`src/tool/utils/route.py`），输出按 token 截断（FileSystem 读上限 9900）。
- 进程隔离白名单只有 `bash / request / fetch / search`，不可扩大。
- 有状态工具（callmcp、brainstorm、task、memo 等）必须留在主进程；callmcp 用 `asyncio.wait_for` 防挂起。

新增工具：`src/tool/<name>/` → 注册到 `src/tool/__init__.py` → 加入 `route.py` 的 `TOOL_FUNC_MAP`。

## 其它子系统

- DAG：[Graph 开发](../plugins/graph.md)，人工干预节点必须真暂停。
- Sensor：[Sensor 开发](../plugins/sensor.md)，stdout 只输出 JSON-RPC，日志走 stderr。
- ACP：[ACP 接口](../api/acp.md)，需 `X-PurrCat-Token`。

## 运行数据

```text
~/.purrcat/
├─ settings.json · model.json · mcp_config.json · activate_sensor.json
├─ file.json · mcp_schema.json · acp_token
├─ core/          # SOUL.md / GOAL.md / MEMORY.md / info.json / heartbeat.json / cron.json
├─ paradigms/ · skills/ · mcps/ · sensor/ · graph/ · webmin-plugins/
├─ data/          # memory · projects · checkpoints/agent · checkpoints/task
└─ bin/acp_relay.py · logs/backend.log · run/control.json
```

`data_root` 可迁移。用户数据不得写入源码目录。

## 调试

- 改后端必须彻底重启进程并清理残留的 `uv.exe`，否则内存代码与磁盘不一致。
- 崩溃先看 `~/.purrcat/logs/backend.log`。
- 改了 `src/server` 必须同步 `docs/api/`，否则 `scripts/check_api_docs.py` 与 CI 会失败。
