#!/usr/bin/env python3
# 测试init_tool函数

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath('.'))

print("开始测试init_tool函数...")

try:
    from src.plugins.plugin_manager import init_tool
    print("成功导入init_tool函数")
    
    # 执行初始化
    init_tool()
    print("初始化完成")
    
    # 检查tool.jsonl文件
    tool_jsonl_path = os.path.join('src', 'plugins', 'tool.jsonl')
    if os.path.exists(tool_jsonl_path):
        print(f"✅ tool.jsonl文件已创建")
        # 读取文件内容
        with open(tool_jsonl_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.strip().split('\n')
            print(f"✅ tool.jsonl包含 {len(lines)} 个工具条目")
            
            # 统计local工具数量
            local_count = 0
            for line in lines:
                if '"route": "local"' in line:
                    local_count += 1
            print(f"✅ 其中包含 {local_count} 个local工具")
            
            # 显示前5个local工具
            print("\n前5个local工具:")
            local_tools = [line for line in lines if '"route": "local"' in line]
            for i, tool in enumerate(local_tools[:5]):
                print(f"{i+1}. {tool}")
    else:
        print("❌ tool.jsonl文件未创建")
        
    print("\n测试完成")
    
except Exception as e:
    print(f"测试过程中出错: {e}")
    import traceback
    traceback.print_exc()
