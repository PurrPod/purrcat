# SPEC-037 内置 default 图写保护

## 背景

`default` 图是随包分发的内置资产：启动时与 `src/harness/graph_templates/default/graph.json`
逐字比对，缺失或被改动都会用模板修复。既然用户目录副本不再权威，就必须屏蔽所有写入口，
否则用户会在进化工厂或画布里改完，重启又被覆盖，产生“改了但没生效”的错觉。

## 验收标准

- [ ] AC-1：`graph_factory_init("default", is_upgrade=True/False)` 直接返回错误提示，不创建沙盒；
  提示指向仓库模板路径。
- [ ] AC-2：`graph_request_handle` 拒绝合并名为 `default` 的产物。
- [ ] AC-3：`POST /api/graphs/default` 返回 400，不落盘。
- [ ] AC-4：`POST /api/market/graphs/uninstall` 对 `default` 返回 400，不删除目录。
- [ ] AC-5：进化工厂画布打开 `default` 时工具栏显示「内置图 · 只读」，保存按钮禁用；
  沙盒内的同名草图不受影响（`sandboxCtx` 优先）。

## 非目标

- 不限制在画布上查看、缩放、自动布局 `default`。
- 不阻止用户复制 `default` 为新名字后自由编辑。
