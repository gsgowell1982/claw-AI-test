"""
Short Term Memory - 短期记忆

负责:
- 会话级别的临时存储
- 快速读写
- 自动过期
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading


@dataclass
class MemoryItem:
    """记忆项"""
    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed.isoformat(),
            "metadata": self.metadata
        }


class ShortTermMemory:
    """
    短期记忆
    
    提供会话级别的快速临时存储
    """
    
    DEFAULT_TTL = 3600  # 默认 TTL (秒)
    MAX_ITEMS = 10000   # 最大项目数
    
    def __init__(
        self,
        default_ttl: int = DEFAULT_TTL,
        max_items: int = MAX_ITEMS
    ):
        self.default_ttl = default_ttl
        self.max_items = max_items
        
        self._storage: Dict[str, MemoryItem] = {}
        self._lock = threading.Lock()
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        设置记忆
        
        Args:
            key: 键
            value: 值
            ttl: 过期时间(秒)
            metadata: 元数据
            
        Returns:
            是否成功
        """
        with self._lock:
            # 检查容量
            if len(self._storage) >= self.max_items and key not in self._storage:
                self._evict_oldest()
            
            expires_at = None
            if ttl is not None:
                expires_at = datetime.now() + timedelta(seconds=ttl)
            elif self.default_ttl > 0:
                expires_at = datetime.now() + timedelta(seconds=self.default_ttl)
            
            self._storage[key] = MemoryItem(
                key=key,
                value=value,
                expires_at=expires_at,
                metadata=metadata or {}
            )
            
            return True
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取记忆
        
        Args:
            key: 键
            default: 默认值
            
        Returns:
            值
        """
        with self._lock:
            item = self._storage.get(key)
            
            if item is None:
                return default
            
            if item.is_expired():
                del self._storage[key]
                return default
            
            # 更新访问信息
            item.access_count += 1
            item.last_accessed = datetime.now()
            
            return item.value
    
    def delete(self, key: str) -> bool:
        """
        删除记忆
        
        Args:
            key: 键
            
        Returns:
            是否成功
        """
        with self._lock:
            if key in self._storage:
                del self._storage[key]
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        with self._lock:
            item = self._storage.get(key)
            if item is None:
                return False
            if item.is_expired():
                del self._storage[key]
                return False
            return True
    
    def keys(self, pattern: Optional[str] = None) -> List[str]:
        """
        获取所有键
        
        Args:
            pattern: 匹配模式
            
        Returns:
            键列表
        """
        self._cleanup_expired()
        
        keys = list(self._storage.keys())
        
        if pattern:
            import fnmatch
            keys = [k for k in keys if fnmatch.fnmatch(k, pattern)]
        
        return keys
    
    def values(self) -> List[Any]:
        """获取所有值"""
        self._cleanup_expired()
        return [item.value for item in self._storage.values()]
    
    def items(self) -> List[tuple]:
        """获取所有键值对"""
        self._cleanup_expired()
        return [(k, v.value) for k, v in self._storage.items()]
    
    def clear(self) -> None:
        """清空所有记忆"""
        with self._lock:
            self._storage.clear()
    
    def size(self) -> int:
        """获取记忆数量"""
        return len(self._storage)
    
    def _evict_oldest(self) -> None:
        """驱逐最旧的项目"""
        if not self._storage:
            return
        
        # 按最后访问时间排序,删除最旧的 10%
        sorted_items = sorted(
            self._storage.items(),
            key=lambda x: x[1].last_accessed
        )
        
        to_remove = max(1, len(sorted_items) // 10)
        for key, _ in sorted_items[:to_remove]:
            del self._storage[key]
    
    def _cleanup_expired(self) -> int:
        """清理过期项目"""
        expired = []
        
        with self._lock:
            for key, item in self._storage.items():
                if item.is_expired():
                    expired.append(key)
            
            for key in expired:
                del self._storage[key]
        
        return len(expired)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        self._cleanup_expired()
        
        total_access = sum(item.access_count for item in self._storage.values())
        
        return {
            "total_items": len(self._storage),
            "max_items": self.max_items,
            "default_ttl": self.default_ttl,
            "total_access_count": total_access
        }
    
    def touch(self, key: str, ttl: Optional[int] = None) -> bool:
        """
        刷新过期时间
        
        Args:
            key: 键
            ttl: 新的 TTL
            
        Returns:
            是否成功
        """
        with self._lock:
            item = self._storage.get(key)
            if item is None or item.is_expired():
                return False
            
            if ttl is not None:
                item.expires_at = datetime.now() + timedelta(seconds=ttl)
            elif self.default_ttl > 0:
                item.expires_at = datetime.now() + timedelta(seconds=self.default_ttl)
            
            return True
