"""
Vector Store - 向量存储

负责:
- 向量化存储
- 相似度搜索
- 嵌入管理
"""

from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
import threading


@dataclass
class VectorItem:
    """向量项"""
    id: str
    vector: np.ndarray
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "vector": self.vector.tolist(),
            "content": self.content,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


class VectorStore:
    """
    向量存储
    
    提供向量化的语义存储和搜索
    """
    
    def __init__(self, dimension: int = 768):
        self.dimension = dimension
        
        self._vectors: Dict[str, VectorItem] = {}
        self._lock = threading.Lock()
        self._embedder = None
    
    def set_embedder(self, embedder) -> None:
        """
        设置嵌入模型
        
        Args:
            embedder: 嵌入模型(需要有 embed 方法)
        """
        self._embedder = embedder
    
    def add(
        self,
        id: str,
        vector: Optional[np.ndarray] = None,
        content: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加向量
        
        Args:
            id: 唯一标识
            vector: 向量,如果不提供则从 content 生成
            content: 内容
            metadata: 元数据
            
        Returns:
            是否成功
        """
        with self._lock:
            # 如果没有提供向量,尝试从内容生成
            if vector is None:
                if self._embedder and content:
                    vector = self._embed(content)
                else:
                    # 创建零向量
                    vector = np.zeros(self.dimension)
            
            # 确保向量维度正确
            if len(vector) != self.dimension:
                return False
            
            self._vectors[id] = VectorItem(
                id=id,
                vector=np.array(vector),
                content=content,
                metadata=metadata or {}
            )
            
            return True
    
    def _embed(self, content: Any) -> np.ndarray:
        """生成嵌入向量"""
        if self._embedder is None:
            # 返回随机向量作为占位符
            return np.random.randn(self.dimension).astype(np.float32)
        
        if hasattr(self._embedder, 'embed'):
            return np.array(self._embedder.embed(str(content)))
        
        return np.random.randn(self.dimension).astype(np.float32)
    
    def get(self, id: str) -> Optional[VectorItem]:
        """获取向量项"""
        return self._vectors.get(id)
    
    def delete(self, id: str) -> bool:
        """删除向量"""
        with self._lock:
            if id in self._vectors:
                del self._vectors[id]
                return True
            return False
    
    def search(
        self,
        query: Any,
        query_vector: Optional[np.ndarray] = None,
        limit: int = 10,
        threshold: float = 0.0
    ) -> List[Tuple[VectorItem, float]]:
        """
        相似度搜索
        
        Args:
            query: 查询内容
            query_vector: 查询向量,如果不提供则从 query 生成
            limit: 返回数量限制
            threshold: 相似度阈值
            
        Returns:
            (向量项, 相似度) 列表
        """
        if query_vector is None:
            query_vector = self._embed(query)
        
        query_vector = np.array(query_vector)
        
        results = []
        
        for item in self._vectors.values():
            similarity = self._cosine_similarity(query_vector, item.vector)
            
            if similarity >= threshold:
                results.append((item, similarity))
        
        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:limit]
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    def search_by_text(
        self,
        text: str,
        limit: int = 10,
        threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        按文本搜索
        
        Args:
            text: 查询文本
            limit: 返回数量
            threshold: 相似度阈值
            
        Returns:
            结果列表
        """
        results = self.search(text, limit=limit, threshold=threshold)
        
        return [
            {
                "id": item.id,
                "content": item.content,
                "similarity": similarity,
                "metadata": item.metadata
            }
            for item, similarity in results
        ]
    
    def update(
        self,
        id: str,
        vector: Optional[np.ndarray] = None,
        content: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        更新向量项
        
        Args:
            id: 唯一标识
            vector: 新向量
            content: 新内容
            metadata: 新元数据
            
        Returns:
            是否成功
        """
        with self._lock:
            if id not in self._vectors:
                return False
            
            item = self._vectors[id]
            
            if vector is not None:
                item.vector = np.array(vector)
            elif content is not None:
                item.vector = self._embed(content)
            
            if content is not None:
                item.content = content
            
            if metadata is not None:
                item.metadata.update(metadata)
            
            return True
    
    def clear(self) -> None:
        """清空所有向量"""
        with self._lock:
            self._vectors.clear()
    
    def size(self) -> int:
        """获取向量数量"""
        return len(self._vectors)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_vectors": len(self._vectors),
            "dimension": self.dimension,
            "has_embedder": self._embedder is not None
        }
    
    def list_ids(self) -> List[str]:
        """列出所有 ID"""
        return list(self._vectors.keys())
