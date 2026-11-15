# SPEC-026 GenUI 声明式组件库

## 状态

Implemented

## 背景

MCP Apps 依赖服务端提供 `ui://` HTML，宿主无法控制视觉一致性，也无法复用数据渲染能力。
本规格引入宿主内建的声明式 UI：模型或工具输出一段纯文本 DSL，宿主用它渲染成聊天内的卡片，
所有组件样式、交互与主题由宿主维护。

## DSL 语法

```text
$state = initialValue        # 声明可交互状态，渲染为 $state 绑定
name = Title("Hello")        # 声明节点，按名字被引用
root = Col([name, Text("...")], 3)
```

- 语句：`标识符 = 表达式`；`$标识符 = 表达式` 声明状态。
- 表达式：字符串（单/双引号）、数字、`true/false/null`、数组、对象、引用、成员访问 `a.b`、索引 `a[0]`、
  一元 `!` `-` `+`、二元 `+ - * / % == != > < >= <= && ||`、三元 `? :`。
- 函数调用：`@Name(args)`；组件调用：`Name(args)`。
- 引用可前向声明；未定义引用求值为空。语法错误的语句被整条丢弃，便于流式输出。
- 注释：`//` 到行尾。

## 组件

| 分类 | 组件 |
| --- | --- |
| 布局 | `Col` `Row` `Box` `Grid` `Card` `Carousel` `Popover` `Divider` `Spacer` |
| 文本 | `Title` `Text` `Caption` `Label` `Badge` `Link` `List` `ListItem` `Markdown` `Quote` `Code` `Math` |
| 输入 | `Button` `IconButton` `Pressable` `Input` `TextArea` `Select` `SegmentedControl` `Slider` `Checkbox` `RadioGroup` `DatePicker` `Timer` `Form` |
| 媒体数据 | `Icon` `Image` `SearchImage` `Audio` `Video` `Table` `Chart` `Map` `MapMarker` `YouTube` |
| 绘图 | `Svg` `G` `Circle` `Ellipse` `Rect` `Line` `Path` `Polyline` `Polygon` `SvgText` |
| 播放与扩展 | `Flashcard` `Celebration` `HtmlView` |

组件参数按位置传入；颜色名（`info` `success` `warning` `danger` `purple` `pink` `chart1..6`）
映射到主题变量。输入组件的第一个参数是 `$变量` 绑定。

## 函数

`Count First Last Sum Avg Min Max Sort Filter Round Abs Floor Ceil Each Append Prepend Concat
Remove RemoveAt Update Toggle Includes Find IndexOf Take Slice Unique Reverse Range Pick Shuffle
Flatten Chunk Pow Sqrt Sin Cos Tan Random Clamp Percent Lerp Allocate Payment Convert Format Join
Plural Pad Upper Lower Trim Capitalize Split Replace Duration Default MixColor Now Today FormatDate
AddDays AddMonths DaysBetween MonthsBetween StartOf GroupBy Pivot Top Between Bucket Cumulative
MovingAvg Change Histogram Stats`

动作步骤：`ToAssistant` `OpenUrl` `Set` `Reset` `CopyToClipboard`，通过 `Action([...])` 组合。

## 集成

- 助手消息中语言标记为 `genui` / `openui` 的围栏代码块渲染为 `.genui-card`。
- 工具结果的 `structuredContent` 若为 `{kind: "openui"|"genui"|"openui-lang", source|dsl|ui: "..."}`，
  渲染为卡片；否则回退到 JSON 兜底卡片。
- `Map` 接受数据对象数组，也接受 `MapMarker(label, lat, lng, description, category)` 子组件。
- `ToAssistant` 与 `@Set` 等动作写回聊天输入框，用户可见、可编辑。
- 助手可用 `![](/agent_vm/genui/x.genui)` 引用 DSL 文件，宿主读取后展开为卡片；读取失败显示错误占位。
- 助手可用 `![](路径)` 内嵌本地图片、音频、视频：本地路径转 `/api/filesystem/preview`，远程图片保持原生 `<img>`。
- `Audio` / `Video` 组件同样支持本地路径自动转预览地址。
- 历史重建前销毁 GenUI 实例（清理定时器与事件）；状态按 DSL 内容哈希缓存。

## 验收标准

- AC-1 解析器支持全部语法与容错，非法语句整条忽略。
- AC-2 组件全部可渲染，未知组件降级为提示卡片而不抛错。
- AC-3 输入组件通过 `$变量` 双向绑定，变化后整树重渲染并恢复焦点。
- AC-4 `@Each`/`@Filter`/`@Sort` 等函数覆盖文档列出的全部函数。
- AC-5 图表支持 bar/line/area/pie/donut/scatter，输出 SVG 且带图例与提示。
- AC-6 地图按经纬度投影绘制标记、标签与路线，可点击写回绑定。
- AC-7 `Svg` 系列组件产出命名空间正确的 SVG 元素。
- AC-8 聊天内代码块与工具 `structuredContent` 均能渲染为卡片。
- AC-9 历史重建时 GenUI 实例被销毁，不残留定时器。
- AC-10 L0 测试通过 node harness 覆盖解析、求值与 HTML 输出。
- AC-11 `List` 的标记样式只取第二个参数；`ListItem` 第三参为自定义标记文本，写 `none`/`bullet`/`number` 时不显示。
- AC-12 `![](路径)` 按扩展名识别：本地图片/音频/视频转内嵌媒体，`.genui` 转占位卡并在插入后展开；远程图片保持原生 `<img>`。
- AC-13 本地路径统一转成 `/api/filesystem/preview?path=...`，远程地址原样使用；`Audio`/`Video` 组件复用同一转换。
