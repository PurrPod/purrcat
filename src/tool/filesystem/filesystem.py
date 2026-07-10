"""FileSystem 工具主入口 - 统一调度所有文件操作"""

import traceback

from src.tool.filesystem.copy_file import copy_file
from src.tool.filesystem.delete_file import delete_file
from src.tool.filesystem.exceptions import FileSystemError, HostPathNotFoundError
from src.tool.filesystem.history import rewind_file
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
from src.tool.filesystem.utils import require_write
from src.tool.utils.format import error_response, text_response


def _summarize_diff(diff_text: str) -> str:
    """解析 unified diff 文本，计算新增和删除的代码行数"""
    if not diff_text:
        return "新增 0 行，删除 0 行"

    additions = 0
    deletions = 0
    for line in diff_text.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return f"新增了 {additions} 行代码，删除了 {deletions} 行代码"


def FileSystem(action: str, path: str = None, destination: str = None, **kwargs) -> str:
    """
    FileSystem 工具主入口函数。
    """
    try:
        action = action.strip().lower() if action else ""
        allowed_actions = [
            "list",
            "read_picture",
            "read",
            "edit",
            "write",
            "search",
            "glob",
            "move",
            "copy",
            "delete",
            "undo",
        ]

        if action not in allowed_actions:
            return error_response(
                f"无效的操作: {action}。支持: {allowed_actions}", "❌ 参数错误"
            )

        if action == "read_picture":
            image_paths = kwargs.get("picture_paths") or ([path] if path else [])
            if not image_paths:
                return error_response(
                    "read_picture 至少需要提供 path 或 picture_paths 参数",
                    "❌ 参数缺失",
                )
            try:
                result = read_picture(
                    paths=image_paths,
                    prompt=kwargs.get("prompt", "请详细描述这些图片。"),
                )
                return text_response(result, f"👁️ 成功分析了 {len(image_paths)} 张图片")
            except HostPathNotFoundError as e:
                return error_response(str(e), "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 图片读取失败")

        if not path:
            return error_response(f"{action} 操作必须提供 path 参数", "❌ 参数缺失")

        if action == "read":
            result = read_file(path, kwargs.get("offset", 0), kwargs.get("limit", 2000))
            # 🌟 改造：直接把组装好的带行号的字符串作为 content
            read_text = f"文件路径: {result['path']}\n总行数: {result['total_lines']}\n\n{result['content']}"

            # 🌟 新增：在被 route.py 全局落盘机制拦截前，进行前置字数超限拦截
            if len(read_text) > 5000:
                return error_response(
                    "返回字数超5000字已被拦截，请缩小行数限制参数重新分批读取。",
                    "❌ 文本超限",
                )

            return text_response(read_text, f"📄 读取了 {result['showing_lines']} 行")

        if action == "edit":
            old_str, new_str = kwargs.get("old_string"), kwargs.get("new_string")
            if old_str is None or new_str is None:
                return error_response(
                    "edit 操作需提供 old_string 和 new_string", "❌ 参数缺失"
                )
            result = edit_file(path, old_str, new_str, kwargs.get("replace_all", False))

            diff_text = result.get("diff", "")
            diff_summary = _summarize_diff(diff_text)
            response_text = (
                f"✂️ 修改成功！{diff_summary}。\n"
                f"💡 提示：如果误删了重要代码，你可以随时使用 `action='undo'` 进行回溯。\n\n"
                f"{result.get('message', '')}"
            )
            return text_response(response_text, "✂️ 修改成功")

        if action == "undo":
            if not path:
                return error_response("undo 操作必须提供 path 参数", "❌ 参数缺失")
            try:
                # 终极修复：加入 require_write 进行路径映射和权限校验
                # 把 /agent_vm/... 映射为真实的 D:\cat-in-cup\agent_vm\...
                resolved_path = require_write(path)

                # Agent 调用 undo 时，回滚该文件的最新一次操作
                result_msg = rewind_file(resolved_path)
                return text_response(
                    f"文件 {resolved_path} 回滚情况：\n{result_msg}", f"↩️ {result_msg}"
                )

            except FileSystemError as e:
                error_msg = str(e)
                # 核心：拦截"找不到备份"的报错，加上对 Agent 的专属安抚提示
                if "未找到" in error_msg or "可回滚" in error_msg:
                    return error_response(
                        f"{error_msg}\n"
                        f"💡 系统提示：备份文件已不存在。这可能是因为用户已为你执行了回滚，"
                        f"或者修改已被人类确认并固化。请不要继续尝试 undo，直接使用 read 工具查看该文件的最新状态！",
                        "❌ 回滚取消",
                    )
                return error_response(error_msg, "❌ 回滚失败")

        if action == "write":
            content = kwargs.get("content")
            if content is None:
                return error_response("write 操作需提供 content", "❌ 参数缺失")
            result = write_file(path, content)

            diff_text = result.get("diff", "")
            diff_summary = _summarize_diff(diff_text)
            response_text = (
                f"{result['message']}\n\n"
                f"📊 变更统计：{diff_summary}。\n"
                f"� 提示：如果覆盖导致重要代码丢失，你可以使用 `action='undo'` 恢复到上一版本。"
            )
            return text_response(response_text, "📝 写入成功")

        if action == "search":
            if not kwargs.get("pattern"):
                return error_response("缺少 pattern", "❌ 参数缺失")
            result = search_file(path, kwargs.get("pattern"))
            search_txt = f"🎯 在目录 {result['search_dir']} 中搜索正则 `{result['pattern']}`\n匹配结果 ({result['match_count']}处):\n{result['results']}"
            return text_response(search_txt, f"🔍 找到 {result['match_count']} 处匹配")

        if action == "glob":
            if not kwargs.get("pattern"):
                return error_response("缺少 pattern", "❌ 参数缺失")
            result = glob_file(path, kwargs.get("pattern"))
            glob_txt = (
                f"🎯 在目录 {result['search_dir']} 中匹配模式 `{result['pattern']}`\n找到文件 ({result['total_matches']}个):\n"
                + "\n".join(result["files_sorted_by_mtime"])
            )
            return text_response(glob_txt, f"🌐 找到 {result['total_matches']} 个文件")

        if action == "list":
            try:
                result = list_filesystem(path=path, depth=kwargs.get("depth", 1))
                return text_response(
                    result["tree"],
                    f"📂 📁{result['dir_count']} 📄{result['file_count']}",
                )
            except HostPathNotFoundError:
                return error_response("路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 列表失败")

        if action == "move":
            if not destination:
                return error_response(
                    "move 操作需提供 destination 目标路径", "❌ 参数缺失"
                )
            try:
                result = move_file(path_from=path, path_to=destination)
                return text_response(result["message"], "🚚 移动/导入导出成功")
            except HostPathNotFoundError:
                return error_response("源路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 移动失败")

        if action == "copy":
            if not destination:
                return error_response(
                    "copy 操作需提供 destination 目标路径", "❌ 参数缺失"
                )
            try:
                result = copy_file(path_from=path, path_to=destination)
                return text_response(result["message"], "📋 复制成功")
            except HostPathNotFoundError:
                return error_response("源路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 复制失败")

        if action == "delete":
            try:
                result = delete_file(path=path)
                return text_response(result["message"], "🗑️ 删除成功")
            except HostPathNotFoundError:
                return error_response("要删除的路径不存在", "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 删除失败")

        return error_response("未知错误", "❌ 系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"系统异常: {str(e)}", "❌ 异常")
