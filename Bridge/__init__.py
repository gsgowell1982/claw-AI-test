# Bridge Layer - 桥接层
"""
Bridge 层负责:
- 请求流向解析
- 组件间通信
- 消息调度
"""

from .dispatcher import Dispatcher, MessageRoute

__all__ = ['Dispatcher', 'MessageRoute']
