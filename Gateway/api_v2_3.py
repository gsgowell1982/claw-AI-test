"""
Gateway API v2.3 - HTTP / WebSocket API 接口

版本: v2.3
更新: 
- 工具调用支持 (Agentic Tool-Use Loop)
- 自动决策是否使用工具
- 工具执行结果回传
- GitHub 集成

负责:
- HTTP REST API 端点
- WebSocket 实时通信 + 流式响应
- 工具调用与执行
"""

from typing import Optional, Dict, Any, List, AsyncGenerator
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import asyncio
import json
import time
from datetime import datetime

from .session import SessionManager, Session
from .channel import Channel
from .runtime_v2_3 import ToolRuntime, get_runtime, ToolCall

import logging
logger = logging.getLogger("OpenClaw.Gateway")

from Test.chat_logger import get_chat_logger, log_chat


# ============== 请求/响应模型 ==============

class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., description="用户消息内容", min_length=1)
    session_id: Optional[str] = Field(None, description="会话ID")
    context: Optional[Dict[str, Any]] = Field(None, description="额外上下文")
    enable_tools: bool = Field(True, description="是否启用工具调用")


class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool
    response: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class APIInfo(BaseModel):
    """API 信息模型"""
    name: str
    version: str
    description: str
    endpoints: List[Dict[str, str]]
    tools: List[str]


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    active_sessions: int
    active_connections: int
    llm_status: str
    tools_count: int
    timestamp: str


# ============== Gateway API 类 ==============

