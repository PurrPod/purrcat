"""
基础工具调度器：统一管理工作流工具和业务工具的调度入口（插件化版本）

核心工具（task_done、yield_to_human）是引擎级核心，始终强制注入，无需用户配置。
基础任务工具（bash、filesystem、search、mcp）是保底工具，通过 route.py 调度。
业务工具由用户自由扩展，通过插件化方式注册。
"""
import json
import os
import importlib
from typing import Dict, Any, List


class BaseToolDispatcher:
    """基础工具调度器（插件化版本）"""
    
    _CORE_TOOLS_REGISTRY = {}
    _CORE_TOOLS_SCHEMAS = []
    
    _BUSINESS_TOOLS_REGISTRY = {}
    _BUSINESS_TOOLS_SCHEMAS = []

    @classmethod
    def initialize(cls):
        """扫描 tools 文件夹，动态注册所有工具"""
        if cls._CORE_TOOLS_REGISTRY or cls._BUSINESS_TOOLS_REGISTRY:
            return  # 避免重复加载
        
        base_dir = os.path.dirname(__file__)
        
        # 1. 注册核心工具（core/ 文件夹）
        core_dir = os.path.join(base_dir, "core")
        if os.path.isdir(core_dir):
            cls._load_tools_from_dir(core_dir, cls._CORE_TOOLS_REGISTRY, cls._CORE_TOOLS_SCHEMAS, True)
        
        # 2. 注册业务工具（根目录下的文件夹）
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path) and not item.startswith('_') and item != "core":
                cls._load_tools_from_dir(item_path, cls._BUSINESS_TOOLS_REGISTRY, cls._BUSINESS_TOOLS_SCHEMAS, False)

    @classmethod
    def _load_tools_from_dir(cls, dir_path: str, registry: dict, schemas: list, is_core: bool):
        """从指定目录加载工具"""
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            if os.path.isdir(item_path) and not item.startswith('_'):
                # 直接查找 {item}.json
                meta_path = os.path.join(item_path, f"{item}.json")
                
                if os.path.exists(meta_path):
                    try:
                        # 读取 Schema
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            schema = json.load(f)
                        
                        tool_name = schema["function"]["name"]
                        schemas.append(schema)
                        
                        # 动态加载类
                        parent_dir = os.path.basename(dir_path)
                        if parent_dir == "core":
                            module_path = f"src.harness.tools.core.{item}.tool"
                        else:
                            module_path = f"src.harness.tools.{item}.tool"
                        
                        module = importlib.import_module(module_path)
                        registry[tool_name] = {
                            "class": module.Tool,
                            "is_core": is_core
                        }
                        print(f"✅ 注册{'核心' if is_core else '业务'}工具: {tool_name}")
                    except Exception as e:
                        print(f"❌ 加载工具 {item} 失败: {e}")

    @classmethod
    def get_all_tool_schemas(cls) -> List[Dict[str, Any]]:
        """获取所有业务工具的 schema 定义（核心工具不在这里，由 tool_kit 单独注入）"""
        cls.initialize()
        return cls._BUSINESS_TOOLS_SCHEMAS

    @classmethod
    def get_core_tool_schemas(cls) -> List[Dict[str, Any]]:
        """获取核心工具的 schema 定义（task_done、yield_to_human）"""
        cls.initialize()
        return cls._CORE_TOOLS_SCHEMAS

    @classmethod
    def get_business_tool_names(cls) -> List[str]:
        """获取所有业务工具名称"""
        cls.initialize()
        return list(cls._BUSINESS_TOOLS_REGISTRY.keys())

    @classmethod
    def is_core_tool(cls, tool_name: str) -> bool:
        """判断是否为核心工具"""
        cls.initialize()
        return tool_name.lower() in cls._CORE_TOOLS_REGISTRY

    @classmethod
    def is_business_tool(cls, tool_name: str) -> bool:
        """判断是否为业务工具"""
        cls.initialize()
        return tool_name.lower() in cls._BUSINESS_TOOLS_REGISTRY

    @classmethod
    def dispatch(cls, tool_name: str, arguments: dict, context=None) -> str:
        """
        统一工具调度入口
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            context: 上下文对象（传递给核心工具）
        
        Returns:
            工具执行结果（JSON字符串）
        
        Raises:
            ValueError: 当工具不存在时抛出
        """
        cls.initialize()
        
        tool_name_lower = tool_name.lower()
        
        # 1. 优先查找核心工具
        tool_info = cls._CORE_TOOLS_REGISTRY.get(tool_name_lower)
        if tool_info:
            ToolClass = tool_info["class"]
            tool_instance = ToolClass(context=context)
            result = tool_instance.execute(arguments)
            return json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        
        # 2. 查找业务工具
        tool_info = cls._BUSINESS_TOOLS_REGISTRY.get(tool_name_lower)
        if tool_info:
            ToolClass = tool_info["class"]
            tool_instance = ToolClass(context=context)
            result = tool_instance.execute(arguments)
            return json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
        
        # 3. 尝试使用 route.py 调度基础任务工具（bash、filesystem、search、mcp 等）
        try:
            from src.tool.utils.route import dispatch_tool
            return dispatch_tool(tool_name, arguments)
        except ImportError as e:
            raise ValueError(f"❌ 找不到工具: {tool_name}，且无法加载基础任务工具路由: {str(e)}")
        except Exception as e:
            raise ValueError(f"❌ 工具 [{tool_name}] 执行失败: {str(e)}")

    @classmethod
    def validate_tool(cls, tool_name: str) -> bool:
        """验证工具是否存在"""
        cls.initialize()
        return (tool_name.lower() in cls._CORE_TOOLS_REGISTRY 
                or tool_name.lower() in cls._BUSINESS_TOOLS_REGISTRY)