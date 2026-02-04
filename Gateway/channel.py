"""
Channel - 标准 JSON 消息格式转换

负责:
- 输入消息标准化
- 输出消息格式化
- 消息验证
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json
import uuid


@dataclass
class StandardMessage:
    """标准消息格式"""
    id: str
    type: str  # 'text', 'image', 'tool_call', 'tool_result', 'system'
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StandardMessage":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data.get("type", "text"),
            content=data.get("content", ""),
            metadata=data.get("metadata", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class Channel:
    """
    消息通道
    
    负责消息格式的转换和标准化
    """
    
    MESSAGE_TYPES = ['text', 'image', 'tool_call', 'tool_result', 'system', 'error']
    
    def __init__(self):
        self._validators: Dict[str, callable] = {}
        self._transformers: Dict[str, callable] = {}
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """设置默认处理器"""
        # 文本消息验证器
        self.register_validator('text', lambda x: isinstance(x, str) and len(x) > 0)
        
        # 工具调用验证器
        self.register_validator('tool_call', lambda x: (
            isinstance(x, dict) and 
            'tool' in x and 
            'parameters' in x
        ))
    
    def register_validator(self, msg_type: str, validator: callable) -> None:
        """
        注册消息验证器
        
        Args:
            msg_type: 消息类型
            validator: 验证函数
        """
        self._validators[msg_type] = validator
    
    def register_transformer(self, msg_type: str, transformer: callable) -> None:
        """
        注册消息转换器
        
        Args:
            msg_type: 消息类型
            transformer: 转换函数
        """
        self._transformers[msg_type] = transformer
    
    def validate(self, message: StandardMessage) -> bool:
        """
        验证消息
        
        Args:
            message: 标准消息
            
        Returns:
            是否有效
        """
        if message.type not in self.MESSAGE_TYPES:
            return False
        
        validator = self._validators.get(message.type)
        if validator:
            return validator(message.content)
        
        return True
    
    def format_input(
        self,
        content: Any,
        msg_type: str = "text",
        context: Optional[Dict[str, Any]] = None
    ) -> StandardMessage:
        """
        格式化输入消息
        
        Args:
            content: 消息内容
            msg_type: 消息类型
            context: 上下文信息
            
        Returns:
            标准消息
        """
        metadata = {}
        if context:
            metadata["context"] = context
        
        # 应用转换器
        transformer = self._transformers.get(msg_type)
        if transformer:
            content = transformer(content)
        
        message = StandardMessage(
            id=str(uuid.uuid4()),
            type=msg_type,
            content=content,
            metadata=metadata
        )
        
        return message
    
    def format_output(self, result: Any) -> str:
        """
        格式化输出结果
        
        Args:
            result: 处理结果
            
        Returns:
            格式化的字符串
        """
        if isinstance(result, StandardMessage):
            return result.content if isinstance(result.content, str) else json.dumps(result.content)
        
        if isinstance(result, dict):
            if "content" in result:
                return result["content"]
            return json.dumps(result, ensure_ascii=False)
        
        if isinstance(result, str):
            return result
        
        return str(result)
    
    def parse_message(self, raw: str) -> StandardMessage:
        """
        解析原始消息
        
        Args:
            raw: 原始消息字符串
            
        Returns:
            标准消息
        """
        try:
            data = json.loads(raw)
            return StandardMessage.from_dict(data)
        except json.JSONDecodeError:
            # 作为纯文本处理
            return StandardMessage(
                id=str(uuid.uuid4()),
                type="text",
                content=raw
            )
    
    def create_tool_call(
        self,
        tool: str,
        parameters: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> StandardMessage:
        """
        创建工具调用消息
        
        Args:
            tool: 工具名称
            parameters: 参数
            metadata: 元数据
            
        Returns:
            工具调用消息
        """
        return StandardMessage(
            id=str(uuid.uuid4()),
            type="tool_call",
            content={
                "tool": tool,
                "parameters": parameters
            },
            metadata=metadata or {}
        )
    
    def create_tool_result(
        self,
        tool: str,
        result: Any,
        success: bool = True,
        error: Optional[str] = None
    ) -> StandardMessage:
        """
        创建工具结果消息
        
        Args:
            tool: 工具名称
            result: 执行结果
            success: 是否成功
            error: 错误信息
            
        Returns:
            工具结果消息
        """
        return StandardMessage(
            id=str(uuid.uuid4()),
            type="tool_result",
            content={
                "tool": tool,
                "result": result,
                "success": success,
                "error": error
            }
        )
    
    def create_error(self, error: str, code: Optional[str] = None) -> StandardMessage:
        """
        创建错误消息
        
        Args:
            error: 错误信息
            code: 错误代码
            
        Returns:
            错误消息
        """
        return StandardMessage(
            id=str(uuid.uuid4()),
            type="error",
            content={
                "error": error,
                "code": code
            }
        )
