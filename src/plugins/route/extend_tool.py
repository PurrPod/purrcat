import os
import yaml
import glob
from src.utils.config import SKILL_DIR

def extract_extend_fingerprints():
    """提取extend路由的工具指纹"""
    tools_index = []
    try:
        if os.path.exists(SKILL_DIR):
            skill_dirs = [d for d in os.listdir(SKILL_DIR) if os.path.isdir(os.path.join(SKILL_DIR, d))]
            for skill_name in skill_dirs:
                skill_path = os.path.join(SKILL_DIR, skill_name)
                plugin_dir = os.path.join(skill_path, "plugin")
                if os.path.exists(plugin_dir):
                    yaml_files = glob.glob(os.path.join(plugin_dir, "*.yaml")) + glob.glob(os.path.join(plugin_dir, "*.yml"))
                    for yaml_file in yaml_files:
                        try:
                            with open(yaml_file, "r", encoding="utf-8") as f:
                                plugin_config = yaml.safe_load(f) or {}
                            # 处理yaml文件，可能是直接包含插件配置，或者是嵌套在插件名下
                            if isinstance(plugin_config, dict):
                                # 检查是否有顶层插件名
                                if len(plugin_config) == 1:
                                    plugin_name = list(plugin_config.keys())[0]
                                    plugin_data = plugin_config[plugin_name]
                                else:
                                    plugin_name = os.path.basename(yaml_file).split('.')[0]
                                    plugin_data = plugin_config
                                functions = plugin_data.get("functions", {})
                                for func_name, func_data in functions.items():
                                    desc = func_data.get("function", {}).get("description", "无描述")
                                    tools_index.append({
                                        "route": "extend",
                                        "plugin": f"{skill_name}:{plugin_name}",
                                        "func": func_name,
                                        "desc": desc
                                    })
                        except Exception as e:
                            print(f"❌ 扫描 Skill 插件异常 {yaml_file}: {e}")
    except Exception as e:
        print(f"❌ 扫描 Skill 插件目录异常: {e}")
    return tools_index

def get_extend_tool_schemas(plugin_name, tool_names):
    """获取extend路由的工具schemas"""
    schemas = []
    try:
        # 解析plugin_name格式：skill_name:plugin_name
        if ":" in plugin_name:
            skill_name, plugin_name = plugin_name.split(":", 1)
            skill_path = os.path.join(SKILL_DIR, skill_name)
            plugin_dir = os.path.join(skill_path, "plugin")
            if os.path.exists(plugin_dir):
                # 查找对应的yaml文件
                yaml_files = glob.glob(os.path.join(plugin_dir, f"{plugin_name}.yaml")) + glob.glob(os.path.join(plugin_dir, f"{plugin_name}.yml"))
                if not yaml_files:
                    # 如果没找到，尝试所有yaml文件
                    yaml_files = glob.glob(os.path.join(plugin_dir, "*.yaml")) + glob.glob(os.path.join(plugin_dir, "*.yml"))
                for yaml_file in yaml_files:
                    try:
                        with open(yaml_file, "r", encoding="utf-8") as f:
                            plugin_config = yaml.safe_load(f) or {}
                        # 处理yaml文件，可能是直接包含插件配置，或者是嵌套在插件名下
                        if isinstance(plugin_config, dict):
                            # 检查是否有顶层插件名
                            if len(plugin_config) == 1:
                                yaml_plugin_name = list(plugin_config.keys())[0]
                                plugin_data = plugin_config[yaml_plugin_name]
                            else:
                                plugin_data = plugin_config
                            functions = plugin_data.get("functions", {})
                            for tool_name in tool_names:
                                func_config = functions.get(tool_name)
                                if func_config and "function" in func_config:
                                    schemas.append({"type": "function", "function": func_config["function"]})
                    except Exception as e:
                        print(f"❌ 读取 Extend Schema 失败 {yaml_file}: {e}")
    except Exception as e:
        print(f"❌ 读取 Extend Schema 失败: {e}")
    return schemas

def call_extend_tool(plugin, tool_name, arguments):
    """调用extend路由的工具"""
    import importlib
    import inspect
    import asyncio
    import json
    
    def _format_response(msg_type: str, content):
        return json.dumps({"type": msg_type, "content": content}, ensure_ascii=False)
    
    try:
        # 解析plugin名称，获取skill_name和plugin_name
        if ":" in plugin:
            skill_name, plugin_name = plugin.split(":", 1)
        else:
            return _format_response("error", f"❌ 插件名称格式错误，应为 'skill_name:plugin_name'")
        
        # 构建插件模块的路径
        module_path = f"data.skill.{skill_name}.plugin.{plugin_name}"
        try:
            plugin_module = importlib.import_module(module_path)
        except ImportError:
            # 尝试不同的导入路径
            module_path = f"data.skill.{skill_name}.plugin"
            try:
                plugin_module = importlib.import_module(module_path)
            except ImportError:
                return _format_response("error", f"❌ 无法导入插件模块: {module_path}")
        
        if not hasattr(plugin_module, tool_name):
            return _format_response("error", f"❌ 插件 '{plugin}' 中无函数：{tool_name}")
        
        target_func = getattr(plugin_module, tool_name)
        
        # 兼容异步工具执行
        if inspect.iscoroutinefunction(target_func):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                result = asyncio.get_event_loop().run_until_complete(target_func(**arguments))
            else:
                result = asyncio.run(target_func(**arguments))
        else:
            result = target_func(**arguments)
        
        if isinstance(result, str):
            return result
        else:
            return _format_response("text", str(result) if result is not None else "Success (No Output)")
    except Exception as e:
        return _format_response("error", f"❌ 调用extend工具时发生异常: {str(e)}")
