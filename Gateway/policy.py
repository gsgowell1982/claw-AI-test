"""
Policy - 策略控制

负责:
- 工具调用次数限制 (n=5)
- 速率限制
- 权限检查
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading


class PolicyType(Enum):
    """策略类型"""
    RATE_LIMIT = "rate_limit"
    CALL_LIMIT = "call_limit"
    PERMISSION = "permission"
    CONTENT = "content"


@dataclass
class PolicyRule:
    """策略规则"""
    name: str
    policy_type: PolicyType
    config: Dict[str, Any]
    enabled: bool = True
    description: str = ""


@dataclass
class PolicyViolation:
    """策略违规"""
    rule_name: str
    policy_type: PolicyType
    message: str
    timestamp: datetime = field(default_factory=datetime.now)


class Policy:
    """
    策略控制器
    
    管理各种策略限制
    """
    
    # 默认工具调用限制
    DEFAULT_TOOL_CALL_LIMIT = 5
    
    # 默认速率限制(每分钟请求数)
    DEFAULT_RATE_LIMIT = 60
    
    def __init__(
        self,
        tool_call_limit: int = DEFAULT_TOOL_CALL_LIMIT,
        rate_limit: int = DEFAULT_RATE_LIMIT
    ):
        self.tool_call_limit = tool_call_limit
        self.rate_limit = rate_limit
        
        self._rules: Dict[str, PolicyRule] = {}
        self._call_counters: Dict[str, Dict[str, int]] = {}
        self._rate_counters: Dict[str, List[datetime]] = {}
        self._violations: List[PolicyViolation] = []
        self._lock = threading.Lock()
        
        self._setup_default_rules()
    
    def _setup_default_rules(self) -> None:
        """设置默认规则"""
        # 工具调用限制规则
        self.add_rule(PolicyRule(
            name="tool_call_limit",
            policy_type=PolicyType.CALL_LIMIT,
            config={
                "max_calls": self.tool_call_limit,
                "window": "session"  # 每会话
            },
            description=f"限制每个会话最多调用 {self.tool_call_limit} 次工具"
        ))
        
        # 速率限制规则
        self.add_rule(PolicyRule(
            name="rate_limit",
            policy_type=PolicyType.RATE_LIMIT,
            config={
                "max_requests": self.rate_limit,
                "window_seconds": 60
            },
            description=f"限制每分钟最多 {self.rate_limit} 次请求"
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
    
    def check_tool_call(
        self,
        session_id: str,
        tool_name: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        检查工具调用是否允许
        
        Args:
            session_id: 会话 ID
            tool_name: 工具名称
            
        Returns:
            (是否允许, 错误信息)
        """
        rule = self._rules.get("tool_call_limit")
        if not rule or not rule.enabled:
            return True, None
        
        with self._lock:
            if session_id not in self._call_counters:
                self._call_counters[session_id] = {}
            
            counters = self._call_counters[session_id]
            current_count = counters.get("_total", 0)
            
            max_calls = rule.config.get("max_calls", self.tool_call_limit)
            
            if current_count >= max_calls:
                violation = PolicyViolation(
                    rule_name=rule.name,
                    policy_type=rule.policy_type,
                    message=f"Tool call limit exceeded: {current_count}/{max_calls}"
                )
                self._violations.append(violation)
                return False, violation.message
            
            return True, None
    
    def record_tool_call(
        self,
        session_id: str,
        tool_name: str
    ) -> None:
        """记录工具调用"""
        with self._lock:
            if session_id not in self._call_counters:
                self._call_counters[session_id] = {}
            
            counters = self._call_counters[session_id]
            counters["_total"] = counters.get("_total", 0) + 1
            counters[tool_name] = counters.get(tool_name, 0) + 1
    
    def check_rate_limit(self, identifier: str) -> tuple[bool, Optional[str]]:
        """
        检查速率限制
        
        Args:
            identifier: 标识符(如 IP 或用户 ID)
            
        Returns:
            (是否允许, 错误信息)
        """
        rule = self._rules.get("rate_limit")
        if not rule or not rule.enabled:
            return True, None
        
        now = datetime.now()
        window_seconds = rule.config.get("window_seconds", 60)
        max_requests = rule.config.get("max_requests", self.rate_limit)
        
        with self._lock:
            if identifier not in self._rate_counters:
                self._rate_counters[identifier] = []
            
            # 清理过期记录
            cutoff = now - timedelta(seconds=window_seconds)
            self._rate_counters[identifier] = [
                t for t in self._rate_counters[identifier]
                if t > cutoff
            ]
            
            current_count = len(self._rate_counters[identifier])
            
            if current_count >= max_requests:
                violation = PolicyViolation(
                    rule_name=rule.name,
                    policy_type=rule.policy_type,
                    message=f"Rate limit exceeded: {current_count}/{max_requests} per {window_seconds}s"
                )
                self._violations.append(violation)
                return False, violation.message
            
            return True, None
    
    def record_request(self, identifier: str) -> None:
        """记录请求"""
        with self._lock:
            if identifier not in self._rate_counters:
                self._rate_counters[identifier] = []
            self._rate_counters[identifier].append(datetime.now())
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """获取会话统计"""
        counters = self._call_counters.get(session_id, {})
        return {
            "session_id": session_id,
            "total_tool_calls": counters.get("_total", 0),
            "tool_call_limit": self.tool_call_limit,
            "remaining_calls": max(0, self.tool_call_limit - counters.get("_total", 0)),
            "tool_breakdown": {
                k: v for k, v in counters.items()
                if k != "_total"
            }
        }
    
    def reset_session(self, session_id: str) -> None:
        """重置会话计数"""
        with self._lock:
            if session_id in self._call_counters:
                del self._call_counters[session_id]
    
    def get_violations(
        self,
        limit: int = 100,
        policy_type: Optional[PolicyType] = None
    ) -> List[Dict[str, Any]]:
        """获取违规记录"""
        violations = self._violations
        
        if policy_type:
            violations = [v for v in violations if v.policy_type == policy_type]
        
        return [
            {
                "rule_name": v.rule_name,
                "policy_type": v.policy_type.value,
                "message": v.message,
                "timestamp": v.timestamp.isoformat()
            }
            for v in violations[-limit:]
        ]
    
    def list_rules(self) -> List[Dict[str, Any]]:
        """列出所有规则"""
        return [
            {
                "name": r.name,
                "type": r.policy_type.value,
                "enabled": r.enabled,
                "config": r.config,
                "description": r.description
            }
            for r in self._rules.values()
        ]
