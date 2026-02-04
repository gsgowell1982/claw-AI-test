"""
Memory Bridge - 内存桥接

负责:
- Gateway 与 Memory 层的通信
- 读写逻辑封装
- 缓存管理
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class MemoryEntry:
    """内存条目"""
    key: str
    value: Any
    memory_type: str  # 'short_term', 'long_term', 'vector'
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "memory_type": self.memory_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }


class MemoryBridge:
    """
    内存桥接器
    
    提供 Gateway 访问 Memory 层的统一接口
    """
    
    def __init__(self):
        self._short_term = None
        self._long_term = None
        self._vector_store = None
        self._cache: Dict[str, MemoryEntry] = {}
        self._cache_enabled = True
    
    def set_short_term_memory(self, memory) -> None:
        """设置短期记忆"""
        self._short_term = memory
    
    def set_long_term_memory(self, memory) -> None:
        """设置长期记忆"""
        self._long_term = memory
    
    def set_vector_store(self, store) -> None:
        """设置向量存储"""
        self._vector_store = store
    
    def enable_cache(self, enabled: bool = True) -> None:
        """启用/禁用缓存"""
        self._cache_enabled = enabled
    
    async def read(
        self,
        key: str,
        memory_type: str = "short_term",
        use_cache: bool = True
    ) -> Optional[Any]:
        """
        读取记忆
        
        Args:
            key: 键
            memory_type: 记忆类型
            use_cache: 是否使用缓存
            
        Returns:
            值,不存在则返回 None
        """
        # 检查缓存
        cache_key = f"{memory_type}:{key}"
        if use_cache and self._cache_enabled and cache_key in self._cache:
            return self._cache[cache_key].value
        
        # 从对应存储读取
        value = None
        if memory_type == "short_term" and self._short_term:
            value = await self._read_from_store(self._short_term, key)
        elif memory_type == "long_term" and self._long_term:
            value = await self._read_from_store(self._long_term, key)
        elif memory_type == "vector" and self._vector_store:
            value = await self._read_from_store(self._vector_store, key)
        
        # 更新缓存
        if value is not None and use_cache and self._cache_enabled:
            self._cache[cache_key] = MemoryEntry(
                key=key,
                value=value,
                memory_type=memory_type,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                metadata={}
            )
        
        return value
    
    async def write(
        self,
        key: str,
        value: Any,
        memory_type: str = "short_term",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        写入记忆
        
        Args:
            key: 键
            value: 值
            memory_type: 记忆类型
            metadata: 元数据
            
        Returns:
            是否成功
        """
        success = False
        
        if memory_type == "short_term" and self._short_term:
            success = await self._write_to_store(self._short_term, key, value)
        elif memory_type == "long_term" and self._long_term:
            success = await self._write_to_store(self._long_term, key, value)
        elif memory_type == "vector" and self._vector_store:
            success = await self._write_to_store(self._vector_store, key, value)
        
        # 更新缓存
        if success and self._cache_enabled:
            cache_key = f"{memory_type}:{key}"
            now = datetime.now()
            self._cache[cache_key] = MemoryEntry(
                key=key,
                value=value,
                memory_type=memory_type,
                created_at=now,
                updated_at=now,
                metadata=metadata or {}
            )
        
        return success
    
    async def delete(
        self,
        key: str,
        memory_type: str = "short_term"
    ) -> bool:
        """
        删除记忆
        
        Args:
            key: 键
            memory_type: 记忆类型
            
        Returns:
            是否成功
        """
        success = False
        
        if memory_type == "short_term" and self._short_term:
            success = await self._delete_from_store(self._short_term, key)
        elif memory_type == "long_term" and self._long_term:
            success = await self._delete_from_store(self._long_term, key)
        elif memory_type == "vector" and self._vector_store:
            success = await self._delete_from_store(self._vector_store, key)
        
        # 清除缓存
        cache_key = f"{memory_type}:{key}"
        if cache_key in self._cache:
            del self._cache[cache_key]
        
        return success
    
    async def search(
        self,
        query: str,
        memory_type: str = "vector",
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索记忆
        
        Args:
            query: 查询字符串
            memory_type: 记忆类型
            limit: 返回数量限制
            
        Returns:
            搜索结果列表
        """
        if memory_type == "vector" and self._vector_store:
            if hasattr(self._vector_store, 'search'):
                return await self._vector_store.search(query, limit=limit)
        
        return []
    
    async def _read_from_store(self, store, key: str) -> Optional[Any]:
        """从存储读取"""
        if hasattr(store, 'get'):
            if asyncio.iscoroutinefunction(store.get):
                return await store.get(key)
            return store.get(key)
        return None
    
    async def _write_to_store(self, store, key: str, value: Any) -> bool:
        """写入存储"""
        if hasattr(store, 'set'):
            if asyncio.iscoroutinefunction(store.set):
                await store.set(key, value)
            else:
                store.set(key, value)
            return True
        return False
    
    async def _delete_from_store(self, store, key: str) -> bool:
        """从存储删除"""
        if hasattr(store, 'delete'):
            if asyncio.iscoroutinefunction(store.delete):
                await store.delete(key)
            else:
                store.delete(key)
            return True
        return False
    
    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            "enabled": self._cache_enabled,
            "entries": len(self._cache),
            "types": {
                "short_term": sum(1 for e in self._cache.values() if e.memory_type == "short_term"),
                "long_term": sum(1 for e in self._cache.values() if e.memory_type == "long_term"),
                "vector": sum(1 for e in self._cache.values() if e.memory_type == "vector")
            }
        }


# 需要导入 asyncio
import asyncio
