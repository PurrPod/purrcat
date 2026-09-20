"""
端口信封协议 (Port Envelope)
节点间每条连线传递一个自描述 JSON 信封：
    { "type": "string|jsonstring|number|boolean|list|file|MessageList|any",
      "data": <内联值 或 purrcat:// URI>,
      "mime": "text/html",
      "meta": {} }

- string/number/boolean 内联；file 只存 URI（实体在节点 files/ 或 graph asset/）
- jsonstring：内容为 JSON 文本的 string 子类型（纯声明语义，与 string 双向兼容）
- list 是透明容器：data 存原始数组，元素可为裸值或信封（消费方按需 is_envelope 判断）
- MessageList 的 data 直接是消息数组（AgentNode 特例）
"""

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

ENVELOPE_TYPES = {
    "string",
    "jsonstring",
    "number",
    "boolean",
    "list",
    "file",
    "MessageList",
    "any",
}

# 单端口声明的允许类型（union），如 ["string", "file"]
AllowedTypes = List[str]

PURRCAT_SCHEME = "purrcat://"


def make(type_: str, data: Any, mime: str = None, meta: dict = None) -> dict:
    """构造一个信封"""
    if type_ not in ENVELOPE_TYPES:
        type_ = "any"
    env = {"type": type_, "data": data}
    if mime:
        env["mime"] = mime
    if meta:
        env["meta"] = meta
    return env


def is_envelope(v: Any) -> bool:
    """判断值是否为合法信封（dict 且含合法 type + data 键）"""
    if not isinstance(v, dict):
        return False
    if "type" not in v or "data" not in v:
        return False
    return v["type"] in ENVELOPE_TYPES


def infer_type(raw: Any) -> str:
    """从裸值推断信封类型"""
    if isinstance(raw, bool):
        return "boolean"
    if isinstance(raw, (int, float)):
        return "number"
    if isinstance(raw, str):
        return "string"
    if isinstance(raw, list):
        return "list"
    return "any"


def coerce(raw: Any, port_type: Any = None) -> dict:
    """裸值→信封（惰性兼容旧 checkpoint 裸数据）。
    port_type 可为单类型字符串或 union 列表；优先采用端口声明，推断失败落 any。
    已是信封则原样返回。"""
    if is_envelope(raw):
        return raw
    preferred = None
    if isinstance(port_type, str):
        preferred = port_type
    elif isinstance(port_type, list) and len(port_type) == 1:
        preferred = port_type[0]
    if preferred in (None, "any"):
        preferred = infer_type(raw)
    return make(preferred, raw)


def normalize_allowed(allowed: Any) -> AllowedTypes:
    """端口声明的类型归一化为列表；缺省视为 any 万能"""
    if allowed is None:
        return ["any"]
    if isinstance(allowed, str):
        return [allowed]
    if isinstance(allowed, list) and allowed:
        return [str(t) for t in allowed]
    return ["any"]


def check(env: dict, allowed: Any) -> Tuple[bool, str]:
    """校验信封类型是否在端口允许列表内。
    any 万能；MessageList↔list 双向兼容；jsonstring↔string 双向兼容（子类型）。"""
    allowed_list = normalize_allowed(allowed)
    if "any" in allowed_list:
        return True, ""
    env_type = env.get("type", "any") if isinstance(env, dict) else infer_type(env)
    if env_type == "any":
        return True, ""
    if env_type == "MessageList" and "list" in allowed_list:
        return True, ""
    # list 信封亦可进 MessageList 端口（消息数组是 list 的特例，双向兼容）
    if env_type == "list" and "MessageList" in allowed_list:
        return True, ""
    # jsonstring 是 string 的子类型，双向兼容（消费方自行 parse JSON）
    if env_type == "jsonstring" and "string" in allowed_list:
        return True, ""
    if env_type == "string" and "jsonstring" in allowed_list:
        return True, ""
    if env_type in allowed_list:
        return True, ""
    return (
        False,
        f"类型不兼容：端口只接受 {allowed_list}，实际收到 [{env_type}]",
    )


def to_task_uri(checkpoint_dir: str, node_id: str, filename: str) -> str:
    """构造指向 task 节点 files/ 目录的 URI"""
    return f"purrcat://task/node/{node_id}/files/{filename}"


def _safe_join(base: Path, relative: str) -> Optional[Path]:
    """拼接并校验路径穿越，逃逸 base 则返回 None"""
    target = (base / relative).resolve()
    base_resolved = base.resolve()
    if target == base_resolved or base_resolved in target.parents:
        return target
    return None


def parse_uri(
    uri: str,
    *,
    graph_name: str = None,
    checkpoint_dir: str = None,
) -> Optional[Path]:
    """解析 purrcat:// URI 或绝对路径为物理路径。

    - purrcat://graph/{name}/asset/x → GRAPHS_DIR/{name}/asset/x
    - purrcat://task/node/{nid}/files/x → checkpoint_dir/nodes/{nid}/files/x
    - purrcat://task/{tid}/node/{nid}/files/x → 同上（tid 仅作标识，靠 checkpoint_dir 定位）
    - 其它非 purrcat:// 的按绝对路径兜底（仅本地信任域）
    """
    if not isinstance(uri, str) or not uri:
        return None

    if not uri.startswith(PURRCAT_SCHEME):
        # 绝对路径兜底
        p = Path(os.path.expanduser(uri))
        return p if p.is_absolute() else None

    from src.utils.config import GRAPHS_DIR

    body = uri[len(PURRCAT_SCHEME):]
    parts = body.split("/")

    if len(parts) >= 3 and parts[0] == "graph":
        # purrcat://graph/{name}/asset/...
        name = parts[1]
        rest = "/".join(parts[2:])
        return _safe_join(Path(GRAPHS_DIR) / name, rest)

    if len(parts) >= 4 and parts[0] == "task":
        # purrcat://task[/node]/{nid}/files/... 或 purrcat://task/{tid}/node/{nid}/files/...
        if parts[1] == "node":
            # purrcat://task/node/{nid}/files/... → parts[3:] 保留 files/ 层
            node_id, rest = parts[2], "/".join(parts[3:])
        else:
            node_id, rest = parts[3], "/".join(parts[4:])
        if not checkpoint_dir:
            return None
        return _safe_join(Path(checkpoint_dir) / "nodes" / node_id, rest)

    return None
