"""
Observability - 可观测性

负责:
- Debug 日志
- 审计追踪
- 性能指标
- 事件记录
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import threading


class EventType(Enum):
    """事件类型"""
    REQUEST = "request"
    RESPONSE = "response"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class LogLevel(Enum):
    """日志级别"""
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4


@dataclass
class Event:
    """事件记录"""
    event_id: str
    event_type: EventType
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "trace_id": self.trace_id
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class Metric:
    """性能指标"""
    name: str
    value: float
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class Observability:
    """
    可观测性管理器
    
    提供日志、审计和指标功能
    """
    
    def __init__(
        self,
        log_level: LogLevel = LogLevel.INFO,
        max_events: int = 10000
    ):
        self.log_level = log_level
        self.max_events = max_events
        
        self._events: List[Event] = []
        self._metrics: Dict[str, List[Metric]] = {}
        self._event_handlers: List[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        self._event_counter = 0
    
    def _generate_event_id(self) -> str:
        """生成事件 ID"""
        with self._lock:
            self._event_counter += 1
            return f"evt_{self._event_counter:08d}"
    
    def record_event(
        self,
        event_type: EventType,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Event:
        """记录事件"""
        event = Event(
            event_id=self._generate_event_id(),
            event_type=event_type,
            message=message,
            data=data or {},
            session_id=session_id,
            trace_id=trace_id
        )
        
        with self._lock:
            self._events.append(event)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events // 2:]
        
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception:
                pass
        
        return event
    
    def debug(self, message: str, **kwargs) -> Optional[Event]:
        """记录 DEBUG 日志"""
        if self.log_level.value <= LogLevel.DEBUG.value:
            return self.record_event(EventType.DEBUG, message, kwargs)
        return None
    
    def info(self, message: str, **kwargs) -> Optional[Event]:
        """记录 INFO 日志"""
        if self.log_level.value <= LogLevel.INFO.value:
            return self.record_event(EventType.INFO, message, kwargs)
        return None
    
    def warning(self, message: str, **kwargs) -> Optional[Event]:
        """记录 WARNING 日志"""
        if self.log_level.value <= LogLevel.WARNING.value:
            return self.record_event(EventType.WARNING, message, kwargs)
        return None
    
    def error(self, message: str, **kwargs) -> Optional[Event]:
        """记录 ERROR 日志"""
        if self.log_level.value <= LogLevel.ERROR.value:
            return self.record_event(EventType.ERROR, message, kwargs)
        return None
    
    def record_request(
        self,
        endpoint: str,
        method: str,
        data: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ) -> Event:
        """记录请求"""
        return self.record_event(
            EventType.REQUEST,
            f"{method} {endpoint}",
            {"endpoint": endpoint, "method": method, "data": data},
            session_id=session_id
        )
    
    def record_response(
        self,
        endpoint: str,
        status_code: int,
        duration_ms: float,
        session_id: Optional[str] = None
    ) -> Event:
        """记录响应"""
        return self.record_event(
            EventType.RESPONSE,
            f"Response {status_code} for {endpoint}",
            {"endpoint": endpoint, "status_code": status_code, "duration_ms": duration_ms},
            session_id=session_id
        )
    
    def record_tool_call(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        result: Any,
        duration_ms: float,
        success: bool,
        session_id: Optional[str] = None
    ) -> Event:
        """记录工具调用"""
        return self.record_event(
            EventType.TOOL_CALL,
            f"Tool call: {tool_name}",
            {
                "tool_name": tool_name,
                "parameters": parameters,
                "result": result,
                "duration_ms": duration_ms,
                "success": success
            },
            session_id=session_id
        )
    
    def record_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: float,
        session_id: Optional[str] = None
    ) -> Event:
        """记录 LLM 调用"""
        return self.record_event(
            EventType.LLM_CALL,
            f"LLM call: {model}",
            {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "duration_ms": duration_ms
            },
            session_id=session_id
        )
    
    def record_metric(self, name: str, value: float, unit: str = "", **tags) -> Metric:
        """记录指标"""
        metric = Metric(name=name, value=value, unit=unit, tags=tags)
        
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = []
            self._metrics[name].append(metric)
            if len(self._metrics[name]) > 1000:
                self._metrics[name] = self._metrics[name][-500:]
        
        return metric
    
    def add_event_handler(self, handler: Callable[[Event], None]) -> None:
        """添加事件处理器"""
        self._event_handlers.append(handler)
    
    def get_events(
        self,
        event_type: Optional[EventType] = None,
        session_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取事件"""
        events = self._events
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if session_id:
            events = [e for e in events if e.session_id == session_id]
        return [e.to_dict() for e in events[-limit:]]
    
    def get_metrics(self, name: Optional[str] = None, limit: int = 100) -> Dict[str, List[Dict[str, Any]]]:
        """获取指标"""
        if name:
            metrics = self._metrics.get(name, [])
            return {
                name: [
                    {"value": m.value, "unit": m.unit, "tags": m.tags, "timestamp": m.timestamp.isoformat()}
                    for m in metrics[-limit:]
                ]
            }
        return {
            k: [
                {"value": m.value, "unit": m.unit, "tags": m.tags, "timestamp": m.timestamp.isoformat()}
                for m in v[-limit:]
            ]
            for k, v in self._metrics.items()
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """获取摘要"""
        event_counts = {}
        for event in self._events:
            event_type = event.event_type.value
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        return {
            "total_events": len(self._events),
            "event_counts": event_counts,
            "metric_names": list(self._metrics.keys()),
            "log_level": self.log_level.value
        }
    
    def clear_events(self) -> None:
        """清空事件"""
        with self._lock:
            self._events.clear()
    
    def clear_metrics(self) -> None:
        """清空指标"""
        with self._lock:
            self._metrics.clear()


_default_observability: Optional[Observability] = None


def get_observability() -> Observability:
    """获取全局可观测性实例"""
    global _default_observability
    if _default_observability is None:
        _default_observability = Observability()
    return _default_observability
