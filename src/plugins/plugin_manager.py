import os
import re

import yaml
from typing import Dict, Optional, List

GLOBAL_TOOL_YAML = os.path.join(os.path.dirname(__file__), "tool.yaml")
PLUGIN_COLLECTION_DIR = os.path.join(os.path.dirname(__file__), "plugin_collection")

CONFIG_DATA = {}


def load_global_tool_yaml() -> Dict:
    """加载全局tool.yaml配置（返回扁平字典，顶层为mcp_type）"""
    try:
        with open(GLOBAL_TOOL_YAML, "r", encoding="utf-8") as f:
            global CONFIG_DATA
            CONFIG_DATA = yaml.safe_load(f) or {}
        if not isinstance(CONFIG_DATA, dict):
            raise TypeError(f"tool.yaml格式错误，需为字典结构（当前类型：{type(CONFIG_DATA)}）")
        return CONFIG_DATA
    except yaml.YAMLError as e:
        raise ValueError(f"解析tool.yaml失败：{str(e)}")
    except Exception as e:
        # 首次启动可能文件不存在，允许返回空
        if isinstance(e, FileNotFoundError):
            return {}
        raise RuntimeError(f"加载tool.yaml异常：{str(e)}")


def get_config_data():
    return CONFIG_DATA


def init_config_data():
    load_global_tool_yaml()


def get_plugin_config(mcp_type: str) -> Optional[Dict]:
    """根据mcp_type读取插件完整配置"""
    if not isinstance(mcp_type, str) or not mcp_type.strip():
        raise ValueError("mcp_type必须是非空字符串")
    try:
        global_config = get_config_data()
        return global_config.get(mcp_type)
    except Exception as e:
        print(f"加载配置发生错误：{e}")
        return {}


def get_plugin_tool_info(tools: List[str]) -> Optional[List[Dict]]:
    init_config_data()
    global_config = get_config_data()
    tool_pool = []
    added_func_names = set()
    for tool_identifier in tools:
        if not tool_identifier: continue
        if '/' in tool_identifier or '__' in tool_identifier:
            try:
                if '/' in tool_identifier:
                    mcp_type, func_name = tool_identifier.split('/', 1)
                else:
                    mcp_type, func_name = tool_identifier.split('__', 1)
                if mcp_type not in global_config:
                    try:
                        register_plugin(mcp_type)
                        global_config = get_config_data()
                    except Exception as e:
                        # 修复了漏掉的 f 字符串前缀
                        print(f"Warning: 插件 {mcp_type} 不存在或无导出函数. 错误: {e}")

                if mcp_type in global_config and 'functions' in global_config[mcp_type]:
                    tool_config = global_config[mcp_type]['functions'].get(func_name)
                    if tool_config:
                        real_name = tool_config.get('function', {}).get('name')
                        if real_name and real_name not in added_func_names:
                            tool_pool.append(tool_config)
                            added_func_names.add(real_name)
                    else:
                        print(f"Warning: 函数 {func_name} 未在 {mcp_type} 中定义")
            except Exception as e:
                print(f"Error parsing tool identifier '{tool_identifier}': {e}")

        else:
            mcp_type = tool_identifier
            if mcp_type not in global_config:
                try:
                    register_plugin(mcp_type)
                    global_config = get_config_data()
                except Exception as e:
                    print(f"Warning: 插件 {mcp_type} 不存在或无导出函数. 错误: {e}")

            if mcp_type in global_config and 'functions' in global_config[mcp_type]:
                all_funcs = global_config[mcp_type]['functions']
                for _, tool_config in all_funcs.items():
                    real_name = tool_config.get('function', {}).get('name')
                    if real_name and real_name not in added_func_names:
                        tool_pool.append(tool_config)
                        added_func_names.add(real_name)
            else:
                print(f"Warning: 插件 {mcp_type} 仍未找到有效配置")

    return tool_pool

def register_plugin(plugin_name: str) -> bool:
    print(f"正在尝试注册插件: {plugin_name} ...")
    plugin_dir = os.path.join(PLUGIN_COLLECTION_DIR, plugin_name)
    config_file = os.path.join(plugin_dir, f"{plugin_name}.yaml")

    if not os.path.isdir(plugin_dir) or not os.path.isfile(config_file):
        print(f"错误：插件目录或配置文件不存在 -> {plugin_dir}")
        return False

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            new_config = yaml.safe_load(f)

        # 提取配置内容
        content = new_config
        if isinstance(new_config, dict) and len(new_config) == 1 and plugin_name in new_config:
            content = new_config[plugin_name]

        # 读取全局配置
        current = {}
        if os.path.exists(GLOBAL_TOOL_YAML):
            with open(GLOBAL_TOOL_YAML, 'r', encoding='utf-8') as f:
                current = yaml.safe_load(f) or {}

        # 写入
        current[plugin_name] = content
        with open(GLOBAL_TOOL_YAML, 'w', encoding='utf-8') as f:
            yaml.dump(current, f, allow_unicode=True, sort_keys=False, indent=2)

        init_config_data()  # 刷新内存
        return True
    except Exception as e:
        print(f"注册插件异常：{e}")
        return False


def unregister_plugin(plugin_name: str) -> bool:
    print(f"正在尝试注销插件: {plugin_name} ...")
    try:
        with open(GLOBAL_TOOL_YAML, 'r', encoding='utf-8') as f:
            current = yaml.safe_load(f) or {}

        if plugin_name in current:
            del current[plugin_name]
            with open(GLOBAL_TOOL_YAML, 'w', encoding='utf-8') as f:
                if not current:
                    f.write("")
                else:
                    yaml.dump(current, f, allow_unicode=True, sort_keys=False, indent=2)
            init_config_data()  # 刷新
        return True
    except Exception as e:
        print(f"注销插件异常：{e}")
        return False


if __name__ == '__main__':
    print(get_plugin_tool_info(["mock"]))