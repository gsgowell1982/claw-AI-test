"""
Gateway API - HTTP / WebSocket API 接口

负责:
- HTTP REST API 端点
- WebSocket 实时通信
- 请求路由与处理
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import asyncio
import json

from .session import SessionManager, Session
from .channel import Channel
from .planner import Planner


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool
    response: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None


class GatewayAPI:
    """
    Gateway API 管理类
    
    管理所有 HTTP 和 WebSocket 端点
    """
    
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["gateway"])
        self.session_manager = SessionManager()
        self.channel = Channel()
        self.planner = Planner()
        self.active_connections: Dict[str, WebSocket] = {}
        
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """配置路由"""
        
        @self.router.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            """处理聊天请求"""
            try:
                # 获取或创建会话
                session = self.session_manager.get_or_create(request.session_id)
                
                # 转换消息格式
                formatted_message = self.channel.format_input(
                    content=request.message,
                    context=request.context
                )
                
                # 规划执行
                result = await self.planner.process(
                    message=formatted_message,
                    session=session
                )
                
                # 格式化响应
                response_content = self.channel.format_output(result)
                
                return ChatResponse(
                    success=True,
                    response=response_content,
                    session_id=session.session_id
                )
            except Exception as e:
                return ChatResponse(
                    success=False,
                    error=str(e)
                )
        
        @self.router.get("/sessions")
        async def list_sessions():
            """列出所有活跃会话"""
            sessions = self.session_manager.list_sessions()
            return {"sessions": sessions}
        
        @self.router.get("/sessions/{session_id}")
        async def get_session(session_id: str):
            """获取会话详情"""
            session = self.session_manager.get(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            return session.to_dict()
        
        @self.router.delete("/sessions/{session_id}")
        async def delete_session(session_id: str):
            """删除会话"""
            success = self.session_manager.remove(session_id)
            if not success:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"success": True}
        
        @self.router.get("/health")
        async def health_check():
            """健康检查"""
            return {
                "status": "healthy",
                "service": "gateway",
                "active_sessions": self.session_manager.count(),
                "active_connections": len(self.active_connections)
            }
    
    def get_router(self) -> APIRouter:
        """获取路由器"""
        return self.router
    
    async def websocket_handler(self, websocket: WebSocket):
        """
        WebSocket 处理器
        
        Args:
            websocket: WebSocket 连接
        """
        await websocket.accept()
        
        # 创建会话
        session = self.session_manager.create()
        session_id = session.session_id
        self.active_connections[session_id] = websocket
        
        try:
            # 发送连接确认
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id
            })
            
            while True:
                # 接收消息
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                if message_data.get("type") == "message":
                    content = message_data.get("content", "")
                    
                    # 处理消息
                    try:
                        formatted = self.channel.format_input(content=content)
                        result = await self.planner.process(
                            message=formatted,
                            session=session
                        )
                        response = self.channel.format_output(result)
                        
                        await websocket.send_json({
                            "type": "message",
                            "role": "assistant",
                            "content": response
                        })
                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "content": str(e)
                        })
                
                elif message_data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            pass
        finally:
            # 清理连接
            if session_id in self.active_connections:
                del self.active_connections[session_id]
    
    async def broadcast(self, message: Dict[str, Any], exclude: Optional[str] = None):
        """
        广播消息到所有连接
        
        Args:
            message: 要广播的消息
            exclude: 要排除的会话 ID
        """
        for session_id, ws in self.active_connections.items():
            if session_id != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass


def setup_gateway_routes(app) -> GatewayAPI:
    """
    配置 Gateway 路由到 FastAPI 应用
    
    Args:
        app: FastAPI 应用实例
        
    Returns:
        GatewayAPI 实例
    """
    gateway = GatewayAPI()
    app.include_router(gateway.get_router())
    
    @app.websocket("/ws/chat")
    async def websocket_endpoint(websocket: WebSocket):
        await gateway.websocket_handler(websocket)
    
    return gateway
