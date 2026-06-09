"""FileSystem 工具主入口 - 统一调度所有文件操作"""

import traceback

from src.tool.filesystem.exceptions import FileSystemError, HostPathNotFoundError
from src.tool.filesystem.list_filesystem import list_filesystem
from src.tool.filesystem.move_file import move_file
from src.tool.filesystem.read_picture import read_picture
from src.tool.filesystem.text_ops import (
    read_file, edit_file, write_file, search_file, glob_file,
)
from src.tool.utils.format import error_response, text_response

def FileSystem(action: str, path: str = None, destination: str = None, **kwargs) -> str:
    """
    FileSystem 工具主入口函数。
    """
    try:
        action = action.strip().lower() if action else ""
        allowed_actions = ["list", "read_picture", "read", "edit", "write", "search", "glob", "move"]
        
        if action not in allowed_actions:
            return error_response(f"无效的操作: {action}。支持: {allowed_actions}", "❌ 参数错误")

        if action == "read_picture":
            image_paths = kwargs.get("picture_paths") or ([path] if path else [])
            if not image_paths:
                return error_response("read_picture 至少需要提供 path 或 picture_paths 参数", "❌ 参数缺失")
            try:
                result = read_picture(paths=image_paths, prompt=kwargs.get("prompt", "请详细描述这些图片。"))
                return text_response(result, f"👁️ 成功分析了 {len(image_paths)} 张图片")
            except HostPathNotFoundError as e:
                return error_response(str(e), "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 图片读取失败")

        if not path:
            return error_response(f"{action} 操作必须提供 path 参数", "❌ 参数缺失")

        if action == "read":
            result = read_file(path, kwargs.get("offset", 0), kwargs.get("limit", 2000))
            return text_response(result, f"📄 读取了 {result['showing_lines']} 行")

        if action == "edit":
            old_str, new_str = kwargs.get("old_string"), kwargs.get("new_string")
            if old_str is None or new_str is None:
                return error_response("edit 操作需提供 old_string 和 new_string", "❌ 参数缺失")
            result = edit_file(path, old_str, new_str, kwargs.get("replace_all", False))
            return text_response(result, "✂️ 修改成功")

        if action == "write":
            content = kwargs.get("content")
            if content is None:
                return error_response("write 操作需提供 content", "❌ 参数缺失")
            result = write_file(path, content)
            return text_response(result, "📝 写入成功")

        if action == "search":
            if not kwargs.get("pattern"): return error_response("缺少 pattern", "❌ 参数缺失")
            result = search_file(path, kwargs.get("pattern"))
            return text_response(result, f"🔍 找到 {result['match_count']} 处匹配")

        if action == "glob":
            if not kwargs.get("pattern"): return error_response("缺少 pattern", "❌ 参数缺失")
            result = glob_file(path, kwargs.get("pattern"))
            return text_response(result, f"🌐 找到 {result['total_matches']} 个文件")

        if action == "list":
            try:
                result = list_filesystem(path=path, depth=kwargs.get("depth", 1))
                return text_response(result, f"📂 📁{result['dir_count']} 📄{result['file_count']}")
            except HostPathNotFoundError:
                return error_response("路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 列表失败")

        if action == "move":
            if not destination:
                return error_response("move 操作需提供 destination 目标路径", "❌ 参数缺失")
            try:
                result = move_file(path_from=path, path_to=destination)
                return text_response(result, "🚚 移动/导入导出成功")
            except HostPathNotFoundError:
                return error_response("源路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 移动失败")

        return error_response("未知错误", "❌ 系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"系统异常: {str(e)}", "❌ 异常")