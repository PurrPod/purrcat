# 待办请求 `/api/requests`

> 源码：`src/server/api/request.py` ｜ 前缀：`/api/requests` ｜ 端点：4 个

Agent 审批请求（同意 / 拒绝 / 忽略）的查询与处理。

---

## GET `/api/requests`

获取前端需要弹窗提示的所有待处理请求。返回前会为新请求自动触发 skill_test / sensor_test 的免审测试（测试失败会被静默忽略，不影响返回）。

**请求**

无请求参数。

**响应**

```json
[
  { "id": "req_a1b2c3", "type": "skill_test", "content": "……" }
]
```

请求条目结构由请求工具层决定，此处为示意；无待处理请求时为 `[]`。查询异常返回 500。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/requests'
```

---

## POST `/api/requests/{req_id}/resolve`

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| req_id | path | string | 是 | 请求 ID |
| approved | body | boolean | 否 | 是否同意，默认 `false` |
| feedback | body | string | 否 | 反馈文本，默认空字符串 |
| ignore | body | boolean | 否 | 是否静默忽略，默认 `false` |

**响应**

```json
{ "status": "success", "message": "请求已处理" }
```

处理失败返回 400（`detail` 携带原因），其它异常返回 500；具体字段由请求工具层的返回值决定。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/requests/req_a1b2c3/resolve' \
  -H 'Content-Type: application/json' \
  -d '{"approved": true, "feedback": "同意", "ignore": false}'
```

---

## GET `/api/requests/resolved`

获取所有已处理完毕的请求。

**请求**

无请求参数。

**响应**

```json
[
  { "id": "req_a1b2c3", "approved": true, "feedback": "同意" }
]
```

条目结构由请求工具层决定，此处为示意；无记录时为 `[]`。查询异常返回 500。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/requests/resolved'
```

---

## DELETE `/api/requests/{req_id}`

彻底删除某个请求记录。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| req_id | path | string | 是 | 请求 ID |

**响应**

```json
{ "status": "success", "message": "请求已移除" }
```

请求未找到返回 404，其它异常返回 500。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/requests/req_a1b2c3'
```
