---
name: purrcat-genui
description: 用 PurrCat 内建 GenUI DSL 生成聊天内可交互界面卡片。支持布局、文本、表单、图表、地图、SVG、闪卡与动作回传；输出 genui 围栏代码块即可渲染。
version: 1.0.0
triggers:
  - "GenUI"
  - "生成式 UI"
  - "声明式 UI"
  - "DSL 界面"
  - "聊天内卡片"
  - "可视化卡片"
  - "交互式图表"
  - "genui"
---

# GenUI Skill

## 你是什么

你用 PurrCat 内建的 GenUI 声明式 DSL 输出界面卡片：只写纯文本，宿主负责解析、渲染与交互。
适用于「用界面而不是长文回答」的场景：数据看板、对比、行程地图、表单收集、测验闪卡、步骤 Demo。

不适用：需要真实后端逻辑、自由 CSS/JS、文件下载、跨卡片通信的需求。需要自定义网页时改用 `HtmlView` 或 MCP App。

## 输出方式

推荐「先写文件，再引用」：DSL 落到 `/agent_vm/genui/<名字>.genui`，回复里只放一行引用。

```text
![](/agent_vm/genui/paris.genui)
```

宿主识别到 `.genui` / `.openui` 后缀会读取文件并展开为完整卡片。好处是消息短、可重新编辑、历史里不重复存 DSL。

内联写法仍然支持：在回复里用语言标记为 `genui` 的围栏代码块（也接受 `openui`）。适合一次性的短卡片。

同一个界面不要既写文件又贴内联。

## 内嵌媒体

`![]()` 指向本地文件时，宿主会按扩展名自动展开：

```text
![](/agent_vm/out/trend.png)      // 图片
![](/agent_vm/out/voice.mp3)      // 音频播放器
![](/agent_vm/out/demo.mp4)       // 视频播放器
```

- 支持：图片 png/jpg/jpeg/gif/webp/svg/avif；音频 mp3/wav/ogg/m4a/aac/flac/opus；视频 mp4/webm/ogv/mov/m4v/mkv。
- 远程 http(s) 媒体同样可用；远程图片保持原生 `<img>`。
- 方括号里的文字会作为文件名/说明展示。
- 路径支持 `/agent_vm/...`、`file://`、Windows 绝对路径、`./`、`../`。

卡片内部也可以直接用 `Audio` / `Video` 组件，见下表。

## 语法

```text
$state = initialValue      // 声明可交互状态
name = Title("标题")        // 具名节点，可被引用
root = Col([name, Text("...")], 3)
```

- 一行一条语句；数组和对象内部可以换行。`//` 到行尾是注释。
- 值：字符串（单/双引号，支持 `\n` `\"`）、数字、`true`/`false`/`null`、数组 `[a, b]`、对象 `{k: v}`。
- 引用：`name`；成员访问 `a.b`；索引 `a[0]`；一元 `!` `-` `+`；二元 `+ - * / % == != > < >= <= && ||`；三元 `a ? b : c`。
- 组件：`Name(args)`；函数：`@Name(args)`；动作用 `Action([@ToAssistant("...")])` 组合。
- 允许前向引用；语法错误的行整条丢弃，不影响其它行。
- 组件参数是**按位置**传的，不需要写参数名。

样式取值约定：

| 类型 | 取值 |
| --- | --- |
| 间距 / gap / padding | 数字 = 4px 的倍数（`3` → 12px），也可写 `"12px"` |
| 颜色 | `ink` `muted` `faint` `surface` `info` `success` `warning` `danger` `purple` `pink` `primary` `accent` `chart1`~`chart6`，或 `"#RRGGBB"` |
| 圆角 | `sm` `md` `lg` `xl` `full`，或数字（px） |
| 对齐 | `start` `center` `end` `stretch`；justify 另支持 `between` `around` `evenly` |

## 组件速查

### 布局

| 组件 | 参数 |
| --- | --- |
| `Col` | `(children, gap, align)` |
| `Row` | `(children, gap, align, justify, wrap)` |
| `Box` | `(children, direction, gap, padding, background, radius, border, width, height, flex, justify, wrap)` |
| `Grid` | `(children, columns=2, minWidth=0, gap)`；`minWidth > 0` 时自动列宽 |
| `Card` | `(children, variant="outline"|"soft", padding, gap)` |
| `Carousel` | `(items, itemWidth=240, gap)` |
| `Popover` | `(trigger, content)`；trigger 为字符串或组件 |
| `Divider` | `()` |
| `Spacer` | `()` |

### 文本

