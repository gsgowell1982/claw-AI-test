"""
Short-term Memory - 短期记忆管理

版本: v2.5.1
功能:
- 会话内工具调用结果缓存
- 避免重复的工具调用
- 上下文信息聚合
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger("OpenClaw.Memory.ShortTerm")


@dataclass
class ToolCallRecord:
    """工具调用记录"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    ttl_seconds: int = 300  # 5分钟有效期
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now() > self.timestamp + timedelta(seconds=self.ttl_seconds)
    
    def matches(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """检查是否匹配（相同工具和参数）"""
        if self.tool_name != tool_name:
            return False
        # 比较参数
        return json.dumps(self.arguments, sort_keys=True) == json.dumps(arguments, sort_keys=True)


class ShortTermMemory:
    """
    短期记忆
    
    存储当前会话的工具调用结果，用于：
    1. 避免重复调用相同参数的工具
    2. 为 LLM 提供已知信息的上下文
    """
    
    def __init__(self, max_records: int = 50, default_ttl: int = 300):
        self.max_records = max_records
        self.default_ttl = default_ttl
        self._records: List[ToolCallRecord] = []
        self._context_cache: Dict[str, Any] = {}  # 关键信息缓存
    
    def add_tool_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        success: bool,
        ttl: Optional[int] = None
    ) -> None:
        """添加工具调用结果"""
        # 清理过期记录
        self._cleanup_expired()
        
        # 检查是否已存在相同调用，如果有则更新
        for i, record in enumerate(self._records):
            if record.matches(tool_name, arguments):
                self._records[i] = ToolCallRecord(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                    success=success,
                    ttl_seconds=ttl or self.default_ttl
                )
                logger.debug(f"[ShortTerm] 更新缓存: {tool_name}")
                return
        
        # 添加新记录
        record = ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            ttl_seconds=ttl or self.default_ttl
        )
        self._records.append(record)
        
        # 限制记录数量
        if len(self._records) > self.max_records:
            self._records = self._records[-self.max_records:]
        
        # 更新上下文缓存
        self._update_context_cache(tool_name, arguments, result, success)
        
        logger.debug(f"[ShortTerm] 添加缓存: {tool_name}, 当前记录数: {len(self._records)}")
    
    def get_cached_result(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Optional[ToolCallRecord]:
        """获取缓存的工具调用结果"""
        self._cleanup_expired()
        
        for record in reversed(self._records):  # 从最新的开始查找
            if record.matches(tool_name, arguments) and not record.is_expired():
                logger.info(f"[ShortTerm] 命中缓存: {tool_name}")
                return record
        
        return None
    
    def _update_context_cache(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any,
        success: bool
    ) -> None:
        """更新上下文缓存（提取关键信息）"""
        if not success:
            return
        
        # 根据工具类型提取关键信息
        if tool_name == "list_files":
            path = arguments.get("path", ".")
            if isinstance(result, dict) and "files" in result:
                self._context_cache[f"files_in_{path}"] = {
                    "files": result.get("files", []),
                    "directories": result.get("directories", []),
                    "timestamp": datetime.now().isoformat()
                }
        
        elif tool_name == "read_file":
            path = arguments.get("path", "")
            if isinstance(result, dict) and "content" in result:
                self._context_cache[f"file_content_{path}"] = {
                    "content_preview": result.get("content", "")[:500],
                    "size": result.get("size", 0),
                    "timestamp": datetime.now().isoformat()
                }
        
        elif tool_name == "check_package":
            package = arguments.get("package_name", "")
            if isinstance(result, dict):
                self._context_cache[f"package_{package}"] = {
                    "installed": result.get("installed", False),
                    "version": result.get("version"),
                    "timestamp": datetime.now().isoformat()
                }
    
    def get_context_summary(self) -> str:
        """获取上下文摘要，用于 LLM"""
        self._cleanup_expired()
        
        if not self._records and not self._context_cache:
            return ""
        
        summary_parts = []
        
        # 已知的文件列表
        for key, value in self._context_cache.items():
            if key.startswith("files_in_"):
                path = key.replace("files_in_", "")
                files = value.get("files", [])
                dirs = value.get("directories", [])
                if files or dirs:
                    summary_parts.append(
                        f"- 目录 '{path}' 包含: {len(files)} 个文件, {len(dirs)} 个子目录"
                    )
                    if files:
                        summary_parts.append(f"  文件: {', '.join(files[:10])}" + 
                                           ("..." if len(files) > 10 else ""))
        
        # 已知的包状态
        package_info = []
        for key, value in self._context_cache.items():
            if key.startswith("package_"):
                package = key.replace("package_", "")
                installed = value.get("installed", False)
                version = value.get("version", "")
                status = f"已安装({version})" if installed else "未安装"
                package_info.append(f"{package}: {status}")
        
        if package_info:
            summary_parts.append(f"- 包状态: {', '.join(package_info)}")
        
        # 最近的工具调用
        recent_calls = []
        for record in self._records[-5:]:  # 最近5次
            if record.success:
                recent_calls.append(f"{record.tool_name}({json.dumps(record.arguments, ensure_ascii=False)})")
        
        if recent_calls:
            summary_parts.append(f"- 最近调用: {', '.join(recent_calls)}")
        
        if summary_parts:
            return "## 当前会话已知信息（无需重复查询）\n\n" + "\n".join(summary_parts)
        
        return ""
    
    def get_recent_errors(self) -> List[Dict[str, Any]]:
        """获取最近的错误记录"""
        self._cleanup_expired()
        
        errors = []
        for record in self._records:
            if not record.success:
                errors.append({
                    "tool": record.tool_name,
                    "arguments": record.arguments,
                    "error": record.result,
                    "timestamp": record.timestamp.isoformat()
                })
        
        return errors[-5:]  # 最近5个错误
    
    def _cleanup_expired(self) -> None:
        """清理过期记录"""
        before = len(self._records)
        self._records = [r for r in self._records if not r.is_expired()]
        after = len(self._records)
        
        if before != after:
            logger.debug(f"[ShortTerm] 清理过期记录: {before} -> {after}")
    
    def clear(self) -> None:
        """清空所有记录"""
        self._records.clear()
        self._context_cache.clear()
        logger.info("[ShortTerm] 已清空所有记录")


# 会话级短期记忆存储
_session_memories: Dict[str, ShortTermMemory] = {}


def get_session_memory(session_id: str) -> ShortTermMemory:
    """获取会话的短期记忆"""
    if session_id not in _session_memories:
        _session_memories[session_id] = ShortTermMemory()
        logger.info(f"[ShortTerm] 创建会话记忆: {session_id[:8]}...")
    return _session_memories[session_id]


def clear_session_memory(session_id: str) -> None:
    """清除会话的短期记忆"""
    if session_id in _session_memories:
        del _session_memories[session_id]
        logger.info(f"[ShortTerm] 清除会话记忆: {session_id[:8]}...")
