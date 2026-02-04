"""
Query Module - 查询模块

负责:
- 统一查询接口
- 查询优化
- 结果聚合
"""

from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, field
from enum import Enum


class QueryType(Enum):
    """查询类型"""
    EXACT = "exact"
    PATTERN = "pattern"
    SEMANTIC = "semantic"
    RANGE = "range"
    COMPOSITE = "composite"


@dataclass
class QueryCondition:
    """查询条件"""
    field: str
    operator: str  # 'eq', 'ne', 'gt', 'lt', 'gte', 'lte', 'contains', 'startswith', 'endswith'
    value: Any
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value
        }


@dataclass
class Query:
    """查询定义"""
    query_type: QueryType
    conditions: List[QueryCondition] = field(default_factory=list)
    text: Optional[str] = None
    limit: int = 100
    offset: int = 0
    sort_by: Optional[str] = None
    sort_order: str = "asc"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query_type": self.query_type.value,
            "conditions": [c.to_dict() for c in self.conditions],
            "text": self.text,
            "limit": self.limit,
            "offset": self.offset,
            "sort_by": self.sort_by,
            "sort_order": self.sort_order
        }


@dataclass
class QueryResult:
    """查询结果"""
    items: List[Dict[str, Any]]
    total: int
    query: Query
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "query": self.query.to_dict(),
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata
        }


class QueryModule:
    """
    查询模块
    
    提供统一的记忆查询接口
    """
    
    OPERATORS = {
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "gt": lambda a, b: a > b,
        "lt": lambda a, b: a < b,
        "gte": lambda a, b: a >= b,
        "lte": lambda a, b: a <= b,
        "contains": lambda a, b: b in a if isinstance(a, (str, list)) else False,
        "startswith": lambda a, b: a.startswith(b) if isinstance(a, str) else False,
        "endswith": lambda a, b: a.endswith(b) if isinstance(a, str) else False
    }
    
    def __init__(self):
        self._short_term = None
        self._long_term = None
        self._vector_store = None
    
    def set_short_term_memory(self, memory) -> None:
        """设置短期记忆"""
        self._short_term = memory
    
    def set_long_term_memory(self, memory) -> None:
        """设置长期记忆"""
        self._long_term = memory
    
    def set_vector_store(self, store) -> None:
        """设置向量存储"""
        self._vector_store = store
    
    def query(self, query: Query) -> QueryResult:
        """
        执行查询
        
        Args:
            query: 查询定义
            
        Returns:
            查询结果
        """
        import time
        start_time = time.time()
        
        if query.query_type == QueryType.EXACT:
            items = self._query_exact(query)
        elif query.query_type == QueryType.PATTERN:
            items = self._query_pattern(query)
        elif query.query_type == QueryType.SEMANTIC:
            items = self._query_semantic(query)
        elif query.query_type == QueryType.RANGE:
            items = self._query_range(query)
        elif query.query_type == QueryType.COMPOSITE:
            items = self._query_composite(query)
        else:
            items = []
        
        # 应用条件过滤
        if query.conditions:
            items = self._apply_conditions(items, query.conditions)
        
        total = len(items)
        
        # 排序
        if query.sort_by:
            items = self._sort_items(items, query.sort_by, query.sort_order)
        
        # 分页
        items = items[query.offset:query.offset + query.limit]
        
        execution_time = (time.time() - start_time) * 1000
        
        return QueryResult(
            items=items,
            total=total,
            query=query,
            execution_time_ms=execution_time
        )
    
    def _query_exact(self, query: Query) -> List[Dict[str, Any]]:
        """精确查询"""
        items = []
        
        if self._short_term:
            for key in self._short_term.keys():
                value = self._short_term.get(key)
                items.append({"key": key, "value": value, "source": "short_term"})
        
        if self._long_term:
            for key in self._long_term.keys():
                value = self._long_term.get(key)
                items.append({"key": key, "value": value, "source": "long_term"})
        
        return items
    
    def _query_pattern(self, query: Query) -> List[Dict[str, Any]]:
        """模式匹配查询"""
        items = []
        pattern = query.text or "*"
        
        if self._short_term:
            for key in self._short_term.keys(pattern):
                value = self._short_term.get(key)
                items.append({"key": key, "value": value, "source": "short_term"})
        
        if self._long_term:
            for key in self._long_term.keys(pattern):
                value = self._long_term.get(key)
                items.append({"key": key, "value": value, "source": "long_term"})
        
        return items
    
    def _query_semantic(self, query: Query) -> List[Dict[str, Any]]:
        """语义查询"""
        items = []
        
        if self._vector_store and query.text:
            results = self._vector_store.search_by_text(
                query.text,
                limit=query.limit
            )
            
            for result in results:
                items.append({
                    "key": result["id"],
                    "value": result["content"],
                    "similarity": result["similarity"],
                    "source": "vector_store"
                })
        
        return items
    
    def _query_range(self, query: Query) -> List[Dict[str, Any]]:
        """范围查询"""
        # 基于条件的范围查询
        return self._query_exact(query)
    
    def _query_composite(self, query: Query) -> List[Dict[str, Any]]:
        """组合查询"""
        # 合并所有来源
        items = self._query_exact(query)
        
        if query.text and self._vector_store:
            semantic_items = self._query_semantic(query)
            items.extend(semantic_items)
        
        return items
    
    def _apply_conditions(
        self,
        items: List[Dict[str, Any]],
        conditions: List[QueryCondition]
    ) -> List[Dict[str, Any]]:
        """应用条件过滤"""
        filtered = []
        
        for item in items:
            match = True
            
            for condition in conditions:
                value = item.get(condition.field)
                operator_func = self.OPERATORS.get(condition.operator)
                
                if operator_func and not operator_func(value, condition.value):
                    match = False
                    break
            
            if match:
                filtered.append(item)
        
        return filtered
    
    def _sort_items(
        self,
        items: List[Dict[str, Any]],
        sort_by: str,
        sort_order: str
    ) -> List[Dict[str, Any]]:
        """排序"""
        reverse = sort_order.lower() == "desc"
        
        return sorted(
            items,
            key=lambda x: x.get(sort_by, ""),
            reverse=reverse
        )
    
    def search(
        self,
        text: str,
        query_type: QueryType = QueryType.SEMANTIC,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        简化搜索接口
        
        Args:
            text: 搜索文本
            query_type: 查询类型
            limit: 返回数量
            
        Returns:
            结果列表
        """
        query = Query(
            query_type=query_type,
            text=text,
            limit=limit
        )
        
        result = self.query(query)
        return result.items
