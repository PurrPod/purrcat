<div align="center">

# PurrCat

*高度可定制的本地优先个人 Agent 框架。*

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)]()
[![License](https://img.shields.io/badge/license-GPLv3-green)]()

[**English Docs**](./README.md)

</div>

---

## 快速开始

```bash
git clone https://github.com/PurrPod/purrcat.git
cd purrcat

purrcat setup       # 一键部署（Docker沙盒 + Conda环境 + 嵌入模型）
purrcat init        # 生成 .purrcat/ 配置文件
purrcat start       # 启动 TUI 界面
purrcat start --headless  # 无界面启动
```

完整文档：[https://purrpod.github.io/purrcat/](https://purrpod.github.io/purrcat/)

---

## 核心亮点

**1. 双重沙盒隔离。** 所有代码执行封锁在 Docker 容器内，与宿主机完全隔离。通过 `.purrcat/.file.yaml` 严格白名单控制文件访问：`dont_read_dirs`（隐私禁区）、`sandbox_dirs`（操作域）、`docker_mount`（挂载通道），从源头杜绝 Agent 暴走风险。

**2. 可定制 Harness Engineering。** 在同一系统内调度多个 Expert（科研助手、交易员、程序员）。通过标准 Skill、模块化 Tool（`src/tool/`，由 `dispatch_tool()` 动态加载）、或完整 Harness/Expert（继承 `BaseTask`）扩展。

**3. 99%+ KV Cache 命中率。** `dispatch_tool()` 将工具 Schema 从 System Prompt 中剥离，模型 KV Cache 不会因动态注入而失效。实现极致 Token 经济性与毫秒级响应。

**4. 7x24 小时稳定运行。** `APIKeyManager` 自动负载均衡（最少活跃优先）。每轮对话状态实时落盘为 Checkpoint。崩溃后重载即可从断点恢复。

**5. 多核并发。** 后台子任务独立绑定 API Key 和状态机，主会话永不阻塞。Agent 处理繁重任务时仍可下达新指令。

**6. 记忆与灵魂。** Memo 工具 + PurrMemo 本地引擎自动捕捉偏好。心跳 Sensor（`HARNESS.md`）实现无人值守自主迭代。修改 `SOUL.md` 注入独特人格。

---

## 架构分层

```
Sensor 层 (网关)         Feishu / RSS / Clock -> Gateway.push()
       |
Agent 层                 对话 / force_push / 记忆
       |
Model 层 (APIKeyManager)  最少活跃 Key 分配
       |
Tool 层 (dispatch_tool)   Bash / Fetch / FileSystem / Search / Memo / CallMCP / Cron / Task
       |
Harness 层 (BaseTask)     原子方法: run_llm_step / run_tool_calling / check_memory / save_checkpoints
```

---

## 文档导航

- [介绍](https://purrpod.github.io/purrcat/intro)
- [部署指南](https://purrpod.github.io/purrcat/guide/deployment)
- [架构介绍](https://purrpod.github.io/purrcat/develop/architecture)
- [二次开发](https://purrpod.github.io/purrcat/develop/extension)
- [配置说明](https://purrpod.github.io/purrcat/config/)
- [常见问题](https://purrpod.github.io/purrcat/guide/faq)

---

## 致谢

- 感谢 **Gemini Pro 3.1** 协助构建精美的 UI 界面。
- 感谢 **[zhenghuanle](https://github.com/zhenghuanle)** 测试了从零开始的安装流程。
- 感谢 **[Gaeulczy](https://github.com/Gaeulczy)** 测试了一键安装和运行脚本。

---

## 许可证

本项目核心框架采用 **GNU GPL-3.0** 协议开源。

- **核心传染性**：对外分发修改后的核心框架必须开源。
- **插件/拓展豁免**：插件、Harness/Expert 及外部服务**不受 GPL 传染约束**，可闭源商用。
- **免责声明**：代码"按原样"提供，不提供任何担保。
