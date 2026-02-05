"""
Tool Runtime v2.3 - 工具执行运行时

版本: v2.3
负责:
- 工具注册与管理
- 解析 LLM 的 tool_calls
- 执行工具函数
- 结果回传给 LLM
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import json
import re
import logging

from Tools.schema import ToolDefinition, generate_tools_prompt
from Tools.builtins.file_tools import get_file_tools
from Tools.builtins.github_tools import get_github_tools

logger = logging.getLogger("OpenClaw.Runtime")


@dataclass
class ToolCall:
    """工具调用"""
    name: str
    arguments: Dict[str, Any]
    id: Optional[str] = None


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_name: str
    success: bool
    result: Any
    error: Optional[str] = None
    execution_time_ms: float = 0
    
    def to_message(self) -> Dict[str, Any]:
        """转换为消息格式"""
        if self.success:
            content = json.dumps(self.result, ensure_ascii=False, indent=2)
        else:
            content = f"工具执行失败: {self.error}"
        
        return {
            "role": "tool",
            "name": self.tool_name,
            "content": content
        }


class ToolRuntime:
    """
    工具运行时 v2.3
    
    管理工具的注册、调用和结果处理
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._execution_history: List[Dict[str, Any]] = []
        
        # 加载内置工具
        self._load_builtin_tools()
    
    def _load_builtin_tools(self):
        """加载内置工具"""
        # 文件工具
        for tool in get_file_tools():
            self.register_tool(tool)
            logger.info(f"[Runtime] 注册工具: {tool.name} ({tool.category})")
        
        # GitHub 工具
        for tool in get_github_tools():
            self.register_tool(tool)
            logger.info(f"[Runtime] 注册工具: {tool.name} ({tool.category})")
    
    def register_tool(self, tool: ToolDefinition) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
    
    def unregister_tool(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[ToolDefinition]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """获取所有工具的 JSON Schema"""
        return [tool.to_schema() for tool in self._tools.values()]
    
    def get_system_prompt(self) -> str:
        """获取包含工具描述的 System Prompt"""
        return generate_tools_prompt(list(self._tools.values()))
    
    def parse_tool_calls(self, content: str) -> List[ToolCall]:
        """
        从 LLM 响应中解析工具调用
        
        支持多种格式:
        1. JSON 格式: {"tool_calls": [{"name": "xxx", "arguments": {...}}]}
        2. 代码块格式: ```json {...} ```
        
        Args:
            content: LLM 响应内容
            
        Returns:
            工具调用列表
        """
        tool_calls = []
        
        # 尝试解析 JSON 代码块
        json_patterns = [
            r'```json\s*(\{.*?\})\s*```',  # ```json {...} ```
            r'```\s*(\{.*?\})\s*```',       # ``` {...} ```
            r'(\{["\']?tool_calls["\']?\s*:.*?\})',  # 直接的 JSON
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, content, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    
                    # 处理 tool_calls 数组
                    if "tool_calls" in data:
                        for tc in data["tool_calls"]:
                            tool_calls.append(ToolCall(
                                name=tc.get("name", ""),
                                arguments=tc.get("arguments", {}),
                                id=tc.get("id")
                            ))
                    # 处理单个工具调用
                    elif "name" in data:
                        tool_calls.append(ToolCall(
                            name=data.get("name", ""),
                            arguments=data.get("arguments", {}),
                            id=data.get("id")
                        ))
                except json.JSONDecodeError:
                    continue
        
        return tool_calls
    
    def has_tool_calls(self, content: str) -> bool:
        """检查响应是否包含工具调用"""
        return len(self.parse_tool_calls(content)) > 0
    
    async def execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """
        执行单个工具调用
        
        Args:
            tool_call: 工具调用
            
        Returns:
            执行结果
        """
        start_time = datetime.now()
        
        tool = self._tools.get(tool_call.name)
        if not tool:
            return ToolResult(
                tool_name=tool_call.name,
                success=False,
                result=None,
                error=f"工具不存在: {tool_call.name}"
            )
        
        if not tool.handler:
            return ToolResult(
                tool_name=tool_call.name,
                success=False,
                result=None,
                error=f"工具未实现: {tool_call.name}"
            )
        
        try:
            logger.info(f"[Runtime] 执行工具: {tool_call.name}, 参数: {tool_call.arguments}")
            
            # 执行工具
            if tool.is_async:
                result = await tool.handler(**tool_call.arguments)
            else:
                result = tool.handler(**tool_call.arguments)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            logger.info(f"[Runtime] 工具执行完成: {tool_call.name}, 耗时: {execution_time:.0f}ms")
            
            # 记录历史
            self._execution_history.append({
                "tool": tool_call.name,
                "arguments": tool_call.arguments,
                "result": result,
                "timestamp": datetime.now().isoformat(),
                "execution_time_ms": execution_time
            })
            
            return ToolResult(
                tool_name=tool_call.name,
                success=True,
                result=result,
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"[Runtime] 工具执行失败: {tool_call.name}, 错误: {str(e)}")
            
            return ToolResult(
                tool_name=tool_call.name,
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=execution_time
            )
    
    async def execute_tools(self, tool_calls: List[ToolCall]) -> List[ToolResult]:
        """
        执行多个工具调用
        
        Args:
            tool_calls: 工具调用列表
            
        Returns:
            执行结果列表
        """
        results = []
        for tc in tool_calls:
            result = await self.execute_tool(tc)
            results.append(result)
        return results
    
    def get_execution_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self._execution_history[-limit:]


# 全局运行时实例
_runtime: Optional[ToolRuntime] = None


def get_runtime() -> ToolRuntime:
    """获取全局运行时实例"""
    global _runtime
    if _runtime is None:
        _runtime = ToolRuntime()
    return _runtime
