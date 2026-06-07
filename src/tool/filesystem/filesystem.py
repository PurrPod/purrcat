"""FileSystem 工具主入口 - 统一调度 import_file、export_file、list_filesystem、read_picture"""

import traceback

from src.tool.filesystem.exceptions import (
    ExportDirNotAllowedError,
    FileSystemError,
    GitNotAvailableError,
    HostPathNotFoundError,
    SandboxPathNotFoundError,
)
from src.tool.filesystem.export_file import export_file
from src.tool.filesystem.import_file import import_file
from src.tool.filesystem.list_filesystem import list_filesystem
from src.tool.filesystem.move_file import move_file
from src.tool.filesystem.read_picture import read_picture
from src.tool.filesystem.text_ops import (
    read_file,
    edit_file,
    write_file,
    search_file,
    glob_file,
)
from src.tool.utils.format import error_response, text_response, warning_response


def FileSystem(
    action: str, path_from: str = None, path_to: str = None, **kwargs
) -> str:
    """
    FileSystem 工具主入口函数，支持十种操作：import、export、list、read_picture、read、edit、write、search、glob、move

    Args:
        action: 操作类型，必须为 "import"、"export"、"list"、"read_picture"、"read"、"edit"、"write"、"search"、"glob" 或 "move"
        path_from: 源路径
            - import: 宿主机文件/目录路径
            - export: 沙盒内文件/目录路径（必须以 /agent_vm/ 开头）
            - list: 要列出的目录路径（可选，默认为当前目录）
            - read_picture: 单张图片路径（也可使用 paths 参数代替）
            - read/edit/write/search/glob: 文件或目录路径
            - move: 要移动/重命名的源文件路径
        path_to: 目标路径（list 和 read_picture 操作时不需要）
            - import: 沙盒内目标目录（可选，默认为 "imports"）
            - export: 宿主机目标路径
            - move: 移动/重命名的目标路径

    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        action = action.strip().lower() if action else ""
        allowed_actions = [
            "import",
            "export",
            "list",
            "read_picture",
            "read",
            "edit",
            "write",
            "search",
            "glob",
            "move",
        ]
        if action not in allowed_actions:
            return error_response(
                f"无效的操作类型: {action}。支持的操作: {allowed_actions}",
                "参数错误",
            )

        path = path_from if path_from else kwargs.get("path")

        # --- 文本读取 (Read) ---
        if action == "read":
            if not path:
                return error_response("read 操作需提供 path_from", "❌ 参数缺失")
            offset = kwargs.get("offset", 0)
            limit = kwargs.get("limit", 2000)
            result = read_file(path, offset, limit)
            return text_response(result, f"📄 读取了 {result['showing_lines']} 行")

        # --- 文本编辑 (Edit) ---
        if action == "edit":
            if not path:
                return error_response("edit 操作需提供 path_from", "❌ 参数缺失")
            old_str = kwargs.get("old_string")
            new_str = kwargs.get("new_string")
            replace_all = kwargs.get("replace_all", False)
            if old_str is None or new_str is None:
                return error_response(
                    "edit 操作需提供 old_string 和 new_string", "❌ 参数缺失"
                )
            result = edit_file(path, old_str, new_str, replace_all)
            return text_response(result, "✂️ 修改成功")

        # --- 文本覆盖写入 (Write) ---
        if action == "write":
            if not path:
                return error_response("write 操作需提供 path_from", "❌ 参数缺失")
            content = kwargs.get("content")
            if content is None:
                return error_response("write 操作需提供 content", "❌ 参数缺失")
            result = write_file(path, content)
            return text_response(result, "📝 写入成功")

        # --- 全局内容搜索 (Search/Grep) ---
        if action == "search":
            if not path or str(path).strip() == "":
                return error_response(
                    "search 操作必须提供 path 参数，指定搜索的起始目录！", "❌ 参数缺失"
                )
            pattern = kwargs.get("pattern")
            if not pattern:
                return error_response(
                    "search 操作需提供 pattern 正则表达式", "❌ 参数缺失"
                )
            result = search_file(path, pattern)
            return text_response(result, f"🔍 找到 {result['match_count']} 处匹配")

        # --- 全局路径匹配 (Glob) ---
        if action == "glob":
            if not path or str(path).strip() == "":
                return error_response(
                    "glob 操作必须提供 path 参数，指定扫描的起始目录！", "❌ 参数缺失"
                )
            pattern = kwargs.get("pattern")
            if not pattern:
                return error_response(
                    "glob 操作需提供 pattern (例如 **/*.py)", "❌ 参数缺失"
                )
            result = glob_file(path, pattern)
            return text_response(result, f"🌐 找到 {result['total_matches']} 个文件")

        # --- Read Picture 操作处理 ---
        if action == "read_picture":
            # Agent 可能将路径传给 path_from，也可能传给专门的 paths
            paths = kwargs.get("paths") or path_from
            prompt = kwargs.get("prompt", "请详细描述这张/这些图片。")

            if not paths:
                return error_response(
                    "缺少图片路径参数 (paths 或 path_from)", "❌ 参数缺失"
                )

            try:
                result = read_picture(paths=paths, prompt=prompt)
                snip = f"👁️ 成功分析 {result['image_count']} 张图片"
                return text_response(result, snip)
            except HostPathNotFoundError as e:
                return error_response(str(e), "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 图片读取失败")

        # --- List 操作处理 ---
        if action == "list":
            if path_to is not None and str(path_to).strip() != "":
                return error_response("list 操作不支持 path_to 参数", "❌ 参数错误")

            if not path or str(path).strip() == "":
                return error_response(
                    "list 操作必须提供明确的 path 参数！请指明你要查看的目录。",
                    "❌ 参数缺失",
                )

            list_path = path

            # 统一路径斜杠，方便做前缀判断
            normalized_path = list_path.replace("\\", "/")

            # 【修复点2】：如果是 /agent_vm/skills 开头，直接抛出定制提示拦截
            if (
                normalized_path.startswith("/agent_vm/skills/")
                or normalized_path == "/agent_vm/skills"
            ):
                return error_response(
                    "虚拟机内的 skills 文件夹无法直接通过 filesystem 工具检测，请直接使用 bash 工具访问。",
                    "❌ 访问受限",
                )

            # 【修复点3】：将剩余以 /agent_vm 开头的路径映射为 ./agent_vm 相对路径
            if normalized_path.startswith("/agent_vm"):
                list_path = "." + list_path

            kwargs.pop("path", None)
            kwargs.pop("path_from", None)
            try:
                # 把处理过的 list_path 传进去
                result = list_filesystem(path=list_path, **kwargs)
                snip = f"📂 📁{result['dir_count']} 📄{result['file_count']}"
                return text_response(result, snip)
            except HostPathNotFoundError:
                return error_response("路径不存在，请检查后重试", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 列表失败")

        # --- 文件移动/重命名 (Move) ---
        if action == "move":
            if not path_from or not path_to:
                return error_response(
                    "move 操作需同时提供 path_from 和 path_to", "❌ 参数缺失"
                )
            try:
                result = move_file(path_from, path_to)
                return text_response(result, "🚚 移动/重命名成功")
            except HostPathNotFoundError:
                return error_response("源路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 移动失败")

        # --- Import / Export 操作参数强制拦截 ---
        if (
            not path_from
            or not str(path_from).strip()
            or not path_to
            or not str(path_to).strip()
        ):
            return error_response(
                "文件导入导出应当包含path_from和path_to", "❌ 参数缺失"
            )

        # --- Import 操作处理 ---
        if action == "import":
            try:
                result = import_file(host_path=path_from, sandbox_dir=path_to.strip())
                return text_response(result, "⬇️ 导入成功")
            except HostPathNotFoundError:
                return error_response("宿主机路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return warning_response(str(e), "⚠️ 导入失败")

        # --- Export 操作处理 ---
        elif action == "export":
            if not str(path_from).startswith("/agent_vm/"):
                return error_response("路径必须以 '/agent_vm/' 开头", "❌ 路径格式错误")

            try:
                result = export_file(sandbox_path=path_from, host_path=path_to)
                return text_response(result, "⬆️ 导出成功")
            except SandboxPathNotFoundError:
                return error_response("沙盒文件不存在", "❌ 文件不存在")
            except ExportDirNotAllowedError as e:
                msg = (
                    f"目标路径导出受限。仅可导出到目录白名单内的路径: {e.allowed_dirs}"
                )
                return error_response(msg, "❌ 目录受限")
            except GitNotAvailableError:
                return error_response("宿主机未安装git，禁止导出", "❌ Git未安装")
            except FileSystemError as e:
                return warning_response(str(e), "⚠️ 导出失败")

        return error_response("未知错误", "❌ 系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"文件系统异常: {str(e)}", "❌ FS异常")