| 组件 | 参数 |
| --- | --- |
| `Title` | `(text, size="sm"|"md"|"lg"|"xl"|"2xl"|"3xl", color)` |
| `Text` | `(text, size="xs"|"sm"|"md"|"lg", color, weight="normal"|"medium"|"semibold", italic, strike, tabular, maxLines)` |
| `Caption` | `(text, color)` |
| `Label` | `(text)` |
| `Badge` | `(text, color="neutral"|"info"|"success"|"warning"|"danger"|"purple"|"pink"|"ink")` |
| `Link` | `(text, url)` |
| `List` | `(items, marker="bullet"|"number"|"none", timeline)` |
| `ListItem` | `(title, description, markerText?, extraChildren)`；markerText 是自定义标记文本（如 `"1"`、`"★"`），不是 List 的标记样式 |
| `Markdown` | `(markdownText)` |
| `Quote` | `(textOrChildren, cite)` |
| `Code` | `(code, language)` |
| `Math` | `(tex, inline=false)` |

`Title`/`Text`/`Caption`/`Label` 的文本支持内联标记：`**粗体**`、`*斜体*`、`` `代码` ``、`[文字](url)`。
关键词着色用 `<red>文字</red>`，可用 `red` `green` `yellow` `blue` `orange` `purple` `pink` `gray` `muted` `info` `success` `warning` `danger`，内部可再嵌粗体：

```text
Text("营收 <green>+12%</green>，成本 <red>+3%</red>，<yellow>注意</yellow>")
```

未列入的标签（如 `<b>`）按纯文本显示，不会着色。`Markdown` 组件不支持这套着色标记，需要彩色关键词时用 `Text`。

### 输入

| 组件 | 参数 |
| --- | --- |
| `Button` | `(label, action, variant="solid"|"soft"|"outline"|"ghost", color, size="sm"|"md"|"lg", icon, disabled, block)` |
| `IconButton` | `(icon, action, label, variant="ghost")` |
| `Pressable` | `(children, action, selected, padding, background, radius)` |
| `Input` | `($bind, label, type="text"|"number", placeholder)` |
| `TextArea` | `($bind, label, placeholder, rows)` |
| `Select` | `($bind, options, label, placeholder)` |
| `SegmentedControl` | `($bind, options, block)` |
| `Slider` | `($bind, min, max, step, label, unit)` |
| `Checkbox` | `($bind, label, _, lineThrough)` |
| `RadioGroup` | `($bind, options, label, variant)` |
| `DatePicker` | `($bind, label, min, max)` |
| `Timer` | `($bind, label)`；`$bind` 为总秒数 |
| `Form` | `(children)`；内部绑定会在按钮动作里汇总为 `values` |

- `options` 可写字符串数组，或 `{value, label, description}` 对象数组。
- 输入类组件第一个参数必须是 `$变量`，用户改动会写回状态并重渲染。
- `Form` 里的 `Button` 触发动作时，自动把表单内所有绑定作为 `values` 一起回传。

### 媒体与数据

| 组件 | 参数 |
| --- | --- |
| `Icon` | `(name, size="sm"|"md"|"lg"|像素数, color)` |
| `Image` | `(url, alt, aspectRatio, fit="cover"|"contain", radius)` |
| `SearchImage` | `(query, aspectRatio=1.4)`；按描述生成图片 |
| `Audio` | `(src, title?, subtitle?)`；本地路径自动转预览地址 |
| `Video` | `(src, poster?, title?, aspectRatio?)` |
| `Table` | `(columns, rows)`；rows 用数组或按列名取值 |
| `Chart` | `(type, rows, xKey, series[], format, currency, stacked, height)` |
| `Map` | `(markers, route, selectedBinding, height)` |
| `MapMarker` | `(label, lat, lng, description, category)`，只能放在 `Map` 的 markers 里 |
| `YouTube` | `(urlOrId, title)` |

- `Chart` 的 `type`：`bar` `line` `area` `pie` `donut` `scatter`；`format`：`number` `currency` `compact` `percent`。
- `Chart` 的 `rows` 是对象数组，`xKey` 是横轴字段，`series` 是数值字段名数组。
- `Map` 的 `markers` 可直接写对象数组，也可写 `MapMarker(...)`；`route=true` 按顺序连线。
- 常用图标名：`pin` `map-pin` `clock` `search` `check` `check-circle` `x` `star` `heart` `user` `users` `settings` `calendar` `file` `folder` `download` `upload` `play` `pause` `plus` `minus` `arrow-right/left/up/down` `chevron-down/up/right/left` `info` `alert-circle` `sun` `moon` `home` `mail` `phone` `link` `external-link` `refresh` `trash` `edit` `globe` `image` `code` `database` `cpu` `zap` `activity` `trending-up` `trending-down` `dollar`。未知名字回退为 info 图标。

