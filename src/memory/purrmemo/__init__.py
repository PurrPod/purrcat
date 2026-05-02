#!/usr/bin/env python3
"""
PurrMemo 记忆管理系统核心模块
"""

from .client import PurrMemoClient, get_memory_client

__version__ = "1.0.0"
__all__ = ["PurrMemoClient", "get_memory_client"]
