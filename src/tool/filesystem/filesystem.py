"""FileSystem 工具主入口 - 统一调度 import_file、export_file、list_filesystem"""

import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.filesystem.exceptions import (
    FileSystemError,
    HostPathNotFoundError,
    SandboxPathNotFoundError,
    ExportDirNotAllowedError,
    GitNotAvailableError
)
from src.tool.filesystem.import_file import import_file
from src.tool.filesystem.export_file import export_file
from src.tool.filesystem.list_filesystem import list_filesystem


def FileSystem(action: str, path_from: str = None, path_to: str = None, **kwargs) -> str:
    """
    FileSystem 工具主入口函数，支持三种操作：import、export、list

    Args:
        action: 操作类型，必须为 "import"、"export" 或 "list"
        path_from: 源路径
            - import: 宿主机文件/目录路径
            - export: 沙盒内文件/目录路径（必须以 /agent_vm/ 开头）
            - list: 要列出的目录路径（可选，默认为当前目录）
        path_to: 目标路径（list 操作时不需要）
            - import: 沙盒内目标目录（可选，默认为 "imports"）
            - export: 宿主机目标路径

    Returns:
        格式化后的 JSON 字符串，包含 timestamp, type, content, snip
    """
    try:
        action = action.strip().lower() if action else ""
        if action not in ["import", "export", "list"]:
            return error_response(f"无效的操作类型: {action}。支持的操作: import, export, list", "参数错误")

        # --- List 操作处理 ---
        if action == "list":
            if path_to is not None and str(path_to).strip() != "":
                return error_response("list 操作不支持 path_to 参数", "❌ 参数错误")
            path = path_from if path_from else "."
            try:
                result = list_filesystem(path=path, **kwargs)
                snip = f"📂 📁{result['dir_count']} 📄{result['file_count']}"
                return text_response(result, snip)
            except HostPathNotFoundError:
                return error_response('路径不存在，请检查后重试', "❌ 路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "❌ 列表失败")

        # --- Import / Export 操作参数强制拦截 ---
        if not path_from or not str(path_from).strip() or not path_to or not str(path_to).strip():
            return error_response("文件导入导出应当包含path_from和path_to", "❌ 参数缺失")

        # --- Import 操作处理 ---
        if action == "import":
            try:
                result = import_file(host_path=path_from, sandbox_dir=path_to.strip())
                return text_response(result, "⬇️ 导入成功")
            except HostPathNotFoundError:
                return error_response('宿主机路径不存在', "❌ 路径不存在")
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
                msg = f"可导入目录: {e.allowed_dirs}"
                return error_response(msg, "❌ 目录受限")
            except GitNotAvailableError:
                return error_response("宿主机未安装git", "❌ Git未安装")
            except FileSystemError as e:
                return warning_response(str(e), "⚠️ 导出失败")

        return error_response("未知错误", "❌ 系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"文件系统异常: {str(e)}", "❌ FS异常")