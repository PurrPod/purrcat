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
                return error_response("list 操作不支持 path_to 参数", "参数错误")
            path = path_from if path_from else "."
            try:
                result = list_filesystem(path=path, **kwargs)
                snip = f"列出目录: {result['path']} ({result['dir_count']} 目录, {result['file_count']} 文件)"
                return text_response(result, snip)
            except HostPathNotFoundError:
                return error_response('对应文件路径不存在，请确保正确输入了真实的宿主机文件路径，可通过指定action=list来梳理本地文件系统结构\n如：FileSystem(action="list", path_from=".")', "路径不存在")
            except FileSystemError as e:
                return error_response(str(e), "列表操作失败")

        # --- Import / Export 操作参数强制拦截 ---
        if not path_from or not str(path_from).strip() or not path_to or not str(path_to).strip():
            return error_response("文件导入导出应当包含path_from和path_to", "参数缺失")

        # --- Import 操作处理 ---
        if action == "import":
            try:
                result = import_file(host_path=path_from, sandbox_dir=path_to.strip())
                snip = f"导入成功: {result['sandbox_path']}"
                return text_response(result, snip)
            except HostPathNotFoundError:
                return error_response('对应文件路径不存在，请确保正确输入了真实的宿主机文件路径，可通过指定action=list来梳理本地文件系统结构\n如：FileSystem(action="list", path_from=".")', "路径不存在")
            except FileSystemError as e:
                return warning_response(str(e), "导入操作失败")

        # --- Export 操作处理 ---
        elif action == "export":
            if not str(path_from).startswith("/agent_vm/"):
                return error_response("路径错误：export 操作的 path_from 必须是沙盒内的绝对路径，且严格以 '/agent_vm/' 开头。", "参数错误")

            try:
                result = export_file(sandbox_path=path_from, host_path=path_to)
                snip = f"导出成功: {result['host_path']}"
                return text_response(result, snip)
            except SandboxPathNotFoundError:
                return error_response("检测到输入的沙盒文件路径不存在，请确保文件存在或输入参数正确", "沙盒文件不存在")
            except ExportDirNotAllowedError as e:
                msg = f"可导入目录在：{e.allowed_dirs}\n当前目标目录不在此范围内，可选择导入到允许的目录内\n如有特殊需要，请联系老板开启权限"
                return error_response(msg, "目标目录受限")
            except GitNotAvailableError:
                return error_response("检测到宿主机没有安装git，为保证安全，终止导出，请联系老板在宿主机安装git或直接前往沙盒查看文件", "Git未安装")
            except FileSystemError as e:
                return warning_response(str(e), "导出操作失败")

        return error_response("未知错误", "系统错误")

    except Exception as e:
        traceback.print_exc()
        return error_response(f"文件系统运行时异常: {str(e)}", "执行失败")