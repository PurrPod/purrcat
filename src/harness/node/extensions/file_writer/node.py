import os
import asyncio
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """通用的本地文件写入器：支持任意本地物理路径，自动创建父目录"""

    def _sync_write(self, target_path: str, content: str):
        """将同步写操作剥离出来的普通函数，供线程池调用"""
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "💾 [文件落盘] 节点启动")

        content = inputs.get("content", "")
        if not content:
            self.log(
                context, "WARNING", "⚠️ [文件落盘] 收到的内容为空，仍将创建空文件。"
            )

        raw_file_path = inputs.get("file_path") or self.config.get("file_path", "")

        if not raw_file_path:
            self.log(context, "ERROR", "❌ [文件落盘] 缺失 file_path 参数")
            raise ValueError("必须提供文件的保存路径 (file_path)！")

        target_path = os.path.abspath(os.path.expanduser(raw_file_path))

        self.log(
            context, "SYSTEM", f"📂 [文件落盘] 规范化后的物理保存路径: {target_path}"
        )

        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            try:
                # 🌟 创建目录也放入线程池，避免阻塞
                await asyncio.to_thread(os.makedirs, parent_dir, exist_ok=True)
            except PermissionError:
                self.log(
                    context,
                    "ERROR",
                    f"❌ [文件落盘] 权限不足，无法创建目录: {parent_dir}",
                )
                raise PermissionError(
                    f"权限不足：无法在目标位置创建文件夹: {parent_dir}"
                )

        try:
            # 🌟 关键修改：将写文件操作放入线程池执行，坚决不阻塞事件循环
            await asyncio.to_thread(self._sync_write, target_path, str(content))
            self.log(
                context,
                "SYSTEM",
                f"✅ [文件落盘] 成功写入 {len(str(content))} 字符至: {target_path}",
            )
        except PermissionError:
            self.log(
                context, "ERROR", f"❌ [文件落盘] 权限不足，无法写入文件: {target_path}"
            )
            raise PermissionError(
                f"权限不足：当前系统账户没有写入该文件的权限: {target_path}"
            )
        except Exception as e:
            self.log(context, "ERROR", f"❌ [文件落盘] 发生未知错误: {e}")
            raise RuntimeError(f"写入文件时发生系统级错误: {str(e)}")

        return {"absolute_path": target_path}
