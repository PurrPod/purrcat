# SPEC-015：utils 大文件职责拆分

## 背景

`src/utils/` 下多个文件把 I/O 探测、纯决策、后台线程编排与模板常量混在一起，
无法在不启动子进程/不落盘的情况下做单元测试，任何一处调整都要整体回归。
`config.py`、`path.py`、`tracker.py`、`attachments.py` 已完成整理，本次处理其余文件。

## 行为

对外可见行为保持不变：

- `disk_maintenance`：只读观测结果（vhdx 占盘、有效数据估算、空洞比例、提示阈值）、
  压缩/清理任务状态流转、日志文案与磁盘清理规则完全一致。
- `deploy_manager`：依赖检测结果、安装步骤与命令、进度日志、失败提示完全一致。
- `initial` / `paradigm_api`：首启生成的文件集合、生成顺序与幂等语义不变，
  `DEFAULT_PARADIGM_YAML` 文本不变。
- `log_api` / `task_api`：日志渲染文案、任务列表合并与排序、checkpoint 解析语义不变。
- `embedding_setup` / `local_embedding`：模型完整性判定、下载顺序、池化数学不变。
- `graph_api`：迁移规则（`required_inputs → global_schema`、`.bak`、废弃节点告警）不变。

为了可测试性新增最小扩展点，默认参数下行为与原来等价：

- 目录根可通过参数注入（`graph_api.migrate_graphs_to_folders(root=None)`）。
- 平台相关的安装命令抽成纯函数（`deploy_installers.uv_install_command(platform=None)`）。
- 重复的文件遍历、子进程流式执行、大小/时间格式化收口到
  `src/utils/_fs.py`、`_proc.py`、`_format.py`。

## 验收标准

- [ ] AC-1：磁盘维护的配额阈值、空洞计算、isize 解析、时间解析有 L0 用例。
- [ ] AC-2：共用格式化与文件读写辅助有 L0 用例（`_format`、`_fs`）。
- [ ] AC-3：部署项安装命令构造按平台可测，且不执行安装。
- [ ] AC-4：首启默认配置模板与幂等生成有 L0 用例（tmp_path）。
- [ ] AC-5：任务 checkpoint 扫描、合并与排序有 L0 用例（tmp_path）。
- [ ] AC-6：嵌入模型完整性判定与配置读取有 L0 用例（tmp_path）。
- [ ] AC-7：既有 `tests/l0`、`tests/l1` 全绿，`ruff check src/utils tests` 通过。

## 非目标

- 不改变任何磁盘清理、部署安装、初始化顺序、日志格式与任务状态流转。
- 不新增第三方依赖，不引入 import 时副作用。
- 不整理 `config.py`、`path.py`、`tracker.py`、`attachments.py`。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_disk_maintenance.py` | AC-1 |
| L0 | `tests/l0/test_utils_formatting.py` | AC-2 |
| L0 | `tests/l0/test_utils_fs.py` | AC-2 |
| L0 | `tests/l0/test_deploy_manager.py` | AC-3 |
| L0 | `tests/l0/test_initial.py` | AC-4 |
| L0 | `tests/l0/test_task_store.py` | AC-5 |
| L0 | `tests/l0/test_embedding_manifest.py` | AC-6 |

## 风险与回滚

- 磁盘维护涉及 UAC 提权与容器停机：拆分只移动代码，压缩脚本内容、命令顺序、
  缓存失效时机必须逐行比对。
- 部署项在 Windows 上调用 winget/powershell：本次只抽命令构造，执行路径不变。
- 回滚方式：恢复单文件实现；新增测试可直接复用（它们测的是等价接口）。
