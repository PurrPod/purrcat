# SPEC-038 默认 PARADIGM 模板单一来源与恢复默认

## 背景

默认 Agent Loop 曾经有两份仓库文本：`src/utils/initial_templates.py` 里的字面量
（首启播种 `~/.purrcat/paradigms/PARADIGM.yaml`）与 `src/agent/system_rules/PARADIGM.yaml`
（读取兜底）。两份已经漂移，改一处不生效。用户目录副本允许自定义，因此不能用逐字覆盖策略，
只能提供显式的「恢复默认」。

## 验收标准

- [ ] AC-1：默认范式模板只有 `src/agent/system_rules/PARADIGM.yaml` 一份；
  `initial_templates.DEFAULT_PARADIGM_YAML` 直接读取该文件，两者逐字相同。
- [ ] AC-2：模板不再包含 `on_loop_start` 的 `exist_check @RULES`。
- [ ] AC-3：`POST /api/paradigms/reset` 把 `~/.purrcat/paradigms/PARADIGM.yaml` 覆盖为模板，
  返回 `{ok, name:"PARADIGM", path}`；同目录下其它自定义 loop 保持不变。
- [ ] AC-4：进化工厂 Agent Loop 页只在默认 `PARADIGM.yaml` 页面显示「恢复默认」按钮，
  点击需二次确认，成功后重新载入；沙盒产物与其它 loop 不显示。
- [ ] AC-5：打包后仍可读取模板（`collect_all('src')` 已包含该 YAML）。

## 非目标

- 不在启动时自动覆盖用户已自定义的 `PARADIGM.yaml`。
- 不为 RULES.md 生成用户副本。
