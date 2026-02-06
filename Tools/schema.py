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
    
    return f"""你是一个具备工具调用能力的 AI 助手。你可以通过调用工具来完成用户的请求。

## 可用工具

{chr(10).join(tool_descriptions)}

## 工具调用格式

当你需要使用工具时，**只输出**以下 JSON 格式，不要输出任何其他内容：
```json
{{"tool_calls": [{{"name": "工具名称", "arguments": {{"参数名": "参数值"}}}}]}}
```

## 重要规则

1. 仔细分析用户请求，判断是否需要使用工具
2. 如果需要使用工具，**只输出**工具调用 JSON，不要输出解释文字
3. 如果不需要工具，或者需要向用户询问信息，直接用文字回复用户
4. 工具执行结果会返回给你，你需要基于结果生成最终回复
5. **只使用工具定义中存在的参数**，不要添加额外参数

## GitHub 操作流程（非常重要）

当用户要操作 GitHub（如创建仓库、查看仓库等）时，必须按照以下流程：

### 步骤 1：检查用户是否提供了 Token
- 如果用户在消息中提供了 Token（以 `ghp_` 开头的字符串），调用 `github_set_token` 工具
- 如果用户没有提供 Token，用文字回复用户，询问 Token：
  "请提供您的 GitHub Personal Access Token 来完成此操作。获取方式：访问 https://github.com/settings/tokens 创建一个新 Token（需要 repo 权限）"

### 步骤 2：设置并验证 Token
- 当用户提供 Token 后，调用 `github_set_token` 工具：
```json
{{"tool_calls": [{{"name": "github_set_token", "arguments": {{"token": "用户提供的实际Token"}}}}]}}
```
- **token 参数必须是用户提供的实际 Token 字符串（以 ghp_ 开头），不能是占位符**

### 步骤 3：执行 GitHub 操作
- Token 验证成功后，调用相应的 GitHub 工具（如 github_create_repo）
- 如果 Token 无效，告知用户错误信息并请求新的 Token

### 示例：用户说"创建一个 test-repo 仓库"
1. 你回复："请提供您的 GitHub Token 来创建仓库"
2. 用户说："ghp_xxxxx 这是我的 token"
3. 你调用：`github_set_token` (token="ghp_xxxxx")
4. Token 有效后，调用：`github_create_repo` (name="test-repo")

## 文件操作说明

- list_files: 列出目录内容
- read_file: 读取文件内容
- write_file: 写入文件（自动保存到 Test 目录）
"""
