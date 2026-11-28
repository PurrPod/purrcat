# SPEC-045：沙盒目录挂载

## 背景

沙盒容器 `agent_computer` 目前只有一条 bind mount（数据根下的 `agent_vm` → `/agent_vm`），
用户无法把宿主上的既有项目目录交给 Agent 直接用 Bash 操作，只能先复制进沙盒，容易产生两份副本。

Docker 不支持给运行中的容器追加挂载，但可以把当前容器 `docker commit` 成快照镜像后用原参数重建，
从而在保留 pip/npm/apt 安装环境的前提下应用新的挂载。

## 行为

- 文件权限设置页新增「沙盒挂载」区块：用户选择宿主文件夹，系统生成唯一别名，容器内路径为 `/mount/<别名>`。
- 配置持久化在 `~/.purrcat/mounts.json`，与 `file.json` 分离，保存文件权限不会覆盖挂载配置。
- 重名处理：默认取文件夹名，大小写不敏感去重，冲突时自动追加 `-2`、`-3`；别名可改名，但必须唯一。
- 添加/删除/改名只写配置，不打断运行中的沙盒；设置页显示「已生效 / 待应用 / 路径不存在」状态，并提供「应用挂载」。
- 应用挂载时：关闭现有 shell 会话 → 将当前容器提交为 `purrcat-sandbox:state` 快照 → 用相同运行参数
  （环境变量、tmpfs、端口、labels）加全部有效挂载重建同名容器 → 成功后删除旧容器。失败时回滚并重启旧容器。
- 容器不存在或未运行时，下次启动按配置自动创建/重建，无需额外操作。
- Docker 引擎重启导致命名管道断开（WinError 232/109、broken pipe）时自动重连并重试，
  重建中断留下的 `agent_computer_prev` 在下次启动时优先恢复为正式容器。
- 配置中的挂载源缺失时不阻断沙盒启动：新建容器跳过该挂载，已有容器保留现状并提示。
- FileSystem 工具识别 `/mount/<别名>/...` 并映射回宿主路径；该路径视为读写授权（blocked 规则仍然优先）。
- `@SYS` 输出当前可用挂载（容器路径 → 宿主路径），供 Agent 了解可用目录。
- 挂载源必须存在、是目录、可写，且不能与 `agent_vm`、已有挂载互为父子目录。

## 验收标准

- [ ] AC-1：`/mount/<别名>` 能映射到宿主真实路径，`..` 越界、未知别名返回不存在的路径。
- [ ] AC-2：已挂载路径在文件权限判定中为 `readwrite`，但命中 blocked 规则时仍为 `blocked`。
- [ ] AC-3：新增挂载时同名自动追加后缀，重复目录、父子目录、不可写目录、缺失目录均被拒绝。
- [ ] AC-4：`GET/POST/PUT/DELETE /api/config/mounts` 与 `POST /api/config/mounts/apply` 路由存在且行为符合上述规则。
- [ ] AC-5：容器创建/复用启动时按配置生成 `/mount/<别名>` bind mount，配置变化时快照重建。
- [ ] AC-6：`@SYS` 列出配置中的有效挂载。

## 非目标

- 不让 Agent 自行挂载或卸载宿主目录。
- 不做不重建容器的动态挂载。
- 不保留容器内运行中的进程、shell 环境变量与 `/tmp` 内容。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_sandbox_mounts.py` | AC-1、AC-3、AC-5（挂载参数构造）、AC-6 |
| L0 | `tests/l0/test_bash_docker_env.py` | AC-5（引擎重启后连接自愈） |
| L0 | `tests/l0/test_filesystem_permissions.py` | AC-2 |
| L0 | `tests/l0/test_sandbox_path.py` | AC-1 |
| L1 | `tests/l1/test_api_config_mounts.py` | AC-4 |
| L1 | `tests/l1/test_api_routes_contract.py` | AC-4（路由冻结） |

## 风险与回滚

- 快照重建会中断容器内 dev server 与 shell 会话；commit 期间容器短暂 pause。
- 每次应用挂载会在镜像层链上追加一层，长期频繁变更会增大镜像占用。
- 回滚：删除 `~/.purrcat/mounts.json` 并在设置页重建沙盒即可恢复单挂载状态。
