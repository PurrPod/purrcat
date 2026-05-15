#!/usr/bin/env python3
"""
模块导入测试脚本
测试项目核心模块能否正常导入
"""
import sys
import os
import traceback
from pathlib import Path

project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

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
        "src.utils.tracker",
        "src.model",
        "src.model.core",
        "src.model.facade",
        "src.model.manager",
        "src.memory.purrmemo",
        "src.agent.manager",
        "src.tool",
        "src.sensor",
        "src.harness.process",
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
