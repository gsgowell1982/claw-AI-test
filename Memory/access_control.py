"""
Memory Access Control - 记忆访问控制

负责:
- 访问权限管理
- 读写控制
- 审计日志
"""

from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading


class Permission(Enum):
    """权限类型"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"


class AccessLevel(Enum):
    """访问级别"""
    PUBLIC = "public"
    PRIVATE = "private"
    PROTECTED = "protected"
    SYSTEM = "system"


@dataclass
class AccessRule:
    """访问规则"""
    name: str
    subject: str  # 用户或角色
    permissions: Set[Permission]
    resource_pattern: str = "*"
    access_level: AccessLevel = AccessLevel.PRIVATE
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "subject": self.subject,
            "permissions": [p.value for p in self.permissions],
            "resource_pattern": self.resource_pattern,
            "access_level": self.access_level.value
        }


@dataclass
class AccessLog:
    """访问日志"""
    subject: str
    action: Permission
    resource: str
    allowed: bool
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject": self.subject,
            "action": self.action.value,
            "resource": self.resource,
            "allowed": self.allowed,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class MemoryAccessControl:
    """
    记忆访问控制器
    
    管理记忆的访问权限
    """
    
    def __init__(self, enable_audit: bool = True):
        self.enable_audit = enable_audit
        
        self._rules: Dict[str, AccessRule] = {}
        self._audit_log: List[AccessLog] = []
        self._lock = threading.Lock()
        
        self._setup_default_rules()
    
    def _setup_default_rules(self) -> None:
        """设置默认规则"""
        # 系统管理员规则
        self.add_rule(AccessRule(
            name="admin_all",
            subject="admin",
            permissions={Permission.READ, Permission.WRITE, Permission.DELETE, Permission.ADMIN},
            resource_pattern="*",
            access_level=AccessLevel.SYSTEM
        ))
        
        # 默认用户规则
        self.add_rule(AccessRule(
            name="user_default",
            subject="user",
            permissions={Permission.READ, Permission.WRITE},
            resource_pattern="user:*",
            access_level=AccessLevel.PRIVATE
        ))
        
        # 公共读取规则
        self.add_rule(AccessRule(
            name="public_read",
            subject="*",
            permissions={Permission.READ},
            resource_pattern="public:*",
            access_level=AccessLevel.PUBLIC
        ))
    
    def add_rule(self, rule: AccessRule) -> None:
        """添加规则"""
        with self._lock:
            self._rules[rule.name] = rule
    
    def remove_rule(self, name: str) -> bool:
        """移除规则"""
        with self._lock:
            if name in self._rules:
                del self._rules[name]
                return True
            return False
    
    def check_access(
        self,
        subject: str,
        permission: Permission,
        resource: str
    ) -> bool:
        """
        检查访问权限
        
        Args:
            subject: 主体(用户或角色)
            permission: 请求的权限
            resource: 资源
            
        Returns:
            是否允许
        """
        allowed = False
        
        for rule in self._rules.values():
            if self._match_rule(rule, subject, permission, resource):
                allowed = True
                break
        
        # 记录审计日志
        if self.enable_audit:
            self._log_access(subject, permission, resource, allowed)
        
        return allowed
    
    def _match_rule(
        self,
        rule: AccessRule,
        subject: str,
        permission: Permission,
        resource: str
    ) -> bool:
        """检查规则是否匹配"""
        # 检查主体
        if rule.subject != "*" and rule.subject != subject:
            return False
        
        # 检查权限
        if permission not in rule.permissions:
            return False
        
        # 检查资源模式
        import fnmatch
        if not fnmatch.fnmatch(resource, rule.resource_pattern):
            return False
        
        return True
    
    def _log_access(
        self,
        subject: str,
        permission: Permission,
        resource: str,
        allowed: bool
    ) -> None:
        """记录访问日志"""
        log = AccessLog(
            subject=subject,
            action=permission,
            resource=resource,
            allowed=allowed
        )
        
        with self._lock:
            self._audit_log.append(log)
            
            # 限制日志数量
            if len(self._audit_log) > 10000:
                self._audit_log = self._audit_log[-5000:]
    
    def grant(
        self,
        subject: str,
        permission: Permission,
        resource_pattern: str = "*"
    ) -> str:
        """
        授予权限
        
        Args:
            subject: 主体
            permission: 权限
            resource_pattern: 资源模式
            
        Returns:
            规则名称
        """
        import uuid
        rule_name = f"grant_{uuid.uuid4().hex[:8]}"
        
        # 查找现有规则
        for rule in self._rules.values():
            if rule.subject == subject and rule.resource_pattern == resource_pattern:
                rule.permissions.add(permission)
                return rule.name
        
        # 创建新规则
        self.add_rule(AccessRule(
            name=rule_name,
            subject=subject,
            permissions={permission},
            resource_pattern=resource_pattern
        ))
        
        return rule_name
    
    def revoke(
        self,
        subject: str,
        permission: Permission,
        resource_pattern: str = "*"
    ) -> bool:
        """
        撤销权限
        
        Args:
            subject: 主体
            permission: 权限
            resource_pattern: 资源模式
            
        Returns:
            是否成功
        """
        with self._lock:
            for rule in self._rules.values():
                if rule.subject == subject and rule.resource_pattern == resource_pattern:
                    rule.permissions.discard(permission)
                    return True
        
        return False
    
    def get_permissions(
        self,
        subject: str,
        resource: str
    ) -> Set[Permission]:
        """
        获取主体对资源的所有权限
        
        Args:
            subject: 主体
            resource: 资源
            
        Returns:
            权限集合
        """
        permissions = set()
        
        for rule in self._rules.values():
            if self._match_rule(rule, subject, Permission.READ, resource):
                permissions.update(rule.permissions)
        
        return permissions
    
    def get_audit_log(
        self,
        subject: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取审计日志
        
        Args:
            subject: 过滤主体
            resource: 过滤资源
            limit: 返回数量
            
        Returns:
            日志列表
        """
        logs = self._audit_log
        
        if subject:
            logs = [l for l in logs if l.subject == subject]
        
        if resource:
            logs = [l for l in logs if l.resource == resource]
        
        return [l.to_dict() for l in logs[-limit:]]
    
    def list_rules(self) -> List[Dict[str, Any]]:
        """列出所有规则"""
        return [r.to_dict() for r in self._rules.values()]
    
    def clear_audit_log(self) -> None:
        """清空审计日志"""
        with self._lock:
            self._audit_log.clear()
