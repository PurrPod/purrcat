# SPEC-011：Sensor 包拆分（进程控制 / 文件引用解析）

## 背景

`src/sensor/` 有两个可独立验证的纯逻辑块混在编排代码里：从 Agent 消息文本中提取本地文件路径（原先埋在 `bridge.py`），以及传感器子进程的环境清洗与整树击杀（原先埋在 `manager.py`）。两者都无法在不启动子进程、不引入 ACP 总线的情况下单测。

## 行为

- `sensor/file_refs.py` 负责文本 → 宿主路径：markdown 链接、裸 `/agent_vm/...`、`./`/`../` 前缀、`file://`、Windows 盘符路径；行尾中英文标点剥除；重复路径去重；不存在的文件与目录过滤；`/agent_vm_backup/...` 等相似前缀不被误判。
- `sensor/processes.py` 负责子进程低层控制：构造 `uv run <script>` 命令；从父进程环境剔除 `PYTHONHOME/PYTHONPATH/VIRTUAL_ENV/PYTHONSTARTUP/PYTHONUSERBASE` 后合并传感器自定义 env，并强制 `PYTHONIOENCODING=utf-8`；Windows 走 `taskkill /T /F` 整树击杀，POSIX 走 `terminate`；关闭 stdin 写端且吞掉已关闭/缺失管道的异常。
- `SensorManager` 与 `AcpSensorBridge` 的公开行为、日志文案与调用顺序保持不变；`bridge.extract_file_paths` 继续可用（重新导出）。
- 官方下载地址仍指向 `PurrPod/sensors`，候选 URL 顺序保持「包目录布局优先、单文件其次」。

## 验收标准

- [ ] AC-1：`normalize_candidate` 对 8 种合法形态返回规范化路径，5 种非法形态返回 `None`。
- [ ] AC-2：`extract_file_paths` 能从 markdown 链接与裸路径提取、去重、过滤不存在项与非文件项，并返回宿主绝对路径。
- [ ] AC-3：`build_sensor_env` 清除父进程 Python 变量、合并 cfg、不修改入参。
- [ ] AC-4：`sensor_command` / `candidate_urls` 的输出顺序与内容稳定。
- [ ] AC-5：`kill_process_tree` 在 Windows/POSIX 下分别调用 `taskkill`/`terminate`，并总是关闭 stdin。
- [ ] AC-6：`SensorManager` 现有公开方法与 `AcpSensorBridge` 行为不变（现有测试全绿）。

## 非目标

- 不改 watchdog 的轮询周期、下载线程模型与 ACP 桥的事件翻译。
- 不新增传感器协议字段或配置项。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_sensor_file_refs.py` | AC-1、AC-2 |
| L0 | `tests/l0/test_sensor_processes.py` | AC-3、AC-4、AC-5 |
| L0/L1 | 现有全套 | AC-6 |

## 风险与回滚

- 纯搬运 + 薄委托，`manager` 保留 `_close_stdin` / `_kill_process_tree` 私有方法名，避免外部（或测试）依赖断裂。
- 若 Windows 下 `taskkill` 行为异常，可回滚 `manager` 内的两个薄封装为旧实现。
