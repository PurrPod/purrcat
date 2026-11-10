# SPEC-004：Hook 引用解析与沙盒路径映射

## 背景

PARADIGM 钩子用 `@RULES`、`@SYS`、`@USERQUERY` 这类符号引用内容，用 `/agent_vm/...`、`@TASKSPACE/sub` 这类写法引用文件。两处解析逻辑此前只有零散覆盖，边界行为（别名缺失、前缀误判、配置切换）没有断言。

## 行为

### @ 引用展开

- `_expand_refs` 递归处理 str / dict / list，非字符串原样返回，且不修改输入对象。
- 展开是单次左到右替换：替换出来的文本不会被再次当成引用。
- `resolve(alias)` 返回 `None` 时保留原始 `@符号`（文件缺失、当前阶段无此上下文）。
- `@USERQUERY` 只拼 `received_messages` 中 `type=user` 的内容，多条以换行连接；系统注入不参与。
- `file_operation` 的 `path` 走 `_resolve_path`，不做内容展开；`@ALIAS` 命中路径别名，`@ALIAS/sub` 拼到别名目录下。
- 动态别名（`add_alias`）同时支持 host 路径与内容两种形态，新增后立即参与后续 `execute` 的匹配。

### 沙盒路径

- `/agent_vm/...`、`agent_vm/...` 映射到 `AGENT_VM_DIR`，裸根映射到目录本身。
- 仅当完整匹配 `/agent_vm` 或其后紧跟分隔符时才视为沙盒路径；`/agent_vm_backup/...` 这类同前缀路径必须原样返回。
- 映射使用运行期配置的 `AGENT_VM_DIR`，测试中替换该值应立刻生效。

## 验收标准

- [ ] AC-1：`_expand_refs` 的已知别名、未知别名、嵌套容器、不二次展开四种行为均有用例。
- [ ] AC-2：`@USERQUERY` 过滤非 user 消息；缺失文件别名保留原文。
- [ ] AC-3：`file_operation` 用原始路径解析别名并读到文件内容。
- [ ] AC-4：动态别名注册后立即生效。
- [ ] AC-5：hook 与 `convert_sandbox_path` 对 `/agent_vm`、`agent_vm`、裸根、同前缀干扰项均按规则映射，且受 `AGENT_VM_DIR` 配置影响。

## 非目标

- 不改变钩子动作类型与执行顺序。
- 不处理 `.purrcat/`、`src/`、`@ALIAS/sub` 之外的新路径语法。
- 不引入路径穿越白名单（当前仅记录，不在本 spec 修复）。

## 测试矩阵

| 层级 | 位置 | 覆盖的验收标准 |
| --- | --- | --- |
| L0 | `tests/l0/test_hook_refs.py` | AC-1 ~ AC-4 |
| L0 | `tests/l0/test_sandbox_path.py` | AC-5 |

## 风险与回滚

- `_resolve_path` 的前缀判断从 `startswith("/agent_vm")` 收紧为「完整匹配或后接分隔符」，修复同前缀目录被误映射的问题；原有合法路径行为不变。
