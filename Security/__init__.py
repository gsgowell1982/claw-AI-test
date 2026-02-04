# Security Layer - 安全控制层
"""
Security 层负责:
- 认证与授权
- 访问控制
- 安全策略
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import secrets


class AuthLevel(Enum):
    """认证级别"""
    ANONYMOUS = "anonymous"
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


@dataclass
class AuthToken:
    """认证令牌"""
    token: str
    user_id: str
    auth_level: AuthLevel
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_valid(self) -> bool:
        """检查令牌是否有效"""
        if self.expires_at is None:
            return True
        return datetime.now() < self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token[:8] + "...",  # 部分遮盖
            "user_id": self.user_id,
            "auth_level": self.auth_level.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }


class SecurityManager:
    """
    安全管理器
    
    管理认证和授权
    """
    
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or secrets.token_hex(32)
        self._tokens: Dict[str, AuthToken] = {}
        self._users: Dict[str, Dict[str, Any]] = {}
    
    def create_token(
        self,
        user_id: str,
        auth_level: AuthLevel = AuthLevel.USER,
        expire_minutes: int = 60
    ) -> AuthToken:
        """
        创建认证令牌
        
        Args:
            user_id: 用户 ID
            auth_level: 认证级别
            expire_minutes: 过期时间(分钟)
            
        Returns:
            认证令牌
        """
        token_str = secrets.token_urlsafe(32)
        
        token = AuthToken(
            token=token_str,
            user_id=user_id,
            auth_level=auth_level,
            expires_at=datetime.now() + timedelta(minutes=expire_minutes)
        )
        
        self._tokens[token_str] = token
        return token
    
    def validate_token(self, token_str: str) -> Optional[AuthToken]:
        """
        验证令牌
        
        Args:
            token_str: 令牌字符串
            
        Returns:
            有效的令牌,或 None
        """
        token = self._tokens.get(token_str)
        
        if token is None:
            return None
        
        if not token.is_valid():
            del self._tokens[token_str]
            return None
        
        return token
    
    def revoke_token(self, token_str: str) -> bool:
        """撤销令牌"""
        if token_str in self._tokens:
            del self._tokens[token_str]
            return True
        return False
    
    def hash_password(self, password: str) -> str:
        """哈希密码"""
        salted = password + self.secret_key
        return hashlib.sha256(salted.encode()).hexdigest()
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """验证密码"""
        return self.hash_password(password) == hashed
    
    def check_permission(
        self,
        token: AuthToken,
        required_level: AuthLevel
    ) -> bool:
        """
        检查权限
        
        Args:
            token: 认证令牌
            required_level: 要求的权限级别
            
        Returns:
            是否有权限
        """
        level_order = {
            AuthLevel.ANONYMOUS: 0,
            AuthLevel.USER: 1,
            AuthLevel.ADMIN: 2,
            AuthLevel.SYSTEM: 3
        }
        
        return level_order.get(token.auth_level, 0) >= level_order.get(required_level, 0)
    
    def cleanup_expired(self) -> int:
        """清理过期令牌"""
        expired = [
            token_str for token_str, token in self._tokens.items()
            if not token.is_valid()
        ]
        
        for token_str in expired:
            del self._tokens[token_str]
        
        return len(expired)


# 全局实例
_security_manager: Optional[SecurityManager] = None


def get_security_manager() -> SecurityManager:
    """获取全局安全管理器"""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager()
    return _security_manager


__all__ = [
    'AuthLevel',
    'AuthToken',
    'SecurityManager',
    'get_security_manager'
]