class GatewayAPI:
    """
    Gateway API v2.3 - 支持工具调用
    """
    
    VERSION = "2.3.0"
    MAX_TOOL_ITERATIONS = 5  # 最大工具调用轮次
    
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["Gateway API"])
        self.session_manager = SessionManager()
        self.channel = Channel()
        self.runtime = get_runtime()
        self.active_connections: Dict[str, WebSocket] = {}
        self._llm_client = None
        
        self._setup_routes()
    
    def set_llm_client(self, client) -> None:
        """设置 LLM 客户端"""
        self._llm_client = client
        logger.info(f"[Gateway] LLM 客户端已配置: {client.model if client else 'None'}")
    
    def _get_system_prompt(self) -> str:
        """获取包含工具描述的系统提示"""
        base_prompt = """你是 OpenClaw，一个智能 AI 助手。你具备工具调用能力，可以帮助用户完成各种任务。

"""
        tools_prompt = self.runtime.get_system_prompt()
        return base_prompt + tools_prompt
    
    async def _process_with_tools(
        self,
        user_message: str,
        session: Session,
        websocket: Optional[WebSocket] = None
    ) -> tuple[str, List[Dict]]:
        """
        处理带工具调用的对话
        
        实现 Agentic Tool-Use Loop:
        1. 发送用户消息给 LLM
        2. 检查 LLM 响应是否包含工具调用
        3. 如果有，执行工具并将结果回传给 LLM
        4. 重复直到 LLM 给出最终回复
        
        Returns:
            (最终回复, 工具调用记录)
        """
        from LLM.client import ChatMessage
        
        tool_calls_made = []
        iteration = 0
        
        # 构建初始消息
        messages = [ChatMessage(role="system", content=self._get_system_prompt())]
        
        # 添加历史消息
        for msg in session.get_history(limit=10):
            messages.append(ChatMessage(role=msg.role, content=msg.content))
        
        # 添加当前用户消息
        messages.append(ChatMessage(role="user", content=user_message))
        
        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1
            logger.info(f"[Agent] 迭代 {iteration}, 消息数: {len(messages)}")
            
            # 调用 LLM
            full_response = ""
            
            if websocket and iteration == 1:
                # 第一次迭代使用流式响应
                await websocket.send_json({
                    "type": "stream_start",
                    "timestamp": datetime.now().isoformat()
                })
            
            async for chunk in self._llm_client.chat_stream(messages):
                full_response += chunk
                if websocket and iteration == 1:
                    await websocket.send_json({
                        "type": "stream_chunk",
                        "content": chunk
                    })
            
            logger.info(f"[Agent] LLM 响应: {full_response[:200]}...")
            
            # 检查是否有工具调用
            tool_calls = self.runtime.parse_tool_calls(full_response)
            
            if not tool_calls:
                # 没有工具调用，返回最终结果
                if websocket and iteration == 1:
                    await websocket.send_json({
                        "type": "stream_end",
                        "timestamp": datetime.now().isoformat()
                    })
                return full_response, tool_calls_made
            
            # 有工具调用，先结束当前流
            if websocket and iteration == 1:
                await websocket.send_json({
                    "type": "stream_end",
                    "timestamp": datetime.now().isoformat()
                })
                # 发送工具调用通知
                await websocket.send_json({
                    "type": "tool_call",
                    "tools": [{"name": tc.name, "arguments": tc.arguments} for tc in tool_calls],
                    "timestamp": datetime.now().isoformat()
                })
            
            # 执行工具
            logger.info(f"[Agent] 检测到 {len(tool_calls)} 个工具调用")
            
            # 添加助手消息（包含工具调用意图）
            messages.append(ChatMessage(role="assistant", content=full_response))
            
            # 执行每个工具并添加结果
            for tc in tool_calls:
                logger.info(f"[Agent] 执行工具: {tc.name}")
                result = await self.runtime.execute_tool(tc)
                
                tool_calls_made.append({
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": result.result,
                    "success": result.success
                })
                
                # 添加工具结果消息
                result_content = json.dumps(result.result, ensure_ascii=False) if result.success else f"错误: {result.error}"
                messages.append(ChatMessage(
                    role="user",  # Ollama 用 user 角色传递工具结果
                    content=f"工具 {tc.name} 执行结果:\n{result_content}\n\n请基于以上结果回答用户的问题。"
                ))
                
                if websocket:
                    await websocket.send_json({
                        "type": "tool_result",
                        "tool": tc.name,
                        "success": result.success,
                        "timestamp": datetime.now().isoformat()
                    })
        
        # 达到最大迭代次数
        return "抱歉，处理过程中遇到了问题。请稍后重试。", tool_calls_made
    
    def _setup_routes(self) -> None:
        """配置路由"""
        
        @self.router.get("", response_model=APIInfo)
        @self.router.get("/", include_in_schema=False)
        async def api_root():
            """API 根端点"""
            tools = [t.name for t in self.runtime.list_tools()]
            return APIInfo(
                name="OpenClaw Gateway API",
                version=self.VERSION,
                description="OpenClaw AI Agent Platform - 支持工具调用",
                endpoints=[
                    {"method": "GET", "path": "/api", "description": "API 信息"},
                    {"method": "GET", "path": "/api/health", "description": "健康检查"},
                    {"method": "GET", "path": "/api/tools", "description": "可用工具列表"},
                    {"method": "POST", "path": "/api/chat", "description": "发送聊天消息"},
                    {"method": "GET", "path": "/api/logs", "description": "聊天日志"},
                    {"method": "WebSocket", "path": "/ws/chat", "description": "实时聊天"}
                ],
                tools=tools
            )
        
        @self.router.get("/health", response_model=HealthResponse)
        async def health_check():
            """健康检查"""
            llm_status = "未配置"
            if self._llm_client:
                try:
                    result = await self._llm_client.test_connection()
                    llm_status = "正常" if result.get("success") else f"异常"
                except:
                    llm_status = "异常"
            
            return HealthResponse(
                status="healthy",
                service="gateway",
                active_sessions=self.session_manager.count(),
                active_connections=len(self.active_connections),
                llm_status=llm_status,
                tools_count=len(self.runtime.list_tools()),
                timestamp=datetime.now().isoformat()
            )
        
        @self.router.get("/tools")
        async def list_tools():
            """列出可用工具"""
            tools = self.runtime.list_tools()
            return {
                "success": True,
                "count": len(tools),
                "tools": [
                    {
                        "name": t.name,
                        "description": t.description,
                        "category": t.category,
                        "parameters": [
                            {"name": p.name, "type": p.type.value, "required": p.required}
                            for p in t.parameters
                        ]
                    }
                    for t in tools
                ]
            }
        
        @self.router.get("/chat")
        async def chat_info():
            """聊天接口说明"""
            return {
                "endpoint": "/api/chat",
                "method": "POST",
                "description": "发送消息到 AI（支持工具调用）",
                "features": [
                    "自动识别用户意图",
                    "自主决定是否使用工具",
                    "支持文件操作和 GitHub 操作"
                ]
            }
        
        @self.router.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            """处理聊天请求（支持工具调用）"""
            logger.info(f"[Chat] 收到消息: {request.message[:50]}...")
            start_time = time.time()
            
            try:
                session = self.session_manager.get_or_create(request.session_id)
                
                if not self._llm_client:
                    return ChatResponse(success=False, error="LLM 未配置")
                
                if request.enable_tools:
                    response_content, tool_calls = await self._process_with_tools(
                        request.message, session
                    )
                else:
                    # 不使用工具的简单对话
                    from LLM.client import ChatMessage
                    messages = []
                    for msg in session.get_history(limit=10):
                        messages.append(ChatMessage(role=msg.role, content=msg.content))
                    messages.append(ChatMessage(role="user", content=request.message))
                    
                    response = await self._llm_client.chat(messages)
                    response_content = response.content
                    tool_calls = []
                
                duration_ms = (time.time() - start_time) * 1000
                
                # 保存到会话
                session.add_message("user", request.message)
                session.add_message("assistant", response_content)
                
                # 记录日志
                log_chat(
                    session_id=session.session_id,
                    user_message=request.message,
                    assistant_response=response_content,
                    duration_ms=duration_ms,
                    metadata={"tool_calls": tool_calls, "source": "http"}
                )
                
                return ChatResponse(
                    success=True,
                    response=response_content,
                    session_id=session.session_id,
                    tool_calls=tool_calls if tool_calls else None
                )
            except Exception as e:
                logger.error(f"[Chat] 错误: {str(e)}")
                return ChatResponse(success=False, error=str(e))
        
        @self.router.get("/logs")
        async def get_chat_logs(limit: int = 20):
            """获取聊天日志"""
            chat_logger = get_chat_logger()
            return {
                "success": True,
                "stats": chat_logger.get_stats(),
                "recent": chat_logger.get_recent(limit=limit)
            }
        
        @self.router.get("/sessions")
        async def list_sessions():
            """获取会话列表"""
            sessions = self.session_manager.list_sessions()
            return {"success": True, "count": len(sessions), "sessions": sessions}
        
        @self.router.delete("/sessions/{session_id}")
        async def delete_session(session_id: str):
            """删除会话"""
            success = self.session_manager.remove(session_id)
            if not success:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"success": True}
    
    def get_router(self) -> APIRouter:
        """获取路由器"""
        return self.router
    
    async def websocket_handler(self, websocket: WebSocket):
        """WebSocket 处理器 - 支持工具调用"""
        await websocket.accept()
        
        session = self.session_manager.create()
        session_id = session.session_id
        self.active_connections[session_id] = websocket
        
        logger.info(f"[WebSocket] 连接建立: {session_id}")
        
        try:
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "tools": [t.name for t in self.runtime.list_tools()],
                "message": "已连接，支持工具调用"
            })
            
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                if message_data.get("type") == "message":
                    content = message_data.get("content", "")
                    enable_tools = message_data.get("enable_tools", True)
                    
                    logger.info(f"[WebSocket:{session_id[:8]}] 收到消息: {content[:50]}...")
                    start_time = time.time()
                    
                    try:
                        if self._llm_client:
                            if enable_tools:
                                response_content, tool_calls = await self._process_with_tools(
                                    content, session, websocket
                                )
                                
                                # 如果有工具调用，发送最终结果
                                if tool_calls:
                                    await websocket.send_json({
                                        "type": "message",
                                        "role": "assistant",
                                        "content": response_content,
                                        "tool_calls": tool_calls,
                                        "timestamp": datetime.now().isoformat()
                                    })
                            else:
                                # 不使用工具
                                from LLM.client import ChatMessage
                                messages = [ChatMessage(role="user", content=content)]
                                
                                await websocket.send_json({"type": "stream_start"})
                                
                                full_response = ""
                                async for chunk in self._llm_client.chat_stream(messages):
                                    full_response += chunk
                                    await websocket.send_json({
                                        "type": "stream_chunk",
                                        "content": chunk
                                    })
                                
                                await websocket.send_json({"type": "stream_end"})
                                response_content = full_response
                                tool_calls = []
                            
                            duration_ms = (time.time() - start_time) * 1000
                            
                            # 保存
                            session.add_message("user", content)
                            session.add_message("assistant", response_content)
                            
                            log_chat(
                                session_id=session_id,
                                user_message=content,
                                assistant_response=response_content,
                                duration_ms=duration_ms,
                                metadata={"tool_calls": tool_calls, "source": "websocket"}
                            )
                        else:
                            await websocket.send_json({
                                "type": "error",
                                "content": "LLM 未配置"
                            })
                    except Exception as e:
                        logger.error(f"[WebSocket] 错误: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "content": str(e)
                        })
                
                elif message_data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            logger.info(f"[WebSocket] 连接断开: {session_id}")
        finally:
            if session_id in self.active_connections:
                del self.active_connections[session_id]


def setup_gateway_routes(app) -> GatewayAPI:
    """配置 Gateway 路由"""
    gateway = GatewayAPI()
    app.include_router(gateway.get_router())
    
    @app.websocket("/ws/chat")
    async def websocket_endpoint(websocket: WebSocket):
        await gateway.websocket_handler(websocket)
    
    return gateway