### 绘图 / 播放 / 扩展

| 组件 | 参数 |
| --- | --- |
| `Svg` | `(children, width, height)`；作为画布 |
| `G` | `(children, transform, fill, stroke)` |
| `Circle` | `(cx, cy, r, fill)` |
| `Ellipse` | `(cx, cy, rx, ry, fill)` |
| `Rect` | `(x, y, width, height, rx, fill)` |
| `Line` | `(x1, y1, x2, y2, stroke, width)` |
| `Path` | `(d, fill, stroke, width)` |
| `Polyline` | `(points, fill, stroke, width)` |
| `Polygon` | `(points, fill, stroke)` |
| `SvgText` | `(text, x, y, size, fill, anchor="start"|"middle"|"end")` |
| `Flashcard` | `(frontChildren, backChildren, hint)`；点击翻转 |
| `Celebration` | `(show, count=40)`；`show` 为真时飘彩带 |
| `HtmlView` | `(html, height=300, title)`；sandbox iframe，仅限简单静态 HTML |

## 函数

```text
Count First Last Sum Avg Min Max
Sort(list, field, "asc"|"desc")
Filter(list, field, "=="|"!="|">"|"<"|">="|"<="|"contains", value)
Top(rows, field, n, "asc"|"desc")  Between(rows, field, min, max)
Each(list, "item", template)       // template 惰性求值，不需要包字符串

Round(value, decimals)  Abs Floor Ceil  Pow(a, b)  Sqrt  Clamp(v, min, max)
Percent(part, total)  Lerp(a, b, t)  Random(min, max, integer)
Sin Cos Tan  Range(start, end, step)  Percent

Append Prepend Concat Remove RemoveAt Update Toggle Includes Find IndexOf
Take Slice Unique Reverse Pick Shuffle Flatten Chunk

Format(value, "number"|"currency"|"compact"|"percent", decimals, currency)
Join(list, sep, field)  Plural(n, word, plural?)  Pad(v, length, char?)
Upper Lower Trim Capitalize Split Replace
Duration(seconds, "clock"?)  Default(value, fallback)  MixColor(from, to, t)
Convert(value, fromUnit, toUnit)  Allocate(total, weights[], decimals)  Payment(principal, ratePercent, periods)

Now()  Today()  FormatDate(value, "date"|"short"|"long"|"weekday"|"month"|"time"|"datetime"|"iso")
AddDays AddMonths DaysBetween MonthsBetween StartOf(value, "week"|"month"|"year")
GroupBy(rows, key, field, "sum"|"avg"|"count"|"min"|"max")
Pivot(rows, rowKey, colKey, field, kind)
Bucket(rows, dateField, "day"|"week"|"month", field, kind)
Cumulative(rows, field)  MovingAvg(rows, field, window)  Change(current, previous)
Histogram(values, bins, min?, max?)  Stats(values)
```

## 动作

```text
@ToAssistant(message, context?)    // 把文本写回输入框
@OpenUrl(url)
@Set($state, value)
@Reset($a, $b)                     // 不传参数则重置全部状态
@CopyToClipboard(text)
Action([step1, step2])             // 顺序执行
```

按钮的第二个参数就是动作，例如：

```text
Button("提交", Action([@ToAssistant("已提交：", {source: "form"})]), "solid", "primary")
```

## 示例

### 1. 数据看板

```genui
$range = "7d"
$rows = [{d: "周一", uv: 120}, {d: "周二", uv: 180}, {d: "周三", uv: 150}, {d: "周四", uv: 240}]
total = @Sum(@Each($rows, "r", r.uv))
root = Col([
  Row([Title("访问趋势", "xl"), Spacer(), Badge("实时", "success")], 2, "center"),
  Row([
    Card([Caption("总 UV"), Title(total, "2xl")], "soft"),
    Card([Caption("日均"), Title(@Round(@Avg(@Each($rows, "r", r.uv))), "2xl")], "soft"),
    Card([Caption("峰值"), Title(@Max(@Each($rows, "r", r.uv)), "2xl")], "soft")
  ], 3),
  SegmentedControl($range, [{value: "7d", label: "7 天"}, {value: "30d", label: "30 天"}], true),
  Chart("area", $rows, "d", ["uv"], "number", null, false, 220)
], 4)
```

### 2. 表单收集

