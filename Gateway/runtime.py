"""
Tool Runtime - 工具执行与映射

负责:
- 工具执行环境
- 参数映射与验证
- 执行超时控制
- 结果处理
"""

from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import traceback


@dataclass
class ToolExecutionResult:
    """工具执行结果"""
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "execution_time": self.execution_time,
            "metadata": self.metadata
        }


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    handler: Callable
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 30
    async_handler: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "timeout": self.timeout
        }


class ToolRuntime:
    """
    工具运行时
    
    管理工具的执行环境
    """
    
    DEFAULT_TIMEOUT = 30  # 默认超时时间(秒)
    
    def __init__(self, default_timeout: int = DEFAULT_TIMEOUT):
        self._tools: Dict[str, ToolDefinition] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self.default_timeout = default_timeout
    
    def register(
        self,
        name: str,
        handler: Callable,
        description: str = "",
        parameters: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        is_async: bool = False
    ) -> None:
        """
        注册工具
        
        Args:
            name: 工具名称
            handler: 处理函数
            description: 描述
            parameters: 参数定义
            timeout: 超时时间
            is_async: 是否为异步函数
        """
        self._tools[name] = ToolDefinition(
            name=name,
            handler=handler,
            description=description,
            parameters=parameters or {},
            timeout=timeout or self.default_timeout,
            async_handler=is_async
        )
    
    def unregister(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """获取工具定义"""
        return self._tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具"""
        return [tool.to_dict() for tool in self._tools.values()]
    
    async def execute(
        self,
        name: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ToolExecutionResult:
        """
        执行工具
        
        Args:
            name: 工具名称
            parameters: 参数
            context: 执行上下文
            
        Returns:
            执行结果
        """
        if name not in self._tools:
            return ToolExecutionResult(
                success=False,
                error=f"Tool not found: {name}"
            )
        
        tool = self._tools[name]
        params = parameters or {}
        
        # 验证参数
        validation_error = self._validate_parameters(tool, params)
        if validation_error:
            return ToolExecutionResult(
                success=False,
                error=validation_error
            )
        
        # 执行
        start_time = datetime.now()
        
        try:
            if tool.async_handler:
                result = await asyncio.wait_for(
                    tool.handler(**params),
                    timeout=tool.timeout
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(tool.handler, **params),
                    timeout=tool.timeout
                )
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            execution_result = ToolExecutionResult(
                success=True,
                result=result,
                execution_time=execution_time
            )
            
        except asyncio.TimeoutError:
            execution_time = (datetime.now() - start_time).total_seconds()
            execution_result = ToolExecutionResult(
                success=False,
                error=f"Tool execution timed out after {tool.timeout}s",
                execution_time=execution_time
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            execution_result = ToolExecutionResult(
                success=False,
                error=str(e),
                execution_time=execution_time,
                metadata={"traceback": traceback.format_exc()}
            )
        
        # 记录执行历史
        self._record_execution(name, params, execution_result)
        
        return execution_result
    
    def _validate_parameters(
        self,
        tool: ToolDefinition,
        params: Dict[str, Any]
    ) -> Optional[str]:
        """
        验证参数
        
        Returns:
            错误信息,无错误则返回 None
        """
        required_params = [
            name for name, spec in tool.parameters.items()
            if spec.get("required", False)
        ]
        
        for param in required_params:
            if param not in params:
                return f"Missing required parameter: {param}"
        
        return None
    
    def _record_execution(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: ToolExecutionResult
    ) -> None:
        """记录执行历史"""
        self._execution_history.append({
            "tool": tool_name,
            "parameters": params,
            "result": result.to_dict(),
            "timestamp": datetime.now().isoformat()
        })
        
        # 保持历史记录不超过 1000 条
        if len(self._execution_history) > 1000:
            self._execution_history = self._execution_history[-500:]
    
    def get_execution_history(
        self,
        tool_name: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取执行历史"""
        history = self._execution_history
        
        if tool_name:
            history = [h for h in history if h["tool"] == tool_name]
        
        return history[-limit:]
    
    def clear_history(self) -> None:
        """清空执行历史"""
        self._execution_history.clear()


# 全局运行时实例
_default_runtime: Optional[ToolRuntime] = None


def get_runtime() -> ToolRuntime:
    """获取全局运行时实例"""
    global _default_runtime
    if _default_runtime is None:
        _default_runtime = ToolRuntime()
    return _default_runtime
