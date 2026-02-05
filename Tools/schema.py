"""
Tool Schema - 工具定义与 JSON Schema 转换器

版本: v2.3
负责:
- 工具定义标准化
- JSON Schema 生成
- 工具元数据管理
"""

from typing import Optional, Dict, Any, List, Callable, get_type_hints
from dataclasses import dataclass, field
from enum import Enum
import inspect
import json


class ParameterType(Enum):
    """参数类型"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: ParameterType
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None
    
    def to_schema(self) -> Dict[str, Any]:
        """转换为 JSON Schema"""
        schema = {
            "type": self.type.value,
            "description": self.description
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


@dataclass
class ToolDefinition:
    """
    工具定义
    
    符合 OpenAI/Ollama 工具调用规范
    """
    name: str
    description: str
    parameters: List[ToolParameter] = field(default_factory=list)
    handler: Optional[Callable] = None
    category: str = "general"
    is_async: bool = False
    
    def to_schema(self) -> Dict[str, Any]:
        """
        转换为 JSON Schema 格式
        
        符合 Ollama/OpenAI 的 tools 参数格式
        """
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_schema()
            if param.required:
                required.append(param.name)
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
    
    def to_prompt_description(self) -> str:
        """生成用于 System Prompt 的工具描述"""
        params_desc = []
        for p in self.parameters:
            req = "(必填)" if p.required else "(可选)"
            params_desc.append(f"    - {p.name}: {p.description} {req}")
        
        params_str = "\n".join(params_desc) if params_desc else "    (无参数)"
        
        return f"""- **{self.name}**: {self.description}
  参数:
{params_str}"""


class ToolSchemaGenerator:
    """
    工具 Schema 生成器
    
    从 Python 函数自动生成工具定义
    """
    
    TYPE_MAPPING = {
        str: ParameterType.STRING,
        int: ParameterType.INTEGER,
        float: ParameterType.NUMBER,
        bool: ParameterType.BOOLEAN,
        list: ParameterType.ARRAY,
        dict: ParameterType.OBJECT,
    }
    
    @classmethod
    def from_function(
        cls,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        category: str = "general"
    ) -> ToolDefinition:
        """
        从 Python 函数生成工具定义
        
        Args:
            func: Python 函数
            name: 工具名称，默认使用函数名
            description: 描述，默认使用函数 docstring
            category: 分类
            
        Returns:
            ToolDefinition
        """
        func_name = name or func.__name__
        func_desc = description or (func.__doc__ or "").strip().split("\n")[0]
        
        # 获取函数签名
        sig = inspect.signature(func)
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        
        parameters = []
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue
            
            # 获取类型
            param_type = hints.get(param_name, str)
            schema_type = cls.TYPE_MAPPING.get(param_type, ParameterType.STRING)
            
            # 获取默认值
            has_default = param.default != inspect.Parameter.empty
            default_value = param.default if has_default else None
            
            # 尝试从 docstring 获取参数描述
            param_desc = f"参数 {param_name}"
            
            parameters.append(ToolParameter(
                name=param_name,
                type=schema_type,
                description=param_desc,
                required=not has_default,
                default=default_value
            ))
        
        return ToolDefinition(
            name=func_name,
            description=func_desc,
            parameters=parameters,
            handler=func,
            category=category,
            is_async=inspect.iscoroutinefunction(func)
        )


def generate_tools_prompt(tools: List[ToolDefinition]) -> str:
    """
    生成包含工具描述的 System Prompt
    
    Args:
        tools: 工具定义列表
        
    Returns:
        格式化的工具描述字符串
    """
    if not tools:
        return ""
    
    tool_descriptions = []
    for tool in tools:
        tool_descriptions.append(tool.to_prompt_description())
    
    return f"""你具备以下工具能力，可以通过调用工具来完成用户的请求：

## 可用工具

{chr(10).join(tool_descriptions)}

## 工具调用格式

当你需要使用工具时，请使用以下 JSON 格式：
```json
{{"tool_calls": [{{"name": "工具名称", "arguments": {{"参数名": "参数值"}}}}]}}
```

## 重要规则

1. 仔细分析用户请求，判断是否需要使用工具
2. 如果需要使用工具，输出工具调用 JSON，不要输出其他内容
3. 如果不需要工具，直接回答用户问题
4. 工具执行结果会返回给你，你需要基于结果生成最终回复
5. 文件操作时，写入的文件会保存在 test 目录下
"""
