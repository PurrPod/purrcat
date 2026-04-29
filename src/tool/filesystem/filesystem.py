"""FileSystem 工具主入口 - 统一调度 import_file、export_file、list_filesystem"""

import traceback
from src.tool.utils.format import text_response, error_response, warning_response
from src.tool.filesystem.exceptions import (
    FileSystemError,
    InvalidActionError,
    MissingParameterError,
    InvalidParameterError
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
        # 参数校验
        action = action.strip().lower() if action else ""
        
        # 检查操作类型
        if action not in ["import", "export", "list"]:
            return error_response(f"无效的操作类型: {action}。支持的操作: import, export, list", "参数错误")
        
        # 参数校验
        if action == "list":
            # list 操作：path_from 可选（默认为当前目录），禁止传 path_to
            if path_to is not None and path_to.strip() != "":
                return error_response("list 操作不支持 path_to 参数", "参数错误")
            
            path = path_from if path_from else "."
            try:
                result = list_filesystem(path=path, **kwargs)
                snip = f"列出目录: {result['path']} ({result['dir_count']} 目录, {result['file_count']} 文件)"
                return text_response(result, snip)
            except FileSystemError as e:
                return error_response(str(e), "列表操作失败")
        
        elif action == "import":
            # import 操作：需要 path_from（宿主机路径），path_to 可选（沙盒目录，默认为 imports）
            if not path_from or not path_from.strip():
                return error_response("import 操作需要提供 path_from（宿主机路径）", "参数错误")
            
            sandbox_dir = path_to.strip() if path_to else "imports"
            try:
                result = import_file(host_path=path_from, sandbox_dir=sandbox_dir)
                snip = f"导入成功: {result['sandbox_path']}"
                return text_response(result, snip)
            except FileSystemError as e:
                return warning_response(str(e), "导入操作失败")
        
        elif action == "export":
            # export 操作：需要 path_from（沙盒路径）和 path_to（宿主机路径）
            if not path_from or not path_from.strip():
                return error_response("export 操作需要提供 path_from（沙盒路径）", "参数错误")
            
            if not path_from.startswith("/agent_vm/"):
                return error_response("路径错误：export 操作的 path_from 必须是沙盒内的绝对路径，且严格以 '/agent_vm/' 开头。", "参数错误")
            
            if not path_to or not path_to.strip():
                return error_response("export 操作需要提供 path_to（宿主机路径）", "参数错误")
            
            try:
                result = export_file(sandbox_path=path_from, host_path=path_to)
                snip = f"导出成功: {result['host_path']}"
                return text_response(result, snip)
            except FileSystemError as e:
                return warning_response(str(e), "导出操作失败")
        
        return error_response("未知错误", "系统错误")
        
    except Exception as e:
        # 【关键】捕获所有异常，格式化为模型可读的错误，而不是让程序崩溃
        traceback.print_exc()
        return error_response(f"文件系统运行时异常: {str(e)}", "执行失败")