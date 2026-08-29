"""
Sensor 指南生成器模块 (evolve/sensor/guide_generator.py)
单文件指南：覆盖协议规范、鉴权求助、文件收发与提交全流程。
"""


def generate_sensor_guide(sensor_name: str, goal: str = "") -> str:
    goal_section = f"\n> 🎯 **本次构建目标**：{goal}\n" if goal else ""
    return f"""# {sensor_name} 传感器工厂指南 (GUIDE)

本指南覆盖协议规范、鉴权规范、文件收发与提交全流程，动手前请先通读。
{goal_section}
## 1. Sensor 是什么

Sensor 是一个**独立的常驻子进程**，由宿主机 SensorManager 用 `uv run <name>.py` 拉起，
通过 stdin/stdout 的**单行 JSON 协议**与宿主机 SensorGateway 双向通信：

* **observe（你 → Agent）**：外部事件（用户消息、提醒、状态变化）推送给 Agent
* **express（Agent → 你）**：Agent 的回复/指令通过你转发到外部渠道（群聊、邮件等）

铁律：
* stdout **只能**输出协议 JSON（一行一条）。调试 print 必须走 stderr：`sys.stdout = sys.stderr`
* 严禁退出主进程。连接崩溃要无限重连（带 sleep 缓冲），守护线程只救意外退出
* 配置凭证一律从环境变量读取（由 activate_sensor.json 的 env 注入），禁止硬编码密钥

## 2. 协议规范

### 出向（stdout → 网关）

文本事件：
```json
{{"method": "observe", "params": {{"content": "[{sensor_name} 收到用户消息] 你好"}}}}
```

文件事件（content_b64 为 base64 编码的原始字节，单文件 ≤ 20MB）：
```json
{{"method": "observe", "params": {{"type": "file", "name": "photo.jpg", "mime": "image/jpeg", "content_b64": "..."}}}}
```
网关会自动落盘到 `/agent_vm/sensor/files/{sensor_name}/` 并把沙盒路径告知 Agent。

日志（只进宿主机控制台，不进 Agent）：
```json
{{"method": "log", "params": {{"msg": "调试信息"}}}}
```

### 入向（stdin ← 网关）

Agent 文本回复（kwargs 可含 target_id 等路由参数）：
```json
{{"method": "express", "params": {{"message": "回复内容", "kwargs": {{}}}}}}
```

Agent 发的文件（Agent 消息里含本地文件链接时网关自动追加）：
```json
{{"method": "express", "params": {{"type": "file", "name": "a.png", "mime": "image/png", "size": 11, "content_b64": "...", "kwargs": {{}}}}}}
```
你需 base64 解码后自行发送到外部渠道。若渠道 API 是"先上传换 key 再发消息"两段式（如飞书），请在后台线程完成，**严禁阻塞 stdin 读取循环**。

## 3. 首次启动鉴权规范 ⭐（最重要）

Sensor 首次启动往往需要凭证（App Secret、API Token 等）。**严禁缺凭证时静默退出或空转**，必须：

1. 启动时检测凭证是否为空；
2. 为空则立即用 **observe 发送文字消息向 Agent 求助**，说清三件事：缺哪些凭证、去哪配置（前端配置中心 → Sensor 设置 → 填写 env 后启用）、凭证到位后自己会做什么；
3. Agent 会转告老板并协助完成配置（配置保存后系统会热重启 sensor，届时读到新 env 自动恢复）；
4. 主进程保持存活待命，不要退出。

示例：
```python
if not os.environ.get("MY_TOKEN"):
    send_json_to_main("observe", {{"content": "[{sensor_name} 求助] 首次启动需要鉴权凭证 MY_TOKEN（当前为空）。请老板在前端配置中心 → Sensor 设置里为 {sensor_name} 填写 MY_TOKEN 后保存启用，我会在热重启后自动连接并保持待命。"}})
```

## 4. 单文件骨架

依赖用 PEP 723 内联声明（uv 会自动建环境）：

```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "在此声明依赖",
# ]
# ///
import sys, json, threading, os

_REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr  # 🌟 铁律：print 全部改走 stderr

def send_json_to_main(method: str, params: dict):
    _REAL_STDOUT.write(json.dumps({{"method": method, "params": params}}, ensure_ascii=False) + "\\n")
    _REAL_STDOUT.flush()

# 后台线程：连接外部服务监听事件 → send_json_to_main("observe", ...)
# 主线程：for line in sys.stdin: 处理 express（文本 + file）
```

## 5. 测试方法

沙盒内可以直接手测（不经过宿主机）：

```bash
cd /agent_vm/sensor_workplace/<uuid>
echo '{{"method":"express","params":{{"message":"hello"}}}}' | uv run {sensor_name}.py
```

观察 stderr 日志与外部渠道是否收到消息；鉴权求助消息会打到 stdout。

## 6. sensor_config.json（合并注册的唯一依据）

沙盒根目录维护 `sensor_config.json`，合并时系统只认它：

```json
{{
  "name": "{sensor_name}",
  "env": {{ "MY_TOKEN": "" }},
  "capabilities": {{ "observe": true, "express": true }},
  "tool_detail": false
}}
```

* `env`：声明全部所需凭证（留空字符串占位，老板配置后注入）
* `capabilities`：声明 observe/express 能力，未声明的能力网关不会下发
* `tool_detail`：true 时 Agent 的工具调用细节（工具名/参数摘要/结果片段）也会推送到本 sensor；false（默认）时只推送 content 正文，不推送工具调用与结果

## 7. 提交合并

测试通过后调用 `Request(request_type="sensor_merge", target="{sensor_name}")`，
并在 reason 中简述功能点供老板 Code Review。批准后系统会：

1. 拷贝 `{sensor_name}.py` 至正式目录并写入 activate_sensor.json（enabled=true）
2. Git 提交版本记录
3. 热重启 Sensor 线程池——**若凭证未填，你会立刻收到该 sensor 的鉴权求助消息**，请转告老板协助配置。
"""
