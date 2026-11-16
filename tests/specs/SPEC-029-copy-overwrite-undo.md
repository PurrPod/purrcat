# SPEC-029：FileSystem copy 允许覆盖并提供 undo 回溯

## 背景

`src/tool/filesystem/copy_file.py` 在目标路径已存在时直接抛错拦截（防覆盖保护），Agent 必须换名重试。目的地可写时覆盖是更顺手的语义，且文件工具已有时光机备份体系（`track_edit` / `rewind_file`），覆盖前备份即可安全回溯。

## 行为

- copy 不再因目标已存在而报错；只要目标路径有写权限即可直接覆盖。
- 覆盖形态与备份策略（复用时光机，undo 走既有 `action='undo'` 路径）：
  - 文件 → 文件：备份目标文件后 `copy2` 覆盖；
  - 文件 → 已存在目录：复制进目录，若目录内存在同名文件则先备份该同名文件；
  - 目录 → 已存在目录：合并复制（`dirs_exist_ok=True`），对将被覆盖的同名目标文件逐个先备份；
  - 目录 → 已存在文件：类型冲突，保持报错（无合理覆盖语义）。
- 每个被覆盖文件备份时同步写入 `.meta`，File Changes 窗口可见。
- 返回结果新增 `overwritten` 布尔字段；发生覆盖时 `message` 明确提示覆盖了什么，并提示可对被覆盖路径使用 `action='undo'` 回溯。
- 未发生覆盖时行为与文案不变。

## 验收标准

- [ ] AC-1：目标文件存在时 copy 成功覆盖，返回 `overwritten=True`，message 含覆盖与 undo 提示；undo 后目标恢复为覆盖前内容。
- [ ] AC-2：目标目录内同名文件被覆盖时先备份，可独立 undo 恢复；目录内其他既有文件保留。
- [ ] AC-3：目录合并复制保留目标目录中源目录没有的文件，同名文件被覆盖且可 undo。
- [ ] AC-4：目录 → 已存在文件仍报 `FileSystemError`。
- [ ] AC-5：目标不存在时 `overwritten=False`，文案与旧行为一致。

## 非目标

- 不改 move 的防覆盖锁。
- 不改 undo 路由与时光机备份结构（`track_edit` / `rewind_file_by_id` / meta 格式）。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_tool_copy_file.py` | AC-1 ~ AC-5 |
| 全量 | `tests/l0`、`tests/l1` | 回归 |

## 风险与回滚

- 目录合并覆盖的备份粒度是逐文件，undo 需对每个被覆盖文件分别调用；备份只增不删，不影响既有备份链。
- 回滚方式：恢复 copy_file.py 的存在性拦截分支；测试删除。
