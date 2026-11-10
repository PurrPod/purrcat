"""从 Agent 消息文本中提取本地文件路径（sensor 出向推送用）。

纯文本解析与落盘/推送分离，便于单测：这里只做候选匹配、规范化与宿主机路径转换。
"""

import os
import re

from src.utils.path import convert_sandbox_path

# markdown 链接/图片的目标地址，如 ![报告](/agent_vm/report.png)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)\s*\)")
# 裸路径引用：/agent_vm/...（含 ./ ../ 前缀）、Windows 盘符绝对路径、file:// 协议
# 盘符前加 (?<![A-Za-z0-9.]) 防止匹配到 "file:" 里的 "e:"
_FILE_PATH_RE = re.compile(
    r"(?:file:///(?:[A-Za-z]:|agent_vm)[^\s\"'<>,|]+"
    r"|(?:/|\.{1,2}/)agent_vm[/\\][^\s\"'<>,|]+"
    r"|(?<![A-Za-z0-9.])[A-Za-z]:[/\\][^\s\"'<>,|]+)"
)


def normalize_candidate(raw: str) -> str | None:
    """把文本中提取到的路径候选规范化为 Agent 视角路径，非法返回 None。"""
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
    """从消息文本中提取本地文件链接，返回宿主机绝对路径列表（去重且仅保留存在的文件）。"""
    candidates = [m.group(1) for m in _MD_LINK_RE.finditer(text)]
    candidates += [m.group(0) for m in _FILE_PATH_RE.finditer(text)]

    paths = []
    seen = set()
    for c in candidates:
        p = normalize_candidate(c)
        if not p:
            continue
        host = convert_sandbox_path(p)
        if host in seen or not os.path.isfile(host):
            continue
        seen.add(host)
        paths.append(host)
    return paths
