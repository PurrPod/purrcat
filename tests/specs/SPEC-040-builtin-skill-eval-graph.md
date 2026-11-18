# SPEC-040 内置 skill_eval 图与新架构对齐

## 背景

`skill_eval` 原先只存在于用户图目录，随架构演进已经与节点定义脱节：
`message_card_builder` 现在固定输出 `role=user`，不再提供 `role` 输入端口，
旧图里 `string_system_role → nd_msg_sys.role` 的连线失效，人设也没有进入系统提示位。
同时技能盲测依赖这张图存在，缺图时只能静默跳过。

本规格把它提升为仓库内置图（与 `default` 同一套播种与写保护），
并按当前 agent_loop 约定把人设改由 `on_build_system_prompt` 注入。

## 验收标准

- [ ] AC-1：模板位于 `src/harness/graph_templates/skill_eval/graph.json`，`name` 与文件夹名一致。
- [ ] AC-2：启动时 `ensure_builtin_graphs` 同步 `default` 与 `skill_eval`；缺失或被改动都按模板修复，结果与模板逐字一致；已一致时不写盘。
- [ ] AC-3：进化工厂新建/升级/合并、`POST /api/graphs/{name}`、市场卸载对任一内置图都拒绝，提示含「内置图」与模板位置。
- [ ] AC-4：模板通过 `validate_graph_folder`，0 error、0 warning，且能被 `build_node_instances` 正常实例化。
- [ ] AC-5：模板保留盲测运行器契约：四个必填入参、`nd_agent_exec` 节点 id、输出键 `exec_summary` / `eval_result`。
- [ ] AC-6：模板不再包含 `string_system_role` 与 `role` 连线；执行工人与 QA 裁判的人设写入各自 `agent_loop` 的 `on_build_system_prompt`。
- [ ] AC-7：进化工厂画布打开任一内置图时显示「内置图 · 只读」并禁用保存；沙盒内同名草图不受影响。

## 非目标

- 不改变盲测流程、评分标准与 `src/evolve/skill/` 的运行逻辑。
- 不阻止用户复制内置图为新名字后自由编辑。
