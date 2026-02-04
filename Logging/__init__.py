# Logging Layer - 日志层
"""
Logging 层负责:
- 日志记录
- 日志格式化
- 日志输出管理
"""

import logging
import sys
from typing import Optional
from pathlib import Path


class OpenClawLogger:
    """
    OpenClaw 日志器
    
    提供统一的日志接口
    """
    
    DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    def __init__(
        self,
        name: str = "OpenClaw",
        level: str = "INFO",
        format_str: Optional[str] = None,
        log_file: Optional[str] = None
    ):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # 清除已有处理器
        self.logger.handlers.clear()
        
        # 格式化器
        formatter = logging.Formatter(format_str or self.DEFAULT_FORMAT)
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
    
    def debug(self, message: str, *args, **kwargs) -> None:
        """记录 DEBUG 日志"""
        self.logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs) -> None:
        """记录 INFO 日志"""
        self.logger.info(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs) -> None:
        """记录 WARNING 日志"""
        self.logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs) -> None:
        """记录 ERROR 日志"""
        self.logger.error(message, *args, **kwargs)
    
    def critical(self, message: str, *args, **kwargs) -> None:
        """记录 CRITICAL 日志"""
        self.logger.critical(message, *args, **kwargs)
    
    def exception(self, message: str, *args, **kwargs) -> None:
        """记录异常"""
        self.logger.exception(message, *args, **kwargs)


# 全局日志实例
_logger: Optional[OpenClawLogger] = None


def get_logger(name: str = "OpenClaw") -> OpenClawLogger:
    """获取日志器"""
    global _logger
    if _logger is None:
        _logger = OpenClawLogger(name)
    return _logger


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None
) -> OpenClawLogger:
    """设置日志"""
    global _logger
    _logger = OpenClawLogger(
        name="OpenClaw",
        level=level,
        log_file=log_file
    )
    return _logger


# 便捷函数
def debug(message: str, *args, **kwargs) -> None:
    get_logger().debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs) -> None:
    get_logger().info(message, *args, **kwargs)


def warning(message: str, *args, **kwargs) -> None:
    get_logger().warning(message, *args, **kwargs)


def error(message: str, *args, **kwargs) -> None:
    get_logger().error(message, *args, **kwargs)


def critical(message: str, *args, **kwargs) -> None:
    get_logger().critical(message, *args, **kwargs)
