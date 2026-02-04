"""
Bridge Dispatcher - 请求流向解析与消息调度

负责:
- 请求路由
- 组件间消息传递
- 流向控制
"""

from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import asyncio


class MessageType(Enum):
    """消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    COMMAND = "command"
    NOTIFICATION = "notification"


class ComponentType(Enum):
    """组件类型"""
    UI = "ui"
    GATEWAY = "gateway"
    LLM = "llm"
    TOOLS = "tools"
    MEMORY = "memory"


@dataclass
class Message:
    """消息"""
    id: str
    type: MessageType
    source: ComponentType
    target: ComponentType
    payload: Any
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "source": self.source.value,
            "target": self.target.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class MessageRoute:
    """消息路由"""
    source: ComponentType
    target: ComponentType
    handler: Callable[[Message], Awaitable[Any]]
    enabled: bool = True
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value,
            "target": self.target.value,
            "enabled": self.enabled,
            "priority": self.priority
        }


class Dispatcher:
    """
    消息调度器
    
    管理组件间的消息传递
    """
    
    def __init__(self):
        self._routes: List[MessageRoute] = []
        self._handlers: Dict[ComponentType, List[Callable]] = {}
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._message_history: List[Message] = []
    
    def register_route(
        self,
        source: ComponentType,
        target: ComponentType,
        handler: Callable[[Message], Awaitable[Any]],
        priority: int = 0
    ) -> MessageRoute:
        """
        注册路由
        
        Args:
            source: 源组件
            target: 目标组件
            handler: 处理函数
            priority: 优先级
            
        Returns:
            路由对象
        """
        route = MessageRoute(
            source=source,
            target=target,
            handler=handler,
            priority=priority
        )
        
        self._routes.append(route)
        self._routes.sort(key=lambda r: r.priority, reverse=True)
        
        return route
    
    def unregister_route(self, route: MessageRoute) -> bool:
        """注销路由"""
        if route in self._routes:
            self._routes.remove(route)
            return True
        return False
    
    def register_handler(
        self,
        component: ComponentType,
        handler: Callable[[Message], Any]
    ) -> None:
        """
        注册组件处理器
        
        Args:
            component: 组件类型
            handler: 处理函数
        """
        if component not in self._handlers:
            self._handlers[component] = []
        self._handlers[component].append(handler)
    
    async def dispatch(self, message: Message) -> Any:
        """
        调度消息
        
        Args:
            message: 消息
            
        Returns:
            处理结果
        """
        # 记录消息
        self._message_history.append(message)
        
        # 查找匹配路由
        for route in self._routes:
            if not route.enabled:
                continue
            
            if route.source == message.source and route.target == message.target:
                try:
                    result = await route.handler(message)
                    return result
                except Exception as e:
                    return {"error": str(e)}
        
        # 查找目标组件处理器
        handlers = self._handlers.get(message.target, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(message)
                else:
                    result = handler(message)
                return result
            except Exception:
                continue
        
        return {"error": f"No handler found for {message.source.value} -> {message.target.value}"}
    
    async def send(
        self,
        source: ComponentType,
        target: ComponentType,
        payload: Any,
        msg_type: MessageType = MessageType.REQUEST,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        发送消息
        
        Args:
            source: 源组件
            target: 目标组件
            payload: 负载
            msg_type: 消息类型
            metadata: 元数据
            
        Returns:
            处理结果
        """
        import uuid
        
        message = Message(
            id=str(uuid.uuid4()),
            type=msg_type,
            source=source,
            target=target,
            payload=payload,
            metadata=metadata or {}
        )
        
        return await self.dispatch(message)
    
    async def broadcast(
        self,
        source: ComponentType,
        payload: Any,
        msg_type: MessageType = MessageType.EVENT,
        exclude: Optional[List[ComponentType]] = None
    ) -> Dict[ComponentType, Any]:
        """
        广播消息
        
        Args:
            source: 源组件
            payload: 负载
            msg_type: 消息类型
            exclude: 排除的组件
            
        Returns:
            各组件的处理结果
        """
        results = {}
        exclude = exclude or []
        
        for component in ComponentType:
            if component != source and component not in exclude:
                result = await self.send(source, component, payload, msg_type)
                results[component] = result
        
        return results
    
    def get_routes(self) -> List[Dict[str, Any]]:
        """获取所有路由"""
        return [r.to_dict() for r in self._routes]
    
    def get_message_history(
        self,
        limit: int = 100,
        source: Optional[ComponentType] = None,
        target: Optional[ComponentType] = None
    ) -> List[Dict[str, Any]]:
        """
        获取消息历史
        
        Args:
            limit: 数量限制
            source: 过滤源组件
            target: 过滤目标组件
            
        Returns:
            消息历史
        """
        history = self._message_history
        
        if source:
            history = [m for m in history if m.source == source]
        
        if target:
            history = [m for m in history if m.target == target]
        
        return [m.to_dict() for m in history[-limit:]]
    
    def clear_history(self) -> None:
        """清空消息历史"""
        self._message_history.clear()


# 全局调度器
_dispatcher: Optional[Dispatcher] = None


def get_dispatcher() -> Dispatcher:
    """获取全局调度器"""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = Dispatcher()
    return _dispatcher
