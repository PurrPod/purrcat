<div style="display: flex; align-items: center; justify-content: space-between;">
  <div style="text-align: center; flex: 1;">
    <h1 style="margin-top: 0;">PurrCat</h1>
    <p><strong><a href="https://purrpod.github.io/">📖 官方文档网站</a></strong></p>
    <p><blockquote>经济、高效、可定制化、更懂你的本地优先个人 Agent 框架。</blockquote></p>
  </div>
  <img src="purrcat-logo.png" width="203" height="206" alt="PurrCat" />
</div>

<div align="center">

<br>

**🐾 快速导航** &nbsp;
[介绍](https://purrpod.github.io/intro) &nbsp; | &nbsp; [部署指南](https://purrpod.github.io/guide/deployment) &nbsp; | &nbsp; [架构介绍](https://purrpod.github.io/develop/architecture) &nbsp; | &nbsp; [二次开发](https://purrpod.github.io/develop/extension) &nbsp; | &nbsp; [配置说明](https://purrpod.github.io/config/) &nbsp; | &nbsp; [常见问题](https://purrpod.github.io/guide/faq)

</div>

---

## ✨ 核心亮点

### 1. 事件驱动的主动感知能力
打破传统大模型单一"问答"模式的局限。框架内置事件网关与多源传感器（如 RSS 轮询、飞书接入、系统定时器等），使 Agent 能够在后台持续关注外部环境变化，并在满足特定条件时主动向用户汇报摘要或自动推进任务。

### 2. 多层混合记忆架构
为改善大模型在长期交互中的信息遗忘问题，系统设计了包含短时工作记忆、通用画像提示词与长期记忆图谱（PurrMemo）的三层结构。配合基于艾宾浩斯曲线的时间衰减机制，长期未被唤起的边缘信息会被逐渐清理，以保持数据库的健康与检索效率。

### 3. 注重上下文缓存优化的调度策略
在较长的上下文交互中，稳定的 KV Cache 命中率对于降低运行成本和提升响应速度至关重要。通过剥离 System Prompt 中的工具 Schema 并采用动态加载方式，配合底层的 API 密钥与会话生命周期强绑定机制，力求在多任务并发场景下维持较高的缓存命中率。

### 4. 独立的沙盒执行环境
框架为 Agent 分配了基于 Docker 构建的隔离运行环境。相比于在宿主机上通过正则拦截命令的方案，物理隔离的设计能够在不引入过多人工干预的前提下，更好地保障本地文件系统的安全，同时也为 Agent 处理长周期任务提供了稳定的驻留空间。

### 5. Git 风格的会话分支管理
系统引入了类似于 Git 分支的会话管理机制。在探索复杂问题的解决路径时，用户可以拉取新的分支进行试错。若结果不符合预期，能够随时切换回主干。此外，系统内置了状态检查工具，在工具调用中断或返回异常时，可自动回滚至上一个安全状态，减少逻辑错乱的发生。

### 6. 模块化有向无环图 (DAG) 调度
对于复杂的业务流程，PurrCat 支持将其拆解为基于 DAG 结构的工作流（Harness）。该机制允许后台节点异步流转，不阻塞前台主会话。在流程遇到权限受限或缺乏足够信息时，系统会触发人机协同（Human-in-the-loop）机制挂起任务，等待人工注入指令后，精确从断点恢复执行。

### 7. 开放的工具与流程拓展体系
期望降低二次开发的门槛。框架支持通过配置文件热更新外部 MCP (Model Context Protocol) 工具，也可通过终端指令快速装载社区分享的 Skill。同时，内置的可视化 UI 提供了节点编排与连线功能，能够将可视化的流程图快速导出为可执行的部署配置。

---

## 🙏 致谢

- 感谢 **Gemini Pro 3.1** 协助构建精美的 UI 界面。
- 感谢 **[zhenghuanle](https://github.com/zhenghuanle)** 测试了从零开始的安装流程。
- 感谢 **[Gaeulczy](https://github.com/Gaeulczy)** 测试了一键安装和运行脚本。

---

## 📜 许可证

本项目核心框架采用 **GNU GPL-3.0** 协议开源。

- **核心传染性**：对外分发修改后的核心框架必须开源。
- **插件/拓展豁免**：基于本项目开发的 Skill、Harness 及外部服务**不受 GPL 传染约束**，可闭源商用。
- **免责声明**：代码"按原样"提供，不提供任何担保。