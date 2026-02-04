# Config Layer - 配置层
"""
Config 层负责:
- 环境变量管理
- 网络地址配置
- 应用配置
"""

from .manager import ConfigManager, get_config

__all__ = ['ConfigManager', 'get_config']
