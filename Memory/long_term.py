"""
Long Term Memory - 长期记忆

负责:
- 持久化存储
- 数据压缩
- 分级存储
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import threading


@dataclass
class LongTermItem:
    """长期记忆项"""
    key: str
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    version: int = 1
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "version": self.version,
            "tags": self.tags,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LongTermItem":
        return cls(
            key=data["key"],
            value=data["value"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            version=data.get("version", 1),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {})
        )


class LongTermMemory:
    """
    长期记忆
    
    提供持久化的长期存储
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        auto_save: bool = True
    ):
        self.storage_path = Path(storage_path) if storage_path else None
        self.auto_save = auto_save
        
        self._storage: Dict[str, LongTermItem] = {}
        self._lock = threading.Lock()
        self._modified = False
        
        # 加载已有数据
        if self.storage_path and self.storage_path.exists():
            self._load()
    
    def set(
        self,
        key: str,
        value: Any,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        设置记忆
        
        Args:
            key: 键
            value: 值
            tags: 标签
            metadata: 元数据
            
        Returns:
            是否成功
        """
        with self._lock:
            existing = self._storage.get(key)
            
            if existing:
                existing.value = value
                existing.updated_at = datetime.now()
                existing.version += 1
                if tags:
                    existing.tags = tags
                if metadata:
                    existing.metadata.update(metadata)
            else:
                self._storage[key] = LongTermItem(
                    key=key,
                    value=value,
                    tags=tags or [],
                    metadata=metadata or {}
                )
            
            self._modified = True
            
            if self.auto_save and self.storage_path:
                self._save()
            
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
        item = self._storage.get(key)
        return item.value if item else default
    
    def get_item(self, key: str) -> Optional[LongTermItem]:
        """获取完整记忆项"""
        return self._storage.get(key)
    
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
                self._modified = True
                
                if self.auto_save and self.storage_path:
                    self._save()
                
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return key in self._storage
    
    def keys(self, pattern: Optional[str] = None) -> List[str]:
        """获取所有键"""
        keys = list(self._storage.keys())
        
        if pattern:
            import fnmatch
            keys = [k for k in keys if fnmatch.fnmatch(k, pattern)]
        
        return keys
    
    def search_by_tags(self, tags: List[str]) -> List[LongTermItem]:
        """
        按标签搜索
        
        Args:
            tags: 标签列表
            
        Returns:
            匹配的记忆项
        """
        results = []
        
        for item in self._storage.values():
            if any(tag in item.tags for tag in tags):
                results.append(item)
        
        return results
    
    def search_by_metadata(
        self,
        criteria: Dict[str, Any]
    ) -> List[LongTermItem]:
        """
        按元数据搜索
        
        Args:
            criteria: 搜索条件
            
        Returns:
            匹配的记忆项
        """
        results = []
        
        for item in self._storage.values():
            match = True
            for key, value in criteria.items():
                if item.metadata.get(key) != value:
                    match = False
                    break
            
            if match:
                results.append(item)
        
        return results
    
    def clear(self) -> None:
        """清空所有记忆"""
        with self._lock:
            self._storage.clear()
            self._modified = True
            
            if self.auto_save and self.storage_path:
                self._save()
    
    def size(self) -> int:
        """获取记忆数量"""
        return len(self._storage)
    
    def _save(self) -> bool:
        """保存到文件"""
        if not self.storage_path:
            return False
        
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                key: item.to_dict()
                for key, item in self._storage.items()
            }
            
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self._modified = False
            return True
        except Exception:
            return False
    
    def _load(self) -> bool:
        """从文件加载"""
        if not self.storage_path or not self.storage_path.exists():
            return False
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self._storage = {
                key: LongTermItem.from_dict(item_data)
                for key, item_data in data.items()
            }
            
            return True
        except Exception:
            return False
    
    def save(self) -> bool:
        """手动保存"""
        with self._lock:
            return self._save()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_tags = set()
        for item in self._storage.values():
            total_tags.update(item.tags)
        
        return {
            "total_items": len(self._storage),
            "total_unique_tags": len(total_tags),
            "storage_path": str(self.storage_path) if self.storage_path else None,
            "auto_save": self.auto_save,
            "modified": self._modified
        }
