# Test Module - 验证模块
"""
Test 模块负责:
- 自动化阶段验证
- 测试结果记录
- 验证日志管理
- 聊天交互日志
"""

from .stage_tracker import StageTracker, StageResult, run_stage1_verification
from .chat_logger import ChatLogger, get_chat_logger, log_chat

__all__ = [
    'StageTracker', 
    'StageResult', 
    'run_stage1_verification',
    'ChatLogger',
    'get_chat_logger',
    'log_chat'
]
