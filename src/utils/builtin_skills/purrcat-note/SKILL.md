---
name: purrcat-note
description: 随手记（builtin-note）插件：用户的日记与计划面板，用 purrcat 卡片把时间段变成可派发的任务，并在卡片上实时显示 RUNNING/DONE、耗时与 token。用户提到随手记、笔记、日记、计划卡片、把某件事派发出去时使用。
---

# 随手记

## 这是什么

「随手记」是极简模式的面板插件（`builtin-note`），本质是**按天归档的 Markdown 日记/计划**：

- 文件位置：`~/.purrcat/notes/<YYYY-MM-DD>.md`，一天一个文件；内容为空时不落盘。
- 用户在这里写日记、列计划；带 `purrcat` 代码块的条目会显示成卡片，并出现在顶部时间线上。
- 卡片可以绑定 Worker 并由用户点「立即执行」，或在时间线到点时自动派发。
- 卡片会实时展示任务状态（WAITING / RUNNING / DONE / ERROR）、耗时与 token。

消息里如果带有「笔记文件」路径，需要看上下文时直接读取该日期的 Markdown。

## 卡片格式

````markdown
```purrcat@default/tsk_ab12cd34
- RUNNING 09:00~10:00 60min
# 写周报
把本周进展整理成周报并归档。
```
````

规则：

- 围栏第一行 `purrcat@<target>[/<task_id>]`
  - `target = main`：派发给主会话（你）； `target = default`：派发给默认 DAG 图（后台任务）。
  - `target = none`：只展示，不派发；到点由宿主弹应用级提醒，用户点「立即执行」即把卡片标记为 `DONE`。
  - `/task_id` 可选，是后台任务 ID；**有它就代表这张卡会实时监听任务状态、耗时和 token**。
- 第二行 `- <STATE> hh:mm~hh:mm <N>min`
  - `STATE` 只能是 `TODO` / `WAITING` / `RUNNING` / `DONE` / `ERROR`，它跟随卡片勋章变化。
  - 时间段可省略；省略时卡片不进时间线。`Nmin` 可省略，会按时间段自动推算。
- `# 标题` 是卡片标题（也可把标题写在第二行末尾）。
- 其余行是描述，支持 Markdown。

## 让卡片显示实时进度

1. 用户绑定 Worker 后，插件把关键字写成 `- WAITING`，围栏写成 `purrcat@default`（还没有任务）。
2. 执行后插件会写入任务 ID：`purrcat@default/<task_id>`，关键字变 `- RUNNING`。
3. 插件轮询 `GET /api/tasks/<task_id>/state`、`/elapsed`、`/token`，在卡片底部显示耗时与 token；
   任务进入终态后自动把关键字改成 `- DONE` 或 `- ERROR`。
4. **不要删除围栏里的 `/task_id`**，否则卡片失去进度与耗时数据；也不要把 `DONE` 改回 `TODO`，
   除非用户明确要求重跑。`DONE` 勋章不可点击，防止二次执行。
5. 把关键字改回 `- TODO` 会丢弃旧的执行记录、让卡片重新参与定时（围栏里的旧 task_id 在下一次派发时被覆盖），
   所以「重跑」就是在 Markdown 里改回 `TODO`。

## 什么时候该动它

- 用户说「帮我计划一下今天」「把这几件事排进随手记」：可以直接编辑当天的 Markdown 追加卡片，
  保持上面格式；需要排时间就用 `hh:mm~hh:mm`。
- 用户问某张卡为什么没跑：检查时间段是否已过、`target` 是否为 `none`、关键字是否已是 `DONE`。
- 用户要做后台任务并需要看进度：保留 `purrcat@default/<task_id>` 和 `- RUNNING`。
- 插件只在自己保存/刷新时重读文件；如果直接改了 Markdown，提醒用户在面板点刷新或重新打开日期。
