import os
import json
from typing import Any, Dict
from src.harness.node.base import BaseNode


class Node(BaseNode):
    """环境变量加载器：动态读取图专属文件夹下的 env.json 并提供缓存与按需提取能力"""

    async def execute(self, inputs: Dict[str, Any], context: Any) -> Dict[str, Any]:
        self.log(context, "SYSTEM", "🌐 [环境变量] 节点启动")
        
        # 1. 动态获取当前运行的图名称
        graph_name = getattr(context, "graph_name", "default")
        
        # 2. 定位 harness 根目录 (当前文件在 harness/node/extensions/env_loader/node.py，向上找4层)
        harness_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        
        # 路径 A (你提议的优雅文件夹模式): harness/graph/{graph_name}/env.json
        folder_mode_path = os.path.join(harness_dir, "graph", graph_name, "env.json")
        # 路径 B (平铺兜底模式): harness/graph/{graph_name}_env.json
        flat_mode_path = os.path.join(harness_dir, "graph", f"{graph_name}_env.json")
        
        # 决定最终读取路径
        if os.path.exists(folder_mode_path):
            target_env_path = folder_mode_path
        else:
            target_env_path = flat_mode_path

        # 3. 任务级单例缓存读取逻辑 (防止图中多节点或循环引发的重复磁盘I/O)
        if not hasattr(context, "_global_env_cache"):
            context._global_env_cache = {}
            
        if graph_name not in context._global_env_cache:
            if not os.path.exists(target_env_path):
                self.log(context, "WARNING", f"⚠️ [环境变量] 未找到此图专属的环境配置文件，将初始化为空配置。检查路径: {target_env_path}")
                context._global_env_cache[graph_name] = {}
            else:
                try:
                    with open(target_env_path, "r", encoding="utf-8") as f:
                        context._global_env_cache[graph_name] = json.load(f)
                    self.log(context, "SYSTEM", f"✅ [环境变量] 成功从磁盘加载并缓存 env.json -> ({target_env_path})")
                except Exception as e:
                    self.log(context, "ERROR", f"❌ [环境变量] 解析 JSON 配置文件失败: {e}")
                    raise RuntimeError(f"环境变量文件损坏: {e}")
        else:
            self.log(context, "SYSTEM", "⚡ [环境变量] 命中当前任务内存缓存，直接读取，无磁盘 I/O 损耗")

        # 拿到大 JSON 配置字典
        env_data = context._global_env_cache[graph_name]

        # 4. 依照前端用户"添加变量"的配置，精准进行引脚数据投递
        exposed_keys = self.config.get("exposed_keys", [])
        outputs = {}
        exposed_count = 0

        for item in exposed_keys:
            if not isinstance(item, dict):
                continue
            
            key_name = item.get("name")
            if not key_name:
                continue
            
            # 从大 JSON 中捞取值，哪怕值本身是另一个 Dict/List 也完全支持
            val = env_data.get(key_name)
            outputs[key_name] = val
            
            # 日志脱敏或简短预览
            val_preview = str(val)[:40] + "..." if len(str(val)) > 40 else str(val)
            self.log(context, "SYSTEM", f"  🔹 成功暴露变量 [{key_name}] = {val_preview}")
            exposed_count += 1

        self.log(context, "SYSTEM", f"✅ [环境变量] 分发完成，共输出 {exposed_count} 个变量至下游链路")
        return outputs