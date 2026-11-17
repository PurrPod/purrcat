# Note 日归档 `/api/note`

> 源码：`src/server/api/note.py` ｜ 前缀：`/api/note` ｜ 端点：3 个

笔记按天归档到 `~/.purrcat/notes/<YYYY-MM-DD>.md`。日期必须是合法的 `YYYY-MM-DD`，否则返回 `400`。内容为空（仅空白字符）时不落盘，已有文件会被删除。

## GET `/api/note`

读取指定日期的笔记，文件不存在时返回空内容（不报错）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `date` | query | string | 是 | 目标日期，格式 `YYYY-MM-DD` |

**响应**

```json
{
  "date": "2026-11-17",
  "content": "# 今日\n- 09:00 喝水",
  "path": "C:\\Users\\me\\.purrcat\\notes\\2026-11-17.md"
}
```

`path` 是该日期归档文件的绝对路径，供插件在向主 Agent 派发任务时附带来源文件。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/note?date=2026-11-17'
```

---

## PUT `/api/note`

整体覆盖写入指定日期的笔记；内容为空白时删除该日文件。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| `date` | body | string | 是 | 目标日期，格式 `YYYY-MM-DD` |
| `content` | body | string | 否 | 笔记全文；空白表示清空并删除文件 |

**响应**

```json
{ "status": "success", "date": "2026-11-17", "deleted": false }
```

内容为空白时 `deleted` 为 `true`。

**示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/note' \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-11-17","content":"# 今日\n- 09:00 喝水"}'
```

---

## GET `/api/note/dates`

列出所有已有归档的日期，按倒序返回。

**请求**

无参数。

**响应**

```json
["2026-11-17", "2026-11-16"]
```

**示例**

```bash
curl 'http://127.0.0.1:8000/api/note/dates'
```
