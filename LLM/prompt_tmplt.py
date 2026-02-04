"""
Prompt Template - Prompt 模板管理

负责:
- Prompt 模板定义与存储
- 模板变量替换
- 预设模板管理
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from string import Template
import json


@dataclass
class PromptTemplate:
    """
    Prompt 模板类
    
    支持变量替换和模板组合
    """
    name: str
    template: str
    description: str = ""
    variables: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def format(self, **kwargs) -> str:
        """
        格式化模板,替换变量
        
        Args:
            **kwargs: 变量键值对
            
        Returns:
            格式化后的字符串
        """
        try:
            return self.template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing required variable: {e}")
    
    def safe_format(self, **kwargs) -> str:
        """
        安全格式化,缺失变量保留原样
        
        Args:
            **kwargs: 变量键值对
            
        Returns:
            格式化后的字符串
        """
        result = self.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result
    
    def validate(self) -> bool:
        """验证模板是否有效"""
        # 检查所有声明的变量是否在模板中
        for var in self.variables:
            if f"{{{var}}}" not in self.template:
                return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "template": self.template,
            "description": self.description,
            "variables": self.variables,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptTemplate":
        """从字典创建模板"""
        return cls(
            name=data["name"],
            template=data["template"],
            description=data.get("description", ""),
            variables=data.get("variables", []),
            metadata=data.get("metadata", {})
        )


class PromptManager:
    """
    Prompt 模板管理器
    
    负责管理和组织多个 Prompt 模板
    """
    
    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._load_default_templates()
    
    def _load_default_templates(self) -> None:
        """加载默认模板"""
        # 系统提示模板
        self.register(PromptTemplate(
            name="system_default",
            template="""你是 OpenClaw,一个智能助手。

你的能力包括:
- 回答用户问题
- 分析和处理信息
- 执行工具调用

请根据用户的需求提供准确、有帮助的回复。""",
            description="默认系统提示",
            variables=[]
        ))
        
        # 工具调用模板
        self.register(PromptTemplate(
            name="tool_call",
            template="""用户请求: {user_request}

可用工具:
{available_tools}

请分析用户请求,决定是否需要调用工具。
如果需要调用工具,请按以下格式输出:
```tool_call
{{"tool": "工具名称", "parameters": {{...}}}}
```

如果不需要工具,直接回复用户。""",
            description="工具调用决策模板",
            variables=["user_request", "available_tools"]
        ))
        
        # 对话历史模板
        self.register(PromptTemplate(
            name="chat_history",
            template="""对话历史:
{history}

当前用户输入: {user_input}

请基于对话历史,回复用户。""",
            description="带历史的对话模板",
            variables=["history", "user_input"]
        ))
        
        # 任务规划模板
        self.register(PromptTemplate(
            name="task_planning",
            template="""任务目标: {goal}

当前状态: {current_state}

可执行操作:
{available_actions}

请制定一个分步骤的执行计划来达成目标。""",
            description="任务规划模板",
            variables=["goal", "current_state", "available_actions"]
        ))
        
        # 错误处理模板
        self.register(PromptTemplate(
            name="error_handling",
            template="""在执行过程中遇到了错误:

错误类型: {error_type}
错误信息: {error_message}
上下文: {context}

请分析错误原因并提供解决方案。""",
            description="错误处理模板",
            variables=["error_type", "error_message", "context"]
        ))
    
    def register(self, template: PromptTemplate) -> None:
        """
        注册模板
        
        Args:
            template: 要注册的模板
        """
        self._templates[template.name] = template
    
    def get(self, name: str) -> Optional[PromptTemplate]:
        """
        获取模板
        
        Args:
            name: 模板名称
            
        Returns:
            模板对象,不存在则返回 None
        """
        return self._templates.get(name)
    
    def format(self, name: str, **kwargs) -> str:
        """
        格式化指定模板
        
        Args:
            name: 模板名称
            **kwargs: 变量
            
        Returns:
            格式化后的字符串
        """
        template = self.get(name)
        if template is None:
            raise ValueError(f"Template not found: {name}")
        return template.format(**kwargs)
    
    def list_templates(self) -> List[str]:
        """列出所有模板名称"""
        return list(self._templates.keys())
    
    def remove(self, name: str) -> bool:
        """
        移除模板
        
        Args:
            name: 模板名称
            
        Returns:
            是否成功移除
        """
        if name in self._templates:
            del self._templates[name]
            return True
        return False
    
    def export_templates(self) -> Dict[str, Any]:
        """导出所有模板为字典"""
        return {
            name: template.to_dict()
            for name, template in self._templates.items()
        }
    
    def import_templates(self, data: Dict[str, Any]) -> int:
        """
        导入模板
        
        Args:
            data: 模板数据字典
            
        Returns:
            导入的模板数量
        """
        count = 0
        for name, template_data in data.items():
            try:
                template = PromptTemplate.from_dict(template_data)
                self.register(template)
                count += 1
            except (KeyError, ValueError):
                continue
        return count


# 全局模板管理器实例
_default_manager: Optional[PromptManager] = None


def get_prompt_manager() -> PromptManager:
    """获取全局模板管理器"""
    global _default_manager
    if _default_manager is None:
        _default_manager = PromptManager()
    return _default_manager


def get_prompt(name: str, **kwargs) -> str:
    """快速获取并格式化模板"""
    return get_prompt_manager().format(name, **kwargs)
