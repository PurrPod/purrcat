import os
import yaml
from src.utils.config import LOCAL_TOOL_YAML, PLUGIN_COLLECTION_DIR


def init_local_config_data():
    """初始化本地工具配置数据，强制重新注册所有必需插件"""
    # 确保文件存在
    if not os.path.exists(LOCAL_TOOL_YAML):
        with open(LOCAL_TOOL_YAML, 'w', encoding='utf-8') as f:
            f.write("")
    
    # 强制重新注册所有必需插件
    required_plugins = ["web", "database", "filesystem", "shell", "schedule", "multimodal"]
    for plugin in required_plugins:
        try:
            register_plugin(plugin)
        except Exception as e:
            print(f"❌ 注册插件 {plugin} 失败: {e}")
    
    try:
        from src.plugins.route.base_tool import load_local_tool_yaml
        load_local_tool_yaml()
    except Exception as e:
        print(f"本地插件系统加载失败！{e}")


def register_plugin(plugin_name: str) -> bool:
    plugin_dir = os.path.join(PLUGIN_COLLECTION_DIR, plugin_name)
    config_file = os.path.join(plugin_dir, f"{plugin_name}.yaml")
    if not os.path.isdir(plugin_dir):
        return False
    if not os.path.isfile(config_file):
        return False
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            new_config = yaml.safe_load(f)
        if not new_config:
            return False
        content = new_config
        if isinstance(new_config, dict) and len(new_config) == 1 and plugin_name in new_config:
            content = new_config[plugin_name]
        current = {}
        if os.path.exists(LOCAL_TOOL_YAML):
            with open(LOCAL_TOOL_YAML, 'r', encoding='utf-8') as f:
                current = yaml.safe_load(f) or {}
        if plugin_name in current:
            # 插件已存在，检查是否需要更新配置
            if current[plugin_name] != content:
                current[plugin_name] = content
                with open(LOCAL_TOOL_YAML, 'w', encoding='utf-8') as f:
                    yaml.dump(current, f, allow_unicode=True, sort_keys=False, indent=2)
                print(f"✅ 已更新插件 {plugin_name} 的配置")
            return True
        current[plugin_name] = content
        with open(LOCAL_TOOL_YAML, 'w', encoding='utf-8') as f:
            yaml.dump(current, f, allow_unicode=True, sort_keys=False, indent=2)
        return True
    except Exception as e:
        return False


def unregister_plugin(plugin_name: str) -> bool:
    print(f"正在尝试注销插件: {plugin_name} ...")
    try:
        current = {}
        if os.path.exists(LOCAL_TOOL_YAML):
            with open(LOCAL_TOOL_YAML, 'r', encoding='utf-8') as f:
                current = yaml.safe_load(f) or {}
        if plugin_name not in current:
            print(f"警告：插件 '{plugin_name}' 不存在，跳过注销")
            return True
        del current[plugin_name]
        with open(LOCAL_TOOL_YAML, 'w', encoding='utf-8') as f:
            if not current:
                f.write("")
            else:
                yaml.dump(current, f, allow_unicode=True, sort_keys=False, indent=2)
        print(f"✅ 插件 '{plugin_name}' 注销成功")
        return True
    except Exception as e:
        print(f"注销插件异常：{e}")
        return False


if __name__ == "__main__":
    # 初始化本地配置
    init_local_config_data()
    # 测试注册和注销功能
    register_plugin("web")
    register_plugin("feishu")
    unregister_plugin("web")
