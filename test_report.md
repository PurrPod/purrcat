# PurrCat 新架构工具异常处理测试报告

**测试时间**: 2026-04-29 22:40 ~ 23:16  
**测试环境**: main 分支（commit a2dfe05）  
**测试人**: Agent

---

## 1. Fetch 工具

### 1.1 source 参数不合法

```json
{
  "source": "invalid"
}
```

**结果**: ✅ 
```
source参数不合法，合法参数有：skill, mcp, web
```

### 1.2 source=skill 无 name

```json
{
  "source": "skill"
}
```

**结果**: ✅
```
搜索skill必须传入参数name
```

### 1.3 source=mcp 无 server_name

```json
{
  "source": "mcp",
  "server_name": ""
}
```

**结果**: ✅
```
搜索mcp必须传入参数serve_name
```

> ⚠️ 提示文案写的是 `serve_name` 而非 `server_name`，与参数名不一致

### 1.4 source=web 无 url

```json
{
  "source": "web"
}
```

**结果**: ✅
```
搜索web必须传入参数url
```

### 1.5 skill 未找到

```json
{
  "source": "skill",
  "name": "nonexistent-skill-12345"
}
```

**结果**: ✅
```
未在技能库中找到技能 nonexistent-skill-12345，请确保该技能：
1.文件夹内含有SKILL.md并配置了相关字段
2.Skill文件夹正确放置在技能库内
```

### 1.6 mcp 未找到

```json
{
  "source": "mcp",
  "server_name": "nonexistent-mcp"
}
```

**结果**: ✅
```
未在缓存文件中找到关于 nonexistent-mcp 的对应MCP工具，请确保： 
1.对应的 相关 工具存在于该MCP工具集中，可使用search工具进行搜索确保其存在
2.你的老板正确进行了该MCP服务的白名单配置并安装对应的MCP
也可能是老板刚安装上，需要重启PurrCat
```

### 1.7 web 网络错误

```json
{
  "source": "web",
  "url": "https://nonexistent-domain-12345.com"
}
```

**结果**: ✅
```
网络错误，请确保：
1.网络正常
2.老板正确配置了Tavily API
```

---

## 2. FileSystem 工具

### 2.1 import 路径不存在

```json
{
  "action": "import",
  "path_from": "D:/nonexistent/path/file.txt",
  "path_to": "/agent_vm/"
}
```

**结果**: ✅
```
对应文件路径不存在，请确保正确输入了真实的宿主机文件路径，
可通过指定action=list来梳理本地文件系统结构
如：FileSystem(action="list", path_from=".")
```

### 2.2 export 无 path_to

```json
{
  "action": "export",
  "path_from": "/agent_vm/test.txt"
}
```

**结果**: ✅
```
文件导入导出应当包含path_from和path_to
```

### 2.3 export 沙盒路径不存在

```json
{
  "action": "export",
  "path_from": "/agent_vm/nonexistent-file-12345.txt",
  "path_to": "D:/cat-in-cup/"
}
```

**结果**: ✅
```
检测到输入的沙盒文件路径不存在，请确保文件存在或输入参数正确
```

### 2.4 export 到不允许的目录

```json
{
  "action": "export",
  "path_from": "/agent_vm/cat-in-cup/README.md",
  "path_to": "D:/Windows/System32/"
}
```

**结果**: ✅
```
可导入目录在：['d:\\cat-in-cup', 'd:\\cat-in-cup\\agent_vm']
当前目标目录不在此范围内，可选择导入到允许的目录内
如有特殊需要，请联系老板开启权限
```

### 2.5 import 含黑名单目录 `src/`（老板修复后）

```json
{
  "action": "import",
  "path_from": "D:/cat-in-cup/agent_vm/cat-in-cup",
  "path_to": "/agent_vm/test_import_blacklist"
}
```

**结果**: ❌
```
目录已导入沙盒: /agent_vm/agent_vm/test_import_blacklist/cat-in-cup (7.0MB)
```
`src/` 完整导入，未跳过。验证：
```bash
$ ls /agent_vm/agent_vm/test_import_blacklist/cat-in-cup/src/
__pycache__  agent  cli.py  ...
```

**根因分析**:  
`import_file.py` 的 `_is_denied()` 比较的是沙盒绝对路径（`/agent_vm/cat-in-cup/src`）与宿主机 Windows 路径（`D:\cat-in-cup\...\src`），永远无法匹配。

### 2.6 list 含黑名单目录（老板修复后）

```json
{
  "action": "list",
  "path_from": "D:/cat-in-cup",
  "depth": 1
}
```

**结果**: ✅
```
├── src/  (04-29 12:49)
│   [黑名单，已跳过]
```

---

## 3. 其他工具

### 3.1 Cron — 无效 action

```json
{
  "action": "invalid"
}
```

**结果**: ✅
```
无效的操作类型: invalid。支持的操作: list, add, delete, update
```

### 3.2 Search — 无效 route

```json
{
  "route": "invalid",
  "query": "test"
}
```

**结果**: ✅
```
无效的路由类型: invalid。支持的路由: web, skill, mcp
```

### 3.3 Task — 无效 action

```json
{
  "action": "invalid"
}
```

**结果**: ✅
```
无效的操作类型: invalid。支持的操作: add, inform, kill, list
```

### 3.4 Task add — 缺 name

```json
{
  "action": "add"
}
```

**结果**: ✅
```
缺少必需参数: name
```

### 3.5 Task add — 缺 prompt

```json
{
  "action": "add",
  "name": "test-task"
}
```

**结果**: ✅
```
缺少必需参数: prompt
```

---

## 4. 总结

| 测试项 | 分支数 | 通过 | 失败 |
|--------|--------|------|------|
| Fetch | 7 | 7 | 0 |
| FileSystem | 6 | 5 | 1 |
| Cron | 1 | 1 | 0 |
| Search | 1 | 1 | 0 |
| Task | 3 | 3 | 0 |
| **合计** | **18** | **17** | **1** |

**唯一失败项**: import 时黑名单 `src/` 未跳过 — `_is_denied()` 路径比较跨操作系统不生效。
