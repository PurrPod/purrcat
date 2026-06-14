"""
平台适配器模块
"""

from .base import BasePlatformAdapter
from .factory import get_platform_adapter

__all__ = ["BasePlatformAdapter", "get_platform_adapter"]