```genui
$name = ""
$plan = "pro"
$agree = false
root = Form([
  Title("开通工作区"),
  Input($name, "名称", "text", "输入工作区名称"),
  Select($plan, [{value: "free", label: "Free"}, {value: "pro", label: "Pro"}, {value: "team", label: "Team"}], "套餐"),
  Checkbox($agree, "我已阅读并同意服务条款"),
  Button("提交", Action([@ToAssistant("开通工作区")]), "solid", "primary", "md", "check", @Count(@Filter([$name], null, "==", "")) > 0, true)
], 3)
```

### 3. 行程地图 + 清单

```genui
$spot = "Paris"
root = Col([
  Title("巴黎三日"),
  Map([
    MapMarker("Paris", 48.8566, 2.3522, "第 1-2 天", "city"),
    MapMarker("Versailles", 48.8049, 2.1204, "第 3 天", "palace")
  ], true, $spot, 280),
  List([
    ListItem("Paris", "卢浮宫 · 塞纳河夜游", "1"),
    ListItem("Versailles", "宫堡与花园", "2")
  ], "none"),
  Caption("当前选择：" + $spot)
], 3)
```

### 4. 测验闪卡

```genui
$i = 0
$cards = [{q: "TCP 三次握手第一步？", a: "客户端发送 SYN"}, {q: "第二步？", a: "服务端回复 SYN+ACK"}, {q: "第三步？", a: "客户端发送 ACK"}]
card = $cards[$i % @Count($cards)]
root = Col([
  Row([Caption("卡片 " + ($i + 1) + " / " + @Count($cards)), Spacer(), Badge("点击翻转", "info")], 2, "center"),
  Flashcard(card.q, card.a, "答案在背面"),
  Row([
    Button("上一张", @Set($i, $i - 1), "ghost"),
    Button("下一张", @Set($i, $i + 1), "solid", "primary")
  ], 2, "center")
], 3)
```

### 5. SVG 示意图

```genui
root = Col([
  Caption("请求链路"),
  Svg([
    Rect(20, 40, 90, 44, 10, "chart2"),
    SvgText("Client", 65, 67, 13, "ink", "middle"),
    Line(110, 62, 190, 62, "muted", 2),
    Rect(190, 40, 90, 44, 10, "chart3"),
    SvgText("API", 235, 67, 13, "ink", "middle")
  ], 300, 120)
], 2)
```

## 常见坑

1. **一行一条语句**：`root = Col([` 可以换行，但新语句必须重新以 `名字 =` 开头。
2. **动作要包在 `Action([...])` 里**再传给按钮，直接写多个 `@...` 会只取第一个。
3. **输入组件第一参必须是 `$变量`**；写 `Input("name")` 不会绑定，也不会回传。
4. **`@Each` 的模板不要加引号**：`@Each($rows, "r", r.name)`，不是 `"r.name"`。
5. **`Chart` 的 rows 必须是对象数组**，不是 `[[x, y]]`；`Table` 两种都行。
6. **`List` 的 items 里放 `ListItem(...)`**，纯字符串也可以，但没有标题/描述层级。标记样式写在 `List` 的第二个参数（`"bullet"` / `"number"` / `"none"`）；`ListItem` 的第三个参数是自定义标记文本，不要写 `"none"`。
7. **`MapMarker` 不能单独渲染**，必须作为 `Map` 的第一参数组元素。
8. **`Timer` 的绑定是秒数**，组件自己负责倒计时与暂停/重置。
9. **`Svg` 子节点只能是绘图组件**，不要把 `Text` 塞进 `Svg`，文字用 `SvgText`。
10. **不要堆太深**：卡片总层级控制在 4 层以内，单项列表超过 12 条先聚合或分页。
11. **未知组件不会报错**，只会渲染成灰色占位；自查拼写。
12. **`HtmlView` 是 sandbox iframe**，不能访问宿主 DOM，也不要依赖外部脚本。
13. **文件引用必须带可识别扩展名**：`.genui` 或 `.openui` 才会展开成卡片，写成 `.txt` 只会当普通图片链接。
14. **媒体链接用 `![]()`**，普通 `[]()` 是链接不会内嵌；没有扩展名的流地址无法识别类型。
15. **文件名避免空格和中文标点**，路径用 `/` 分隔，统一放到 `/agent_vm/genui/` 或 `/agent_vm/out/`。

## 调试

- 预览页：`http://127.0.0.1:<apiPort>/minimal/plugins/builtin/builtin-history/genui/preview.html`，粘贴 DSL 即可看到渲染结果，并提供「组件总览」示例。
- 运行时入口：`window.PurrCatGenUI.mount(el, source, options)`；纯 HTML 输出用 `window.PurrCatGenUI.renderHTML(source, state)`。
- 渲染报错会显示为 `.gui-error` 卡片，提示「组件名: 错误信息」。
