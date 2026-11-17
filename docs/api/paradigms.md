# 范式 `/api/paradigms`

> 源码：`src/server/api/paradigms.py` ｜ 前缀：`/api/paradigms` ｜ 端点：5 个

PARADIGM（Agent Loop）配置文件管理接口。所有配置存放于 `~/.purrcat/paradigms/` 下，一个文件一个 loop：`PARADIGM.yaml` 为默认 Agent Loop，其它文件为可切换编辑的备选 loop。

**约定**

- `{name}` 均为不带 `.yaml` 后缀的文件名。
- `POST` 会整体覆盖写回，天然承担「新建」与「保存」两种语义。

---

## GET `/api/paradigms`

列出 paradigms 目录下所有可编辑文件。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |

**响应**

```json
{
  "default": "PARADIGM",
  "files": [
    { "name": "PARADIGM", "is_default": true },
    { "name": "coding", "is_default": false }
  ]
}
```

`default` 为默认棱式的 base 名；`files` 列出目录下所有 `.yaml` 文件（默认文件排在首位）。列出前会确保默认 `PARADIGM.yaml` 存在。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/paradigms'
```

---

## POST `/api/paradigms/reset`

把默认 `PARADIGM.yaml` 覆盖为随包模板 `src/agent/system_rules/PARADIGM.yaml`，用于「恢复默认」。同目录下其它自定义 loop 不受影响。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |

**响应**

```json
{
  "ok": true,
  "name": "PARADIGM",
  "path": "/abs/path/paradigms/PARADIGM.yaml"
}
```

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/paradigms/reset'
```

---

## GET `/api/paradigms/{name}`

读取某个 paradigm 的完整结构化内容（含 hooks）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 | paradigm 名称（不含 `.yaml`） |

**响应**

```json
{
  "name": "PARADIGM",
  "data": {}
}
```

`data` 为该 YAML 解析后的完整 dict（顶层元信息 + `hooks`）。文件不存在返回 `404`；名称不合法或 YAML 解析失败返回 `400`。

**示例**

```bash
curl 'http://127.0.0.1:8000/api/paradigms/PARADIGM'
```

---

## POST `/api/paradigms/{name}`

整体写回（新建 / 保存同一接口）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 | paradigm 名称（不含 `.yaml`） |
| data | body | object | 是 | 要写入的 YAML 对象，需置于 `{ "data": {...} }` 中 |

**响应**

```json
{
  "ok": true,
  "name": "coding",
  "path": "/abs/path/paradigms/coding.yaml"
}
```

`data` 非对象或名称不合法时返回 `400`。写出采用 `sort_keys=False` 以保留键顺序。

**示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/paradigms/coding' \
  -H 'Content-Type: application/json' \
  -d '{"data": {"name": "coding", "hooks": {}}}'
```

---

## DELETE `/api/paradigms/{name}`

删除指定 paradigm（默认 `PARADIGM.yaml` 除外）。

**请求**

| 参数 | 位置 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| name | path | string | 是 | paradigm 名称（不含 `.yaml`） |

**响应**

```json
{
  "ok": true,
  "name": "coding"
}
```

尝试删除默认 `PARADIGM` 或名称不合法时返回 `400`。

**示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/paradigms/coding'
```
