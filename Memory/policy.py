"""
Memory Policy - 记忆策略

负责:
- 记忆保留策略
- 自动清理规则
- 容量管理
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum


class RetentionPolicy(Enum):
    """保留策略"""
    KEEP_ALL = "keep_all"
    TTL = "ttl"
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    SIZE_LIMIT = "size_limit"


@dataclass
class PolicyRule:
    """策略规则"""
    name: str
    policy: RetentionPolicy
    config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "policy": self.policy.value,
            "config": self.config,
            "enabled": self.enabled,
            "priority": self.priority
        }


class MemoryPolicy:
    """
    记忆策略管理器
    
    管理记忆的保留和清理策略
    """
    
    DEFAULT_TTL = 86400  # 24 小时
    DEFAULT_MAX_SIZE = 10000
    
    def __init__(self):
        self._rules: Dict[str, PolicyRule] = {}
        self._cleanup_callbacks: List[Callable] = []
        
        self._setup_default_rules()
    
    def _setup_default_rules(self) -> None:
        """设置默认规则"""
        # 短期记忆 TTL 规则
        self.add_rule(PolicyRule(
            name="short_term_ttl",
            policy=RetentionPolicy.TTL,
            config={
                "ttl_seconds": 3600,  # 1 小时
                "target": "short_term"
            },
            priority=10
        ))
        
        # 短期记忆 LRU 规则
        self.add_rule(PolicyRule(
            name="short_term_lru",
            policy=RetentionPolicy.LRU,
            config={
                "max_items": 1000,
                "target": "short_term"
            },
            priority=5
        ))
        
        # 长期记忆大小限制
        self.add_rule(PolicyRule(
            name="long_term_size",
            policy=RetentionPolicy.SIZE_LIMIT,
            config={
                "max_items": 10000,
                "target": "long_term"
            },
            priority=5
        ))
        
        # 向量存储大小限制
        self.add_rule(PolicyRule(
            name="vector_size",
            policy=RetentionPolicy.SIZE_LIMIT,
            config={
                "max_items": 50000,
                "target": "vector_store"
            },
            priority=5
        ))
    
    def add_rule(self, rule: PolicyRule) -> None:
        """添加规则"""
        self._rules[rule.name] = rule
    
    def remove_rule(self, name: str) -> bool:
        """移除规则"""
        if name in self._rules:
            del self._rules[name]
            return True
        return False
    
    def enable_rule(self, name: str) -> bool:
        """启用规则"""
        if name in self._rules:
            self._rules[name].enabled = True
            return True
        return False
    
    def disable_rule(self, name: str) -> bool:
        """禁用规则"""
        if name in self._rules:
            self._rules[name].enabled = False
            return True
        return False
    
    def get_rules(self, target: Optional[str] = None) -> List[PolicyRule]:
        """
        获取规则列表
        
        Args:
            target: 目标类型过滤
            
        Returns:
            规则列表
        """
        rules = list(self._rules.values())
        
        if target:
            rules = [r for r in rules if r.config.get("target") == target]
        
        # 按优先级排序
        rules.sort(key=lambda x: x.priority, reverse=True)
        
        return rules
    
    def apply(
        self,
        memory,
        target: str
    ) -> Dict[str, Any]:
        """
        应用策略
        
        Args:
            memory: 记忆存储实例
            target: 目标类型
            
        Returns:
            应用结果
        """
        results = {
            "applied_rules": [],
            "items_removed": 0,
            "errors": []
        }
        
        rules = self.get_rules(target)
        
        for rule in rules:
            if not rule.enabled:
                continue
            
            try:
                removed = self._apply_rule(memory, rule)
                results["items_removed"] += removed
                results["applied_rules"].append(rule.name)
            except Exception as e:
                results["errors"].append({
                    "rule": rule.name,
                    "error": str(e)
                })
        
        # 触发清理回调
        for callback in self._cleanup_callbacks:
            try:
                callback(results)
            except Exception:
                pass
        
        return results
    
    def _apply_rule(self, memory, rule: PolicyRule) -> int:
        """
        应用单个规则
        
        Returns:
            移除的项目数
        """
        if rule.policy == RetentionPolicy.TTL:
            return self._apply_ttl(memory, rule.config)
        elif rule.policy == RetentionPolicy.LRU:
            return self._apply_lru(memory, rule.config)
        elif rule.policy == RetentionPolicy.LFU:
            return self._apply_lfu(memory, rule.config)
        elif rule.policy == RetentionPolicy.FIFO:
            return self._apply_fifo(memory, rule.config)
        elif rule.policy == RetentionPolicy.SIZE_LIMIT:
            return self._apply_size_limit(memory, rule.config)
        
        return 0
    
    def _apply_ttl(self, memory, config: Dict[str, Any]) -> int:
        """应用 TTL 策略"""
        # TTL 清理通常由内存自身处理
        if hasattr(memory, '_cleanup_expired'):
            return memory._cleanup_expired()
        return 0
    
    def _apply_lru(self, memory, config: Dict[str, Any]) -> int:
        """应用 LRU 策略"""
        max_items = config.get("max_items", self.DEFAULT_MAX_SIZE)
        
        if hasattr(memory, 'size') and memory.size() > max_items:
            if hasattr(memory, '_evict_oldest'):
                memory._evict_oldest()
                return memory.size() - max_items if memory.size() > max_items else 0
        
        return 0
    
    def _apply_lfu(self, memory, config: Dict[str, Any]) -> int:
        """应用 LFU 策略"""
        # LFU 需要访问频率追踪
        return 0
    
    def _apply_fifo(self, memory, config: Dict[str, Any]) -> int:
        """应用 FIFO 策略"""
        max_items = config.get("max_items", self.DEFAULT_MAX_SIZE)
        
        if hasattr(memory, 'size') and hasattr(memory, 'keys'):
            current_size = memory.size()
            if current_size > max_items:
                to_remove = current_size - max_items
                keys = memory.keys()[:to_remove]
                for key in keys:
                    memory.delete(key)
                return to_remove
        
        return 0
    
    def _apply_size_limit(self, memory, config: Dict[str, Any]) -> int:
        """应用大小限制策略"""
        return self._apply_lru(memory, config)
    
    def add_cleanup_callback(self, callback: Callable) -> None:
        """添加清理回调"""
        self._cleanup_callbacks.append(callback)
    
    def should_store(
        self,
        key: str,
        value: Any,
        target: str
    ) -> tuple[bool, Optional[str]]:
        """
        检查是否应该存储
        
        Args:
            key: 键
            value: 值
            target: 目标类型
            
        Returns:
            (是否允许, 原因)
        """
        # 可以添加存储前检查逻辑
        return True, None
    
    def list_rules(self) -> List[Dict[str, Any]]:
        """列出所有规则"""
        return [r.to_dict() for r in self._rules.values()]
