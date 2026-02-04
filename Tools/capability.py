"""
Capability Policy - 能力策略控制

负责:
- 工具能力限制
- 合规性检查
- 安全边界定义
"""

from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class CapabilityLevel(Enum):
    """能力级别"""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    EXECUTE = "execute"
    ADMIN = "admin"


class RiskLevel(Enum):
    """风险级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Capability:
    """能力定义"""
    name: str
    level: CapabilityLevel
    risk_level: RiskLevel = RiskLevel.LOW
    description: str = ""
    requires_approval: bool = False
    allowed_contexts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level.value,
            "risk_level": self.risk_level.value,
            "description": self.description,
            "requires_approval": self.requires_approval,
            "allowed_contexts": self.allowed_contexts
        }


@dataclass
class CapabilityCheckResult:
    """能力检查结果"""
    allowed: bool
    capability: str
    reason: Optional[str] = None
    requires_approval: bool = False


class CapabilityPolicy:
    """
    能力策略管理器
    
    管理工具的能力限制和合规性
    """
    
    # 预定义的危险操作
    DANGEROUS_OPERATIONS = {
        "file_delete", "file_write", "system_command",
        "network_request", "database_modify", "process_kill"
    }
    
    def __init__(self):
        self._capabilities: Dict[str, Capability] = {}
        self._tool_capabilities: Dict[str, Set[str]] = {}
        self._blocked_capabilities: Set[str] = set()
        self._approval_queue: List[Dict[str, Any]] = []
        
        self._setup_default_capabilities()
    
    def _setup_default_capabilities(self) -> None:
        """设置默认能力"""
        # 文件操作
        self.define_capability(Capability(
            name="file_read",
            level=CapabilityLevel.READ_ONLY,
            risk_level=RiskLevel.LOW,
            description="读取文件内容"
        ))
        
        self.define_capability(Capability(
            name="file_write",
            level=CapabilityLevel.READ_WRITE,
            risk_level=RiskLevel.MEDIUM,
            description="写入文件内容",
            requires_approval=True
        ))
        
        self.define_capability(Capability(
            name="file_delete",
            level=CapabilityLevel.READ_WRITE,
            risk_level=RiskLevel.HIGH,
            description="删除文件",
            requires_approval=True
        ))
        
        # 网络操作
        self.define_capability(Capability(
            name="network_request",
            level=CapabilityLevel.EXECUTE,
            risk_level=RiskLevel.MEDIUM,
            description="发起网络请求"
        ))
        
        # 系统操作
        self.define_capability(Capability(
            name="system_command",
            level=CapabilityLevel.EXECUTE,
            risk_level=RiskLevel.CRITICAL,
            description="执行系统命令",
            requires_approval=True
        ))
        
        # 数据库操作
        self.define_capability(Capability(
            name="database_read",
            level=CapabilityLevel.READ_ONLY,
            risk_level=RiskLevel.LOW,
            description="读取数据库"
        ))
        
        self.define_capability(Capability(
            name="database_modify",
            level=CapabilityLevel.READ_WRITE,
            risk_level=RiskLevel.HIGH,
            description="修改数据库",
            requires_approval=True
        ))
    
    def define_capability(self, capability: Capability) -> None:
        """定义能力"""
        self._capabilities[capability.name] = capability
    
    def assign_capability(self, tool_name: str, capability_name: str) -> bool:
        """
        为工具分配能力
        
        Args:
            tool_name: 工具名称
            capability_name: 能力名称
            
        Returns:
            是否成功
        """
        if capability_name not in self._capabilities:
            return False
        
        if tool_name not in self._tool_capabilities:
            self._tool_capabilities[tool_name] = set()
        
        self._tool_capabilities[tool_name].add(capability_name)
        return True
    
    def revoke_capability(self, tool_name: str, capability_name: str) -> bool:
        """撤销工具能力"""
        if tool_name in self._tool_capabilities:
            self._tool_capabilities[tool_name].discard(capability_name)
            return True
        return False
    
    def check_capability(
        self,
        tool_name: str,
        capability_name: str,
        context: Optional[str] = None
    ) -> CapabilityCheckResult:
        """
        检查工具能力
        
        Args:
            tool_name: 工具名称
            capability_name: 能力名称
            context: 执行上下文
            
        Returns:
            检查结果
        """
        # 检查能力是否被全局阻止
        if capability_name in self._blocked_capabilities:
            return CapabilityCheckResult(
                allowed=False,
                capability=capability_name,
                reason=f"Capability '{capability_name}' is globally blocked"
            )
        
        # 检查能力是否存在
        if capability_name not in self._capabilities:
            return CapabilityCheckResult(
                allowed=False,
                capability=capability_name,
                reason=f"Unknown capability: {capability_name}"
            )
        
        capability = self._capabilities[capability_name]
        
        # 检查工具是否有此能力
        tool_caps = self._tool_capabilities.get(tool_name, set())
        if capability_name not in tool_caps:
            return CapabilityCheckResult(
                allowed=False,
                capability=capability_name,
                reason=f"Tool '{tool_name}' does not have capability '{capability_name}'"
            )
        
        # 检查上下文限制
        if capability.allowed_contexts and context:
            if context not in capability.allowed_contexts:
                return CapabilityCheckResult(
                    allowed=False,
                    capability=capability_name,
                    reason=f"Capability not allowed in context: {context}"
                )
        
        return CapabilityCheckResult(
            allowed=True,
            capability=capability_name,
            requires_approval=capability.requires_approval
        )
    
    def block_capability(self, capability_name: str) -> None:
        """全局阻止能力"""
        self._blocked_capabilities.add(capability_name)
    
    def unblock_capability(self, capability_name: str) -> None:
        """解除阻止"""
        self._blocked_capabilities.discard(capability_name)
    
    def get_tool_capabilities(self, tool_name: str) -> List[Dict[str, Any]]:
        """获取工具能力列表"""
        cap_names = self._tool_capabilities.get(tool_name, set())
        return [
            self._capabilities[name].to_dict()
            for name in cap_names
            if name in self._capabilities
        ]
    
    def list_capabilities(self) -> List[Dict[str, Any]]:
        """列出所有能力"""
        return [c.to_dict() for c in self._capabilities.values()]
    
    def request_approval(
        self,
        tool_name: str,
        capability_name: str,
        reason: str
    ) -> str:
        """
        请求审批
        
        Returns:
            审批请求 ID
        """
        import uuid
        request_id = str(uuid.uuid4())
        
        self._approval_queue.append({
            "id": request_id,
            "tool_name": tool_name,
            "capability_name": capability_name,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "status": "pending"
        })
        
        return request_id
    
    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """获取待审批列表"""
        return [a for a in self._approval_queue if a["status"] == "pending"]
    
    def approve(self, request_id: str) -> bool:
        """批准请求"""
        for approval in self._approval_queue:
            if approval["id"] == request_id:
                approval["status"] = "approved"
                return True
        return False
    
    def deny(self, request_id: str) -> bool:
        """拒绝请求"""
        for approval in self._approval_queue:
            if approval["id"] == request_id:
                approval["status"] = "denied"
                return True
        return False
