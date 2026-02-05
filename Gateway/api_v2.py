"""
Gateway API v2 - HTTP / WebSocket API 接口

版本: v2
更新: 
- 添加 /api 根端点，显示所有可用 API
- 完善路由定义和文档
- 优化错误处理

负责:
- HTTP REST API 端点
- WebSocket 实时通信
- 请求路由与处理
"""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import asyncio
import json
from datetime import datetime

from .session import SessionManager, Session
from .channel import Channel
from .planner import Planner


# ============== 请求/响应模型 ==============

class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., description="用户消息内容", min_length=1)
    session_id: Optional[str] = Field(None, description="会话ID，不提供则自动创建")
    context: Optional[Dict[str, Any]] = Field(None, description="额外上下文信息")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "你好，请介绍一下你自己",
                "session_id": None,
                "context": {}
            }
        }


class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool = Field(..., description="请求是否成功")
    response: Optional[str] = Field(None, description="AI 回复内容")
    session_id: Optional[str] = Field(None, description="会话ID")
    error: Optional[str] = Field(None, description="错误信息")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="响应时间戳")


class APIInfo(BaseModel):
    """API 信息模型"""
    name: str
    version: str
    description: str
    endpoints: List[Dict[str, str]]


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    active_sessions: int
    active_connections: int
    timestamp: str


# ============== Gateway API 类 ==============

class GatewayAPI:
    """
    Gateway API 管理类 v2
    
    管理所有 HTTP 和 WebSocket 端点
    """
    
    VERSION = "2.0.0"
    
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["Gateway API"])
        self.session_manager = SessionManager()
        self.channel = Channel()
        self.planner = Planner()
        self.active_connections: Dict[str, WebSocket] = {}
        
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """配置路由"""
        
        # ========== API 根端点 ==========
        @self.router.get(
            "",
            response_model=APIInfo,
            summary="API 根端点",
            description="获取 API 信息和所有可用端点列表"
        )
        @self.router.get(
            "/",
            response_model=APIInfo,
            include_in_schema=False
        )
        async def api_root():
            """获取 API 信息"""
            return APIInfo(
                name="OpenClaw Gateway API",
                version=self.VERSION,
                description="OpenClaw AI Agent Platform API",
                endpoints=[
                    {"method": "GET", "path": "/api", "description": "API 信息"},
                    {"method": "GET", "path": "/api/health", "description": "健康检查"},
                    {"method": "POST", "path": "/api/chat", "description": "发送聊天消息"},
                    {"method": "GET", "path": "/api/sessions", "description": "获取会话列表"},
                    {"method": "GET", "path": "/api/sessions/{session_id}", "description": "获取会话详情"},
                    {"method": "DELETE", "path": "/api/sessions/{session_id}", "description": "删除会话"},
                    {"method": "WebSocket", "path": "/ws/chat", "description": "WebSocket 实时聊天"}
                ]
            )
        
        # ========== 健康检查 ==========
        @self.router.get(
            "/health",
            response_model=HealthResponse,
            summary="健康检查",
            description="检查服务状态"
        )
        async def health_check():
            """健康检查"""
            return HealthResponse(
                status="healthy",
                service="gateway",
                active_sessions=self.session_manager.count(),
                active_connections=len(self.active_connections),
                timestamp=datetime.now().isoformat()
            )
        
        # ========== 聊天接口 ==========
        @self.router.post(
            "/chat",
            response_model=ChatResponse,
            summary="发送聊天消息",
            description="发送消息到 AI 并获取回复"
        )
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
        
        # ========== 会话管理 ==========
        @self.router.get(
            "/sessions",
            summary="获取会话列表",
            description="列出所有活跃的会话"
        )
        async def list_sessions():
            """列出所有活跃会话"""
            sessions = self.session_manager.list_sessions()
            return {
                "success": True,
                "count": len(sessions),
                "sessions": sessions
            }
        
        @self.router.get(
            "/sessions/{session_id}",
            summary="获取会话详情",
            description="获取指定会话的详细信息"
        )
        async def get_session(session_id: str):
            """获取会话详情"""
            session = self.session_manager.get(session_id)
            if session is None:
                raise HTTPException(
                    status_code=404, 
                    detail={"error": "Session not found", "session_id": session_id}
                )
            return {
                "success": True,
                "session": session.to_dict()
            }
        
        @self.router.delete(
            "/sessions/{session_id}",
            summary="删除会话",
            description="删除指定的会话"
        )
        async def delete_session(session_id: str):
            """删除会话"""
            success = self.session_manager.remove(session_id)
            if not success:
                raise HTTPException(
                    status_code=404, 
                    detail={"error": "Session not found", "session_id": session_id}
                )
            return {
                "success": True,
                "message": f"Session {session_id} deleted"
            }
        
        # ========== 会话历史 ==========
        @self.router.get(
            "/sessions/{session_id}/history",
            summary="获取会话历史",
            description="获取指定会话的消息历史"
        )
        async def get_session_history(session_id: str, limit: int = 50):
            """获取会话历史"""
            session = self.session_manager.get(session_id)
            if session is None:
                raise HTTPException(
                    status_code=404, 
                    detail={"error": "Session not found", "session_id": session_id}
                )
            
            history = session.get_history(limit=limit)
            return {
                "success": True,
                "session_id": session_id,
                "count": len(history),
                "messages": [msg.to_dict() for msg in history]
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
                "session_id": session_id,
                "message": "WebSocket 连接成功"
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
                            "content": response,
                            "timestamp": datetime.now().isoformat()
                        })
                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "content": str(e),
                            "timestamp": datetime.now().isoformat()
                        })
                
                elif message_data.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })
                    
        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Connection error: {str(e)}"
                })
            except:
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
