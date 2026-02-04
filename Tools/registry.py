"""
Tool Registry - 工具发现与启停

负责:
- 工具注册与注销
- 工具发现
- 工具状态管理
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading


class ToolStatus(Enum):
    """工具状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class ToolInfo:
    """工具信息"""
    name: str
    description: str
    handler: Callable
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: ToolStatus = ToolStatus.ACTIVE
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "status": self.status.value,
            "version": self.version,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }


class ToolRegistry:
    """
    工具注册表
    
    管理所有可用工具
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolInfo] = {}
        self._lock = threading.Lock()
        self._hooks: Dict[str, List[Callable]] = {
            "on_register": [],
            "on_unregister": [],
            "on_status_change": []
        }
    
    def register(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        version: str = "1.0.0",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ToolInfo:
        """
        注册工具
        
        Args:
            name: 工具名称
            handler: 处理函数
            description: 描述
            parameters: 参数定义
            version: 版本
            tags: 标签
            metadata: 元数据
            
        Returns:
            工具信息
        """
        with self._lock:
            tool_info = ToolInfo(
                name=name,
                handler=handler,
                description=description,
                parameters=parameters or {},
                version=version,
                tags=tags or [],
                metadata=metadata or {}
            )
            
            self._tools[name] = tool_info
            
            # 触发钩子
            self._trigger_hooks("on_register", tool_info)
            
            return tool_info
    
    def unregister(self, name: str) -> bool:
        """
        注销工具
        
        Args:
            name: 工具名称
            
        Returns:
            是否成功
        """
        with self._lock:
            if name in self._tools:
                tool_info = self._tools[name]
                del self._tools[name]
                
                # 触发钩子
                self._trigger_hooks("on_unregister", tool_info)
                
                return True
            return False
    
    def get(self, name: str) -> Optional[ToolInfo]:
        """获取工具信息"""
        return self._tools.get(name)
    
    def get_handler(self, name: str) -> Optional[Callable]:
        """获取工具处理函数"""
        tool = self._tools.get(name)
        return tool.handler if tool else None
    
    def list_tools(
        self,
        status: Optional[ToolStatus] = None,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        列出工具
        
        Args:
            status: 过滤状态
            tags: 过滤标签
            
        Returns:
            工具信息列表
        """
        tools = list(self._tools.values())
        
        if status:
            tools = [t for t in tools if t.status == status]
        
        if tags:
            tools = [t for t in tools if any(tag in t.tags for tag in tags)]
        
        return [t.to_dict() for t in tools]
    
    def set_status(self, name: str, status: ToolStatus) -> bool:
        """
        设置工具状态
        
        Args:
            name: 工具名称
            status: 新状态
            
        Returns:
            是否成功
        """
        with self._lock:
            if name in self._tools:
                old_status = self._tools[name].status
                self._tools[name].status = status
                
                # 触发钩子
                self._trigger_hooks(
                    "on_status_change",
                    self._tools[name],
                    old_status,
                    status
                )
                
                return True
            return False
    
    def enable(self, name: str) -> bool:
        """启用工具"""
        return self.set_status(name, ToolStatus.ACTIVE)
    
    def disable(self, name: str) -> bool:
        """禁用工具"""
        return self.set_status(name, ToolStatus.DISABLED)
    
    def is_active(self, name: str) -> bool:
        """检查工具是否激活"""
        tool = self._tools.get(name)
        return tool is not None and tool.status == ToolStatus.ACTIVE
    
    def discover(self, pattern: Optional[str] = None) -> List[str]:
        """
        发现工具
        
        Args:
            pattern: 名称模式 (支持通配符)
            
        Returns:
            工具名称列表
        """
        names = list(self._tools.keys())
        
        if pattern:
            import fnmatch
            names = [n for n in names if fnmatch.fnmatch(n, pattern)]
        
        return names
    
    def add_hook(self, event: str, callback: Callable) -> None:
        """添加钩子"""
        if event in self._hooks:
            self._hooks[event].append(callback)
    
    def remove_hook(self, event: str, callback: Callable) -> None:
        """移除钩子"""
        if event in self._hooks and callback in self._hooks[event]:
            self._hooks[event].remove(callback)
    
    def _trigger_hooks(self, event: str, *args) -> None:
        """触发钩子"""
        for callback in self._hooks.get(event, []):
            try:
                callback(*args)
            except Exception:
                pass
    
    def count(self) -> int:
        """获取工具数量"""
        return len(self._tools)
    
    def clear(self) -> None:
        """清空注册表"""
        with self._lock:
            self._tools.clear()


# 全局注册表
_default_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取全局注册表"""
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def register_tool(
    name: str,
    handler: Callable,
    **kwargs
) -> ToolInfo:
    """便捷注册函数"""
    return get_registry().register(name, handler, **kwargs)
