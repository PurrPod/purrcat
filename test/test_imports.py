#!/usr/bin/env python3
"""
模块导入测试脚本
测试项目各个模块能否正常导入，不进行深度功能测试
"""
import sys
import os
import traceback

def test_import(module_name):
    """测试单个模块导入"""
    try:
        __import__(module_name)
        print(f"✅ {module_name}")
        return True
    except Exception as e:
        print(f"❌ {module_name}: {type(e).__name__}: {e}")
        print(traceback.format_exc())
        return False

def main():
    print("="*60)
    print("开始模块导入测试")
    print("="*60)

    failed = []

    modules = [
        "src.utils.config",
        "src.utils.enums",
        "src.utils.tracker",
        "src.model",
        "src.model.core",
        "src.model.core.llm_client",
        "src.model.facade",
        "src.model.facade.model",
        "src.model.manager",
        "src.model.manager.concurrency",
        "src.model.manager.key_manager",
        "src.memory.purrmemo",
        "src.memory.purrmemo.client",
        "src.memory.purrmemo.core",
        "src.memory.purrmemo.core.config",
        "src.memory.purrmemo.core.search_tool",
        "src.agent.manager",
        "src.tool",
        "src.tool.utils.format",
        "src.tool.utils.route",
        "src.tool.bash",
        "src.tool.callmcp",
        "src.tool.cron",
        "src.tool.fetch",
        "src.tool.filesystem",
        "src.tool.memo",
        "src.tool.search",
        "src.tool.task",
        "src.sensor",
        "src.sensor.base",
        "src.sensor.gateway",
        "src.harness.task",
    ]

    for module in modules:
        if not test_import(module):
            failed.append(module)

    print("="*60)
    if failed:
        print(f"测试失败！共有 {len(failed)} 个模块导入失败：")
        for m in failed:
            print(f"  - {m}")
        return 1
    else:
        print(f"✅ 所有 {len(modules)} 个模块导入测试通过！")
        return 0

if __name__ == "__main__":
    sys.exit(main())
