"""
Tool Simulator - 模拟模式实现

负责:
- 工具模拟执行
- 测试环境隔离
- 模拟数据生成
"""

from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import random
import string


@dataclass
class SimulationResult:
    """模拟结果"""
    tool_name: str
    parameters: Dict[str, Any]
    simulated_output: Any
    execution_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "simulated_output": self.simulated_output,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata
        }


@dataclass
class SimulationConfig:
    """模拟配置"""
    enabled: bool = True
    delay_ms: float = 0
    random_delay: bool = False
    max_delay_ms: float = 1000
    fail_rate: float = 0.0
    custom_responses: Dict[str, Any] = field(default_factory=dict)


class ToolSimulator:
    """
    工具模拟器
    
    在模拟模式下执行工具,用于测试和开发
    """
    
    def __init__(self, config: Optional[SimulationConfig] = None):
        self.config = config or SimulationConfig()
        self._mock_handlers: Dict[str, Callable] = {}
        self._simulation_history: List[SimulationResult] = []
        
        self._setup_default_mocks()
    
    def _setup_default_mocks(self) -> None:
        """设置默认模拟处理器"""
        # 文件读取模拟
        self.register_mock("file_read", lambda **kw: {
            "content": f"Simulated content of {kw.get('path', 'unknown')}",
            "size": random.randint(100, 10000)
        })
        
        # 文件写入模拟
        self.register_mock("file_write", lambda **kw: {
            "success": True,
            "path": kw.get("path", "unknown"),
            "bytes_written": len(kw.get("content", ""))
        })
        
        # 网络请求模拟
        self.register_mock("http_request", lambda **kw: {
            "status_code": 200,
            "body": {"message": "Simulated response"},
            "headers": {"Content-Type": "application/json"}
        })
        
        # 数据库查询模拟
        self.register_mock("database_query", lambda **kw: {
            "rows": [
                {"id": i, "value": f"simulated_{i}"}
                for i in range(random.randint(1, 10))
            ],
            "count": random.randint(1, 10)
        })
        
        # 系统命令模拟
        self.register_mock("system_command", lambda **kw: {
            "exit_code": 0,
            "stdout": f"Simulated output for: {kw.get('command', '')}",
            "stderr": ""
        })
    
    def register_mock(self, tool_name: str, handler: Callable) -> None:
        """
        注册模拟处理器
        
        Args:
            tool_name: 工具名称
            handler: 模拟处理函数
        """
        self._mock_handlers[tool_name] = handler
    
    def unregister_mock(self, tool_name: str) -> bool:
        """注销模拟处理器"""
        if tool_name in self._mock_handlers:
            del self._mock_handlers[tool_name]
            return True
        return False
    
    async def simulate(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> SimulationResult:
        """
        模拟执行工具
        
        Args:
            tool_name: 工具名称
            parameters: 参数
            
        Returns:
            模拟结果
        """
        import asyncio
        
        params = parameters or {}
        start_time = datetime.now()
        
        # 模拟延迟
        if self.config.delay_ms > 0 or self.config.random_delay:
            delay = self.config.delay_ms
            if self.config.random_delay:
                delay = random.uniform(0, self.config.max_delay_ms)
            await asyncio.sleep(delay / 1000)
        
        # 检查失败率
        if self.config.fail_rate > 0 and random.random() < self.config.fail_rate:
            output = {
                "success": False,
                "error": "Simulated random failure"
            }
        # 检查自定义响应
        elif tool_name in self.config.custom_responses:
            output = self.config.custom_responses[tool_name]
        # 使用模拟处理器
        elif tool_name in self._mock_handlers:
            handler = self._mock_handlers[tool_name]
            try:
                if asyncio.iscoroutinefunction(handler):
                    output = await handler(**params)
                else:
                    output = handler(**params)
            except Exception as e:
                output = {"success": False, "error": str(e)}
        # 默认输出
        else:
            output = self._generate_default_output(tool_name, params)
        
        execution_time = (datetime.now() - start_time).total_seconds() * 1000
        
        result = SimulationResult(
            tool_name=tool_name,
            parameters=params,
            simulated_output=output,
            execution_time_ms=execution_time,
            metadata={
                "simulated": True,
                "timestamp": datetime.now().isoformat()
            }
        )
        
        self._simulation_history.append(result)
        
        return result
    
    def _generate_default_output(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """生成默认输出"""
        return {
            "success": True,
            "tool": tool_name,
            "message": f"Simulated execution of {tool_name}",
            "parameters_received": parameters,
            "simulated_data": self._generate_random_data()
        }
    
    def _generate_random_data(self) -> Dict[str, Any]:
        """生成随机数据"""
        return {
            "id": ''.join(random.choices(string.ascii_lowercase + string.digits, k=8)),
            "value": random.randint(1, 1000),
            "timestamp": datetime.now().isoformat(),
            "status": random.choice(["success", "pending", "completed"])
        }
    
    def set_custom_response(self, tool_name: str, response: Any) -> None:
        """设置自定义响应"""
        self.config.custom_responses[tool_name] = response
    
    def clear_custom_responses(self) -> None:
        """清除自定义响应"""
        self.config.custom_responses.clear()
    
    def get_history(self, tool_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取模拟历史"""
        history = self._simulation_history
        
        if tool_name:
            history = [h for h in history if h.tool_name == tool_name]
        
        return [h.to_dict() for h in history[-limit:]]
    
    def clear_history(self) -> None:
        """清空历史"""
        self._simulation_history.clear()
    
    def enable(self) -> None:
        """启用模拟"""
        self.config.enabled = True
    
    def disable(self) -> None:
        """禁用模拟"""
        self.config.enabled = False
    
    def is_enabled(self) -> bool:
        """检查是否启用"""
        return self.config.enabled
