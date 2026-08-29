import base64
import json
import mimetypes
import os
import re
from typing import Any

from src.utils.path import convert_sandbox_path

# stdio 单行传输的文件体积上限（原始字节）。base64 膨胀约 33%，
# 飞书侧图片/文件上传限制为 10MB/30MB，这里取 20MB 兜底
MAX_SENSOR_FILE_BYTES = 20 * 1024 * 1024

# markdown 链接/图片的目标地址，如 ![报告](/agent_vm/report.png)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)\s*\)")
# 裸路径引用：/agent_vm/...（含 ./ ../ 前缀）、Windows 盘符绝对路径、file:// 协议
# 盘符前加 (?<![A-Za-z0-9.]) 防止匹配到 "file:" 里的 "e:"
_FILE_PATH_RE = re.compile(
    r"(?:file:///(?:[A-Za-z]:|agent_vm)[^\s\"'<>,|]+"
    r"|(?:/|\.{1,2}/)agent_vm[/\\][^\s\"'<>,|]+"
    r"|(?<![A-Za-z0-9.])[A-Za-z]:[/\\][^\s\"'<>,|]+)"
)


def _normalize_candidate(raw: str) -> str | None:
    """把文本中提取到的路径候选规范化为宿主机绝对路径，非法返回 None"""
    p = raw.strip()
    if p.startswith("file:///"):
        p = p[len("file:///") :]
    elif p.startswith("file://"):
        return None
    # 去掉行尾粘连的标点（中英文）
    p = p.rstrip("。，；！？、.)]}'\"")
    # ./agent_vm/... ../agent_vm/... agent_vm/... 统一成 /agent_vm/...
    m = re.match(r"^(?:\.{1,2}/)*(agent_vm(?:/|$).*)$", p)
    if m:
        p = "/" + m.group(1)
    if not (p.startswith("/agent_vm/") or re.match(r"^[A-Za-z]:[/\\]", p)):
        return None
    return p


def extract_file_paths(text: str) -> list[str]:
    """从消息文本中提取前端可识别的本地文件链接，返回宿主机绝对路径列表"""
    candidates = [m.group(1) for m in _MD_LINK_RE.finditer(text)]
    candidates += [m.group(0) for m in _FILE_PATH_RE.finditer(text)]

    paths = []
    seen = set()
    for c in candidates:
        p = _normalize_candidate(c)
        if not p:
            continue
        host = convert_sandbox_path(p)
        if host in seen or not os.path.isfile(host):
            continue
        seen.add(host)
        paths.append(host)
    return paths


class RemoteSensorProxy:
    def __init__(
        self, name: str, capabilities: dict, stdin_pipe, tool_detail: bool = False
    ):
        self.name = name
        self.can_observe = capabilities.get("observe", False)
        self.can_express = capabilities.get("express", False)
        # true 时接收 Agent 的工具调用细节；false 时只接收 content 正文
        self.tool_detail = bool(tool_detail)
        self.stdin_pipe = stdin_pipe

    def express(self, message: Any, **kwargs) -> bool:
        if not self.can_express:
            return False

        payload = {
            "method": "express",
            "params": {"message": str(message), "kwargs": kwargs},
        }
        try:
            self.stdin_pipe.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.stdin_pipe.flush()
            return True
        except Exception as e:
            print(f"❌ [Gateway] 向 {self.name} 发送数据失败: {e}")
            return False

    def express_file(self, host_path: str, **kwargs) -> bool:
        """按 file 协议把文件（base64）推送给 sensor，由 sensor 自行发送"""
        if not self.can_express:
            return False
        try:
            size = os.path.getsize(host_path)
        except OSError:
            return False

        if size > MAX_SENSOR_FILE_BYTES:
            return self.express(
                f"📎 检测到文件 {os.path.basename(host_path)}"
                f" ({size / 1024 / 1024:.1f}MB) 超过传输上限，未发送，请从工作区获取",
                **kwargs,
            )

        try:
            with open(host_path, "rb") as f:
                content_b64 = base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            print(f"❌ [Gateway] 读取文件失败 {host_path}: {e}")
            return False

        mime, _ = mimetypes.guess_type(host_path)
        payload = {
            "method": "express",
            "params": {
                "type": "file",
                "name": os.path.basename(host_path),
                "mime": mime or "application/octet-stream",
                "size": size,
                "content_b64": content_b64,
                "kwargs": kwargs,
            },
        }
        try:
            self.stdin_pipe.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.stdin_pipe.flush()
            return True
        except Exception as e:
            print(f"❌ [Gateway] 向 {self.name} 发送文件失败: {e}")
            return False


class SensorGateway:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.sensors: dict[str, RemoteSensorProxy] = {}
        self.active_channels = set()

    def register(self, proxy: RemoteSensorProxy) -> None:
        self.sensors[proxy.name] = proxy

    def push(self, sensor_name: str, content: str) -> None:
        if isinstance(content, str) and content.strip() == "/unbind":
            if sensor_name in self.active_channels:
                self.active_channels.remove(sensor_name)
                self.sensors[sensor_name].express(
                    "✅ 已解除活跃状态，可通过再次发送消息保持活跃"
                )
            return

        proxy = self.sensors.get(sensor_name)
        if not proxy:
            return

        if proxy.can_express and sensor_name not in self.active_channels:
            self.active_channels.add(sensor_name)
            proxy.express("✅ 已标记当前会话为活跃窗口\n输入`/unbind`解除绑定")

        print(f"\n📥 [Sensor Input | {sensor_name}] -> {content}")

        try:
            from src.agent import agent_force_push

            agent_force_push(content=content, type=sensor_name)
        except Exception as e:
            print(f"❌ [Gateway] 无法推送消息给 Agent: {e}")

    def send(self, message: Any, tool_detail: bool = False, **kwargs) -> bool:
        text = message if isinstance(message, str) else str(message)
        # 提取消息中前端可识别的本地文件链接，作为 file 类消息追加发送
        file_paths = extract_file_paths(text)

        success_count = 0
        for channel_name in list(self.active_channels):
            proxy = self.sensors.get(channel_name)
            if not proxy:
                continue
            # 工具细节类消息按各 sensor 的 tool_detail 配置过滤；
            # 关闭时只发 content，不发工具调用与结果
            if tool_detail and not proxy.tool_detail:
                continue
            if proxy.express(text, **kwargs):
                success_count += 1
            for host_path in file_paths:
                if proxy.express_file(host_path, **kwargs):
                    success_count += 1
        return success_count > 0


_gateway = SensorGateway()


def get_gateway() -> SensorGateway:
    return _gateway
