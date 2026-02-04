"""
Planner - 决策规划器

负责:
- 分析用户请求
- 决策：直接回复 or 调用工具
- 执行计划生成
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import re
import json


class ActionType(Enum):
    """动作类型"""
    DIRECT_RESPONSE = "direct_response"
    TOOL_CALL = "tool_call"
    MULTI_STEP = "multi_step"
    CLARIFICATION = "clarification"


@dataclass
class Action:
    """执行动作"""
    type: ActionType
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """执行计划"""
    actions: List[Action]
    estimated_steps: int
    requires_tools: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


class Planner:
    """
    决策规划器
    
    分析用户输入并决定最佳执行路径
    """
    
    # 工具调用关键词
    TOOL_KEYWORDS = [
        "搜索", "查找", "查询", "计算", "执行", "运行",
        "打开", "创建", "删除", "修改", "分析"
    ]
    
    def __init__(self):
        self._tool_registry = {}
        self._llm_client = None
    
    def set_llm_client(self, client) -> None:
        """设置 LLM 客户端"""
        self._llm_client = client
    
    def register_tool(self, name: str, tool: Any) -> None:
        """注册工具"""
        self._tool_registry[name] = tool
    
    async def process(
        self,
        message: Any,
        session: Any = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        处理消息
        
        Args:
            message: 输入消息
            session: 会话对象
            context: 上下文
            
        Returns:
            处理结果
        """
        # 获取消息内容
        content = self._extract_content(message)
        
        # 分析并创建执行计划
        plan = await self.analyze(content, context)
        
        # 执行计划
        result = await self.execute(plan, session)
        
        return result
    
    def _extract_content(self, message: Any) -> str:
        """提取消息内容"""
        if isinstance(message, str):
            return message
        if hasattr(message, 'content'):
            return message.content if isinstance(message.content, str) else str(message.content)
        return str(message)
    
    async def analyze(
        self,
        content: str,
        context: Optional[Dict[str, Any]] = None
    ) -> ExecutionPlan:
        """
        分析输入并生成执行计划
        
        Args:
            content: 用户输入
            context: 上下文
            
        Returns:
            执行计划
        """
        # 检查是否需要工具调用
        requires_tools = self._check_tool_requirement(content)
        
        if requires_tools:
            # 解析工具调用
            tool_calls = self._parse_tool_calls(content)
            
            if tool_calls:
                actions = [
                    Action(
                        type=ActionType.TOOL_CALL,
                        content=tc
                    )
                    for tc in tool_calls
                ]
                return ExecutionPlan(
                    actions=actions,
                    estimated_steps=len(actions),
                    requires_tools=True
                )
        
        # 默认直接回复
        return ExecutionPlan(
            actions=[
                Action(
                    type=ActionType.DIRECT_RESPONSE,
                    content=content
                )
            ],
            estimated_steps=1,
            requires_tools=False
        )
    
    def _check_tool_requirement(self, content: str) -> bool:
        """检查是否需要工具"""
        content_lower = content.lower()
        return any(kw in content_lower for kw in self.TOOL_KEYWORDS)
    
    def _parse_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """解析工具调用"""
        tool_calls = []
        
        # 尝试解析 JSON 格式的工具调用
        pattern = r'```tool_call\s*(\{.*?\})\s*```'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            try:
                tool_call = json.loads(match)
                if "tool" in tool_call:
                    tool_calls.append(tool_call)
            except json.JSONDecodeError:
                continue
        
        return tool_calls
    
    async def execute(
        self,
        plan: ExecutionPlan,
        session: Any = None
    ) -> Any:
        """
        执行计划
        
        Args:
            plan: 执行计划
            session: 会话
            
        Returns:
            执行结果
        """
        results = []
        
        for action in plan.actions:
            if action.type == ActionType.DIRECT_RESPONSE:
                result = await self._execute_direct_response(action, session)
            elif action.type == ActionType.TOOL_CALL:
                result = await self._execute_tool_call(action, session)
            elif action.type == ActionType.CLARIFICATION:
                result = action.content
            else:
                result = {"error": f"Unknown action type: {action.type}"}
            
            results.append(result)
        
        # 合并结果
        if len(results) == 1:
            return results[0]
        return {"results": results}
    
    async def _execute_direct_response(
        self,
        action: Action,
        session: Any
    ) -> Dict[str, Any]:
        """执行直接回复"""
        if self._llm_client:
            from LLM.client import ChatMessage
            
            messages = []
            
            # 添加历史消息
            if session and hasattr(session, 'messages'):
                for msg in session.get_history(limit=10):
                    messages.append(ChatMessage(
                        role=msg.role,
                        content=msg.content
                    ))
            
            # 添加当前消息
            messages.append(ChatMessage(role="user", content=action.content))
            
            try:
                response = await self._llm_client.chat(messages)
                
                # 保存到会话
                if session:
                    session.add_message("user", action.content)
                    session.add_message("assistant", response.content)
                
                return {"content": response.content}
            except Exception as e:
                return {"content": f"LLM 调用失败: {str(e)}"}
        
        # 无 LLM 客户端时的默认响应
        return {"content": f"收到您的消息: {action.content}"}
    
    async def _execute_tool_call(
        self,
        action: Action,
        session: Any
    ) -> Dict[str, Any]:
        """执行工具调用"""
        tool_data = action.content
        tool_name = tool_data.get("tool")
        parameters = tool_data.get("parameters", {})
        
        if tool_name not in self._tool_registry:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}"
            }
        
        try:
            tool = self._tool_registry[tool_name]
            result = await tool.execute(**parameters)
            return {
                "success": True,
                "tool": tool_name,
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "tool": tool_name,
                "error": str(e)
            }
