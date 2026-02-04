"""
Tool Adapters - 参数校验与映射

负责:
- 参数类型验证
- 参数转换与映射
- 输入/输出标准化
"""

from typing import Optional, Dict, Any, List, Callable, Type
from dataclasses import dataclass, field
from enum import Enum
import json


class ParameterType(Enum):
    """参数类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    ANY = "any"


@dataclass
class ParameterSchema:
    """参数模式定义"""
    name: str
    param_type: ParameterType
    required: bool = False
    default: Any = None
    description: str = ""
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.param_type.value,
            "required": self.required,
            "default": self.default,
            "description": self.description,
            "constraints": self.constraints
        }


class ParameterValidator:
    """
    参数验证器
    
    负责验证和转换参数
    """
    
    TYPE_VALIDATORS: Dict[ParameterType, Callable] = {
        ParameterType.STRING: lambda x: isinstance(x, str),
        ParameterType.INTEGER: lambda x: isinstance(x, int) and not isinstance(x, bool),
        ParameterType.FLOAT: lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
        ParameterType.BOOLEAN: lambda x: isinstance(x, bool),
        ParameterType.ARRAY: lambda x: isinstance(x, list),
        ParameterType.OBJECT: lambda x: isinstance(x, dict),
        ParameterType.ANY: lambda x: True
    }
    
    TYPE_CONVERTERS: Dict[ParameterType, Callable] = {
        ParameterType.STRING: str,
        ParameterType.INTEGER: int,
        ParameterType.FLOAT: float,
        ParameterType.BOOLEAN: lambda x: x.lower() in ('true', '1', 'yes') if isinstance(x, str) else bool(x),
        ParameterType.ARRAY: lambda x: json.loads(x) if isinstance(x, str) else list(x),
        ParameterType.OBJECT: lambda x: json.loads(x) if isinstance(x, str) else dict(x),
        ParameterType.ANY: lambda x: x
    }
    
    def __init__(self, schemas: List[ParameterSchema]):
        self.schemas = {s.name: s for s in schemas}
    
    def validate(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证参数
        
        Returns:
            (是否有效, 错误信息)
        """
        # 检查必需参数
        for name, schema in self.schemas.items():
            if schema.required and name not in params:
                return False, f"Missing required parameter: {name}"
        
        # 验证参数类型
        for name, value in params.items():
            if name in self.schemas:
                schema = self.schemas[name]
                validator = self.TYPE_VALIDATORS.get(schema.param_type)
                
                if validator and not validator(value):
                    return False, f"Invalid type for parameter '{name}': expected {schema.param_type.value}"
                
                # 验证约束
                error = self._validate_constraints(name, value, schema.constraints)
                if error:
                    return False, error
        
        return True, None
    
    def _validate_constraints(
        self,
        name: str,
        value: Any,
        constraints: Dict[str, Any]
    ) -> Optional[str]:
        """验证约束条件"""
        if not constraints:
            return None
        
        # 最小值
        if "min" in constraints and value < constraints["min"]:
            return f"Parameter '{name}' is below minimum value {constraints['min']}"
        
        # 最大值
        if "max" in constraints and value > constraints["max"]:
            return f"Parameter '{name}' exceeds maximum value {constraints['max']}"
        
        # 最小长度
        if "min_length" in constraints and len(value) < constraints["min_length"]:
            return f"Parameter '{name}' is shorter than minimum length {constraints['min_length']}"
        
        # 最大长度
        if "max_length" in constraints and len(value) > constraints["max_length"]:
            return f"Parameter '{name}' exceeds maximum length {constraints['max_length']}"
        
        # 枚举值
        if "enum" in constraints and value not in constraints["enum"]:
            return f"Parameter '{name}' must be one of {constraints['enum']}"
        
        # 正则表达式
        if "pattern" in constraints:
            import re
            if not re.match(constraints["pattern"], str(value)):
                return f"Parameter '{name}' does not match pattern {constraints['pattern']}"
        
        return None
    
    def convert(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        转换参数类型
        
        Returns:
            转换后的参数
        """
        result = {}
        
        for name, schema in self.schemas.items():
            if name in params:
                value = params[name]
                converter = self.TYPE_CONVERTERS.get(schema.param_type)
                
                try:
                    result[name] = converter(value) if converter else value
                except (ValueError, TypeError, json.JSONDecodeError):
                    result[name] = value
            elif schema.default is not None:
                result[name] = schema.default
        
        # 保留未定义的参数
        for name, value in params.items():
            if name not in result:
                result[name] = value
        
        return result
    
    def apply_defaults(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """应用默认值"""
        result = params.copy()
        
        for name, schema in self.schemas.items():
            if name not in result and schema.default is not None:
                result[name] = schema.default
        
        return result


class ToolAdapter:
    """
    工具适配器
    
    封装工具的参数处理和执行
    """
    
    def __init__(
        self,
        name: str,
        handler: Callable,
        parameters: Optional[List[ParameterSchema]] = None,
        description: str = ""
    ):
        self.name = name
        self.handler = handler
        self.description = description
        self.validator = ParameterValidator(parameters or [])
        self._input_transformer: Optional[Callable] = None
        self._output_transformer: Optional[Callable] = None
    
    def set_input_transformer(self, transformer: Callable) -> None:
        """设置输入转换器"""
        self._input_transformer = transformer
    
    def set_output_transformer(self, transformer: Callable) -> None:
        """设置输出转换器"""
        self._output_transformer = transformer
    
    async def execute(self, **params) -> Any:
        """
        执行工具
        
        Args:
            **params: 参数
            
        Returns:
            执行结果
        """
        # 验证参数
        valid, error = self.validator.validate(params)
        if not valid:
            raise ValueError(error)
        
        # 转换参数
        converted = self.validator.convert(params)
        
        # 应用输入转换器
        if self._input_transformer:
            converted = self._input_transformer(converted)
        
        # 执行
        import asyncio
        if asyncio.iscoroutinefunction(self.handler):
            result = await self.handler(**converted)
        else:
            result = self.handler(**converted)
        
        # 应用输出转换器
        if self._output_transformer:
            result = self._output_transformer(result)
        
        return result
    
    def get_schema(self) -> Dict[str, Any]:
        """获取工具模式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [s.to_dict() for s in self.validator.schemas.values()]
        }
