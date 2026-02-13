"""
Embeddings - 向量嵌入工具

版本: v2.5.3
功能:
- 文本向量化
- 语义相似度计算
- 支持多种后端（sentence-transformers, TF-IDF, 关键词）
"""

import json
import hashlib
import re
from typing import Optional, List, Dict, Any, Tuple
import logging

logger = logging.getLogger("OpenClaw.Memory.Embeddings")

# 尝试导入不同的嵌入后端
_EMBEDDING_BACKEND = None
_model = None
_vectorizer = None


def _init_backend():
    """初始化嵌入后端"""
    global _EMBEDDING_BACKEND, _model, _vectorizer
    
    if _EMBEDDING_BACKEND is not None:
        return
    
    # 尝试 sentence-transformers
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        _EMBEDDING_BACKEND = "sentence_transformers"
        logger.info("[Embeddings] 使用 sentence-transformers 后端")
        return
    except ImportError:
        pass
    
    # 尝试 scikit-learn TF-IDF
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        _vectorizer = TfidfVectorizer(max_features=512, ngram_range=(1, 2))
        _EMBEDDING_BACKEND = "tfidf"
        logger.info("[Embeddings] 使用 TF-IDF 后端")
        return
    except ImportError:
        pass
    
    # 回退到关键词方法
    _EMBEDDING_BACKEND = "keywords"
    logger.info("[Embeddings] 使用关键词后端（建议安装 sentence-transformers 或 scikit-learn）")


def get_embedding(text: str) -> List[float]:
    """
    获取文本的向量表示
    
    Args:
        text: 输入文本
        
    Returns:
        向量列表
    """
    _init_backend()
    
    if _EMBEDDING_BACKEND == "sentence_transformers":
        return _model.encode(text).tolist()
    
    elif _EMBEDDING_BACKEND == "tfidf":
        # TF-IDF 需要先 fit，这里使用单文本的简化方法
        try:
            vec = _vectorizer.fit_transform([text])
            return vec.toarray()[0].tolist()
        except:
            return _keyword_embedding(text)
    
    else:
        return _keyword_embedding(text)


def _keyword_embedding(text: str, dim: int = 128) -> List[float]:
    """
    基于关键词的简单嵌入
    
    使用关键词哈希生成固定维度的向量
    """
    # 提取关键词
    words = re.findall(r'\b\w+\b', text.lower())
    
    # 生成向量
    vector = [0.0] * dim
    
    for word in words:
        # 使用哈希确定位置和值
        h = int(hashlib.md5(word.encode()).hexdigest(), 16)
        pos = h % dim
        val = ((h >> 8) % 100) / 100.0
        vector[pos] += val
    
    # 归一化
    norm = sum(v * v for v in vector) ** 0.5
    if norm > 0:
        vector = [v / norm for v in vector]
    
    return vector


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    计算余弦相似度
    
    Args:
        vec1: 向量1
        vec2: 向量2
        
    Returns:
        相似度 (0-1)
    """
    if not vec1 or not vec2:
        return 0.0
    
    # 确保维度一致
    min_len = min(len(vec1), len(vec2))
    vec1 = vec1[:min_len]
    vec2 = vec2[:min_len]
    
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(v * v for v in vec1) ** 0.5
    norm2 = sum(v * v for v in vec2) ** 0.5
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot / (norm1 * norm2)


def embedding_to_json(embedding: List[float]) -> str:
    """将向量序列化为 JSON"""
    return json.dumps(embedding)


def json_to_embedding(json_str: str) -> List[float]:
    """从 JSON 反序列化向量"""
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except:
        return []


def get_backend_info() -> Dict[str, Any]:
    """获取当前后端信息"""
    _init_backend()
    return {
        "backend": _EMBEDDING_BACKEND,
        "dimension": 384 if _EMBEDDING_BACKEND == "sentence_transformers" else 
                     512 if _EMBEDDING_BACKEND == "tfidf" else 128
    }


class SemanticIndex:
    """
    语义索引
    
    用于高效的语义检索
    """
    
    def __init__(self):
        self._items: List[Tuple[int, str, List[float]]] = []  # (id, text, embedding)
    
    def add(self, item_id: int, text: str, embedding: Optional[List[float]] = None) -> None:
        """添加项目"""
        if embedding is None:
            embedding = get_embedding(text)
        self._items.append((item_id, text, embedding))
    
    def search(self, query: str, top_k: int = 5, threshold: float = 0.3) -> List[Tuple[int, float]]:
        """
        语义搜索
        
        Args:
            query: 查询文本
            top_k: 返回数量
            threshold: 相似度阈值
            
        Returns:
            [(item_id, similarity), ...]
        """
        query_embedding = get_embedding(query)
        
        results = []
        for item_id, text, embedding in self._items:
            sim = cosine_similarity(query_embedding, embedding)
            if sim >= threshold:
                results.append((item_id, sim))
        
        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def clear(self) -> None:
        """清空索引"""
        self._items = []
    
    def __len__(self) -> int:
        return len(self._items)
