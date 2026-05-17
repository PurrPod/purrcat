import os
from typing import Any, Dict

from src.harness.node.base import BaseNode


class Node(BaseNode):
    """通用的本地纯文本文件读取器：支持任意本地路径，保留二进制文件拦截"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        raw_file_path = inputs.get("file_path") or self.config.get("file_path", "")

        if not raw_file_path:
            self.log(context, "ERROR", "❌ [本地读取] 缺失 file_path 参数")
            raise ValueError("必须提供文件路径 (file_path)！")

        self.log(context, "SYSTEM", f"📥 [本地读取] 收到路径请求: {raw_file_path}")

        # ==========================================
        # 📂 路径解析：支持绝对路径、相对路径和 ~ (Home) 目录
        # ==========================================
        # expanduser 处理 '~'，abspath 处理 './' 或 '../' 并转为绝对物理路径
        target_path = os.path.abspath(os.path.expanduser(raw_file_path))

        self.log(context, "SYSTEM", f"📂 [路径解析] 规范化后的物理路径: {target_path}")

        # ==========================================
        # 📂 业务模块：文件存在性与类型校验
        # ==========================================
        if not os.path.exists(target_path):
            self.log(context, "ERROR", f"❌ [本地读取] 找不到本地文件: {target_path}")
            raise FileNotFoundError(f"找不到指定的本地文件: {target_path}")

        if not os.path.isfile(target_path):
            self.log(context, "ERROR", f"❌ [本地读取] 目标是一个目录: {target_path}")
            raise IsADirectoryError(
                f"目标不能是文件夹，必须是具体的文件: {target_path}"
            )

        self.log(context, "SYSTEM", f"📖 [本地读取] 正在读取物理文件: {target_path}")

        content = ""
        try:
            # 🛡️ 安全模块：二进制炸弹拦截
            # 即使放开了沙盒限制，依然强制使用 utf-8 解码。
            # 这能有效防止大模型被强行喂入 PDF、PNG 等二进制乱码导致 Token 爆炸。
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()

        except UnicodeDecodeError:
            self.log(
                context, "ERROR", "❌ [本地读取] 尝试读取二进制文件 (如 PDF/图片) 失败"
            )
            raise ValueError(
                f"读取失败：{target_path} 似乎是二进制文件（如 PDF、图片、压缩包），当前节点仅支持读取纯文本文件！"
            )
        except PermissionError:
            self.log(
                context, "ERROR", f"❌ [本地读取] 权限不足，无法读取: {target_path}"
            )
            raise PermissionError(
                f"权限不足：当前系统账户没有读取该文件的权限: {target_path}"
            )
        except Exception as e:
            self.log(context, "ERROR", f"❌ [本地读取] 发生未知错误: {e}")
            raise RuntimeError(f"读取文件时发生系统级错误: {str(e)}")

        self.log(
            context, "SYSTEM", f"✅ [本地读取] 成功读取，内容长度: {len(content)} 字符"
        )

        return {"file_content": content}
