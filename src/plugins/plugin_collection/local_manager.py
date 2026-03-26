import os
import yaml

LOCAL_TOOL_YAML = os.path.join(os.path.dirname(__file__), "local_tool.yaml")
PLUGIN_COLLECTION_DIR = os.path.dirname(__file__)


def init_local_config_data():
    if not os.path.exists(LOCAL_TOOL_YAML):
        with open(LOCAL_TOOL_YAML, 'w', encoding='utf-8') as f:
            f.write("")
    current = {}
    with open(LOCAL_TOOL_YAML, 'r', encoding='utf-8') as f:
        current = yaml.safe_load(f) or {}
    required_plugins = ["web", "feishu", "database", "manager", "filesystem"]
    for plugin in required_plugins:
        if plugin not in current:
            register_plugin(plugin)
    try:
        from src.plugins.plugin_manager import load_local_tool_yaml
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
