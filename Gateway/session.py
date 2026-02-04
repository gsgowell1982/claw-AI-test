"""
Session Manager - 会话管理与隔离

负责:
- 会话创建与销毁
- 会话状态管理
- 会话隔离
- 会话持久化
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import uuid
import threading


@dataclass
class Message:
    """消息数据类"""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class Session:
    """
    会话类
    
    代表一个独立的用户会话
    """
    session_id: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_message(self, role: str, content: str, **metadata) -> Message:
        """
        添加消息到会话
        
        Args:
            role: 消息角色 (user/assistant/system)
            content: 消息内容
            **metadata: 额外元数据
            
        Returns:
            创建的消息对象
        """
        message = Message(role=role, content=content, metadata=metadata)
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message
    
    def get_history(self, limit: Optional[int] = None) -> List[Message]:
        """
        获取消息历史
        
        Args:
            limit: 限制返回的消息数量
            
        Returns:
            消息列表
        """
        if limit is None:
            return self.messages.copy()
        return self.messages[-limit:]
    
    def clear_history(self) -> None:
        """清空消息历史"""
        self.messages.clear()
        self.updated_at = datetime.now()
    
    def set_context(self, key: str, value: Any) -> None:
        """设置上下文变量"""
        self.context[key] = value
        self.updated_at = datetime.now()
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """获取上下文变量"""
        return self.context.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [m.to_dict() for m in self.messages],
            "context": self.context,
            "metadata": self.metadata
        }


class SessionManager:
    """
    会话管理器
    
    负责管理所有用户会话
    """
    
    def __init__(self, max_sessions: int = 1000, session_timeout: int = 3600):
        """
        初始化会话管理器
        
        Args:
            max_sessions: 最大会话数量
            session_timeout: 会话超时时间(秒)
        """
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        self.max_sessions = max_sessions
        self.session_timeout = session_timeout
    
    def create(self, session_id: Optional[str] = None) -> Session:
        """
        创建新会话
        
        Args:
            session_id: 可选的会话 ID,不提供则自动生成
            
        Returns:
            新创建的会话
        """
        with self._lock:
            if session_id is None:
                session_id = str(uuid.uuid4())
            
            # 检查是否超过最大会话数
            if len(self._sessions) >= self.max_sessions:
                self._cleanup_oldest()
            
            session = Session(session_id=session_id)
            self._sessions[session_id] = session
            return session
    
    def get(self, session_id: str) -> Optional[Session]:
        """
        获取会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话对象,不存在则返回 None
        """
        return self._sessions.get(session_id)
    
    def get_or_create(self, session_id: Optional[str] = None) -> Session:
        """
        获取或创建会话
        
        Args:
            session_id: 可选的会话 ID
            
        Returns:
            会话对象
        """
        if session_id:
            session = self.get(session_id)
            if session:
                return session
        return self.create(session_id)
    
    def remove(self, session_id: str) -> bool:
        """
        移除会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功移除
        """
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话信息
        
        Returns:
            会话信息列表
        """
        return [
            {
                "session_id": s.session_id,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "message_count": len(s.messages)
            }
            for s in self._sessions.values()
        ]
    
    def count(self) -> int:
        """获取活跃会话数量"""
        return len(self._sessions)
    
    def _cleanup_oldest(self) -> None:
        """清理最旧的会话"""
        if not self._sessions:
            return
        
        # 按更新时间排序,删除最旧的 10%
        sorted_sessions = sorted(
            self._sessions.items(),
            key=lambda x: x[1].updated_at
        )
        
        to_remove = max(1, len(sorted_sessions) // 10)
        for session_id, _ in sorted_sessions[:to_remove]:
            del self._sessions[session_id]
    
    def cleanup_expired(self) -> int:
        """
        清理过期会话
        
        Returns:
            清理的会话数量
        """
        now = datetime.now()
        expired = []
        
        with self._lock:
            for session_id, session in self._sessions.items():
                delta = (now - session.updated_at).total_seconds()
                if delta > self.session_timeout:
                    expired.append(session_id)
            
            for session_id in expired:
                del self._sessions[session_id]
        
        return len(expired)
