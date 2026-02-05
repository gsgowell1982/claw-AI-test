"""
Gateway API v2.2 - HTTP / WebSocket API 接口

版本: v2.2.1
更新: 
- 实现流式响应 (Streaming)
- 添加完整的交互日志
- 保存聊天记录到 Test 目录
- 优化 WebSocket 处理
- 支持 LLM 实时输出

负责:
- HTTP REST API 端点
- WebSocket 实时通信 + 流式响应
- 请求路由与处理
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
from .planner import Planner

# 导入日志模块
import logging
logger = logging.getLogger("OpenClaw.Gateway")

# 导入聊天日志记录器
from Test.chat_logger import get_chat_logger, log_chat


# ============== 请求/响应模型 ==============

class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., description="用户消息内容", min_length=1)
    session_id: Optional[str] = Field(None, description="会话ID，不提供则自动创建")
    context: Optional[Dict[str, Any]] = Field(None, description="额外上下文信息")
    stream: bool = Field(False, description="是否使用流式响应")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "你好，请介绍一下你自己",
                "session_id": None,
                "context": {},
                "stream": False
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
    llm_status: str
    timestamp: str


# ============== Gateway API 类 ==============

class GatewayAPI:
    """
    Gateway API 管理类 v2.2
    
    支持流式响应和完整日志
    """
    
    VERSION = "2.2.0"
    
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["Gateway API"])
        self.session_manager = SessionManager()
        self.channel = Channel()
        self.planner = Planner()
        self.active_connections: Dict[str, WebSocket] = {}
        self._llm_client = None
        
        self._setup_routes()
    
    def set_llm_client(self, client) -> None:
        """设置 LLM 客户端"""
        self._llm_client = client
        self.planner.set_llm_client(client)
        logger.info(f"LLM 客户端已配置: {client.model if client else 'None'}")
    
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
                description="OpenClaw AI Agent Platform API - 支持流式响应",
                endpoints=[
                    {"method": "GET", "path": "/api", "description": "API 信息"},
                    {"method": "GET", "path": "/api/health", "description": "健康检查"},
                    {"method": "GET", "path": "/api/chat", "description": "聊天接口说明"},
                    {"method": "POST", "path": "/api/chat", "description": "发送聊天消息"},
                    {"method": "POST", "path": "/api/chat/stream", "description": "流式聊天 (SSE)"},
                    {"method": "GET", "path": "/api/sessions", "description": "获取会话列表"},
                    {"method": "GET", "path": "/api/sessions/{session_id}", "description": "获取会话详情"},
                    {"method": "GET", "path": "/api/sessions/{session_id}/history", "description": "获取会话历史"},
                    {"method": "DELETE", "path": "/api/sessions/{session_id}", "description": "删除会话"},
                    {"method": "WebSocket", "path": "/ws/chat", "description": "WebSocket 实时聊天 (支持流式)"}
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
            llm_status = "未配置"
            if self._llm_client:
                try:
                    result = await self._llm_client.test_connection()
                    llm_status = "正常" if result.get("success") else f"异常: {result.get('error')}"
                except Exception as e:
                    llm_status = f"异常: {str(e)}"
            
            return HealthResponse(
                status="healthy",
                service="gateway",
                active_sessions=self.session_manager.count(),
                active_connections=len(self.active_connections),
                llm_status=llm_status,
                timestamp=datetime.now().isoformat()
            )
        
        # ========== 聊天接口说明 ==========
        @self.router.get(
            "/chat",
            summary="聊天接口说明",
            description="获取聊天接口的使用说明（实际聊天请使用 POST 方法）"
        )
        async def chat_info():
            """聊天接口使用说明"""
            return {
                "endpoint": "/api/chat",
                "method": "POST",
                "description": "发送消息到 AI 并获取回复",
                "streaming": {
                    "websocket": "ws://localhost:8000/ws/chat",
                    "sse": "POST /api/chat/stream"
                },
                "request_body": {
                    "message": "(必填) 用户消息内容",
                    "session_id": "(可选) 会话ID",
                    "context": "(可选) 额外上下文",
                    "stream": "(可选) 是否流式响应"
                },
                "example": {
                    "curl": 'curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d \'{"message": "你好"}\''
                }
            }
        
        # ========== 普通聊天接口 ==========
        @self.router.post(
            "/chat",
            response_model=ChatResponse,
            summary="发送聊天消息",
            description="发送消息到 AI 并获取回复"
        )
        async def chat(request: ChatRequest):
            """处理聊天请求"""
            logger.info(f"[Chat] 收到消息: {request.message[:50]}...")
            start_time = time.time()
            
            try:
                # 获取或创建会话
                session = self.session_manager.get_or_create(request.session_id)
                logger.info(f"[Chat] 会话ID: {session.session_id}")
                
                # 调用 LLM
                if self._llm_client:
                    from LLM.client import ChatMessage
                    
                    # 构建消息历史
                    messages = []
                    for msg in session.get_history(limit=10):
                        messages.append(ChatMessage(role=msg.role, content=msg.content))
                    messages.append(ChatMessage(role="user", content=request.message))
                    
                    logger.info(f"[Chat] 调用 LLM, 消息数: {len(messages)}")
                    
                    # 调用 LLM
                    response = await self._llm_client.chat(messages)
                    response_content = response.content
                    
                    duration_ms = (time.time() - start_time) * 1000
                    logger.info(f"[Chat] LLM 回复: {response_content[:100]}... (耗时: {duration_ms:.0f}ms)")
                    
                    # 保存到会话
                    session.add_message("user", request.message)
                    session.add_message("assistant", response_content)
                    
                    # 保存到 Test 目录日志
                    log_chat(
                        session_id=session.session_id,
                        user_message=request.message,
                        assistant_response=response_content,
                        duration_ms=duration_ms,
                        metadata={"source": "http"}
                    )
                else:
                    response_content = f"[LLM 未配置] 收到您的消息: {request.message}"
                    logger.warning("[Chat] LLM 客户端未配置")
                
                return ChatResponse(
                    success=True,
                    response=response_content,
                    session_id=session.session_id
                )
            except Exception as e:
                logger.error(f"[Chat] 错误: {str(e)}")
                return ChatResponse(
                    success=False,
                    error=str(e)
                )
        
        # ========== 流式聊天接口 (SSE) ==========
        @self.router.post(
            "/chat/stream",
            summary="流式聊天 (SSE)",
            description="发送消息并以 Server-Sent Events 方式接收流式回复"
        )
        async def chat_stream(request: ChatRequest):
            """流式聊天"""
            logger.info(f"[Stream] 收到消息: {request.message[:50]}...")
            
            async def generate():
                try:
                    session = self.session_manager.get_or_create(request.session_id)
                    
                    if self._llm_client:
                        from LLM.client import ChatMessage
                        
                        messages = []
                        for msg in session.get_history(limit=10):
                            messages.append(ChatMessage(role=msg.role, content=msg.content))
                        messages.append(ChatMessage(role="user", content=request.message))
                        
                        logger.info(f"[Stream] 开始流式生成...")
                        
                        full_response = ""
                        async for chunk in self._llm_client.chat_stream(messages):
                            full_response += chunk
                            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                        
                        # 保存到会话
                        session.add_message("user", request.message)
                        session.add_message("assistant", full_response)
                        
                        logger.info(f"[Stream] 生成完成, 总长度: {len(full_response)}")
                        yield f"data: {json.dumps({'type': 'done', 'session_id': session.session_id})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'content': 'LLM 未配置'})}\n\n"
                except Exception as e:
                    logger.error(f"[Stream] 错误: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive"
                }
            )
        
        # ========== 会话管理 ==========
        @self.router.get(
            "/sessions",
            summary="获取会话列表"
        )
        async def list_sessions():
            """列出所有活跃会话"""
            sessions = self.session_manager.list_sessions()
            return {"success": True, "count": len(sessions), "sessions": sessions}
        
        @self.router.get(
            "/sessions/{session_id}",
            summary="获取会话详情"
        )
        async def get_session(session_id: str):
            """获取会话详情"""
            session = self.session_manager.get(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"success": True, "session": session.to_dict()}
        
        @self.router.get(
            "/sessions/{session_id}/history",
            summary="获取会话历史"
        )
        async def get_session_history(session_id: str, limit: int = 50):
            """获取会话历史"""
            session = self.session_manager.get(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found")
            history = session.get_history(limit=limit)
            return {
                "success": True,
                "session_id": session_id,
                "count": len(history),
                "messages": [msg.to_dict() for msg in history]
            }
        
        @self.router.delete(
            "/sessions/{session_id}",
            summary="删除会话"
        )
        async def delete_session(session_id: str):
            """删除会话"""
            success = self.session_manager.remove(session_id)
            if not success:
                raise HTTPException(status_code=404, detail="Session not found")
            return {"success": True, "message": f"Session {session_id} deleted"}
        
        # ========== 聊天日志 ==========
        @self.router.get(
            "/logs",
            summary="获取聊天日志",
            description="获取保存在 Test 目录的聊天交互日志"
        )
        async def get_chat_logs(limit: int = 20):
            """获取聊天日志"""
            chat_logger = get_chat_logger()
            return {
                "success": True,
                "stats": chat_logger.get_stats(),
                "recent": chat_logger.get_recent(limit=limit)
            }
    
    def get_router(self) -> APIRouter:
        """获取路由器"""
        return self.router
    
    async def websocket_handler(self, websocket: WebSocket):
        """
        WebSocket 处理器 - 支持流式响应
        """
        await websocket.accept()
        
        session = self.session_manager.create()
        session_id = session.session_id
        self.active_connections[session_id] = websocket
        
        logger.info(f"[WebSocket] 连接建立: {session_id}")
        
        try:
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "message": "WebSocket 连接成功"
            })
            
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                if message_data.get("type") == "message":
                    content = message_data.get("content", "")
                    logger.info(f"[WebSocket:{session_id[:8]}] 收到消息: {content[:50]}...")
                    
                    try:
                        if self._llm_client:
                            from LLM.client import ChatMessage
                            
                            # 构建消息
                            messages = []
                            for msg in session.get_history(limit=10):
                                messages.append(ChatMessage(role=msg.role, content=msg.content))
                            messages.append(ChatMessage(role="user", content=content))
                            
                            # 发送流式开始信号
                            await websocket.send_json({
                                "type": "stream_start",
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            logger.info(f"[WebSocket:{session_id[:8]}] 开始流式生成...")
                            
                            # 流式生成
                            full_response = ""
                            token_count = 0
                            start_time = time.time()
                            
                            async for chunk in self._llm_client.chat_stream(messages):
                                full_response += chunk
                                token_count += 1
                                await websocket.send_json({
                                    "type": "stream_chunk",
                                    "content": chunk
                                })
                            
                            # 计算耗时
                            duration_ms = (time.time() - start_time) * 1000
                            
                            # 发送流式结束信号
                            await websocket.send_json({
                                "type": "stream_end",
                                "timestamp": datetime.now().isoformat()
                            })
                            
                            logger.info(f"[WebSocket:{session_id[:8]}] 生成完成, chunks: {token_count}, 长度: {len(full_response)}, 耗时: {duration_ms:.0f}ms")
                            
                            # 保存到会话
                            session.add_message("user", content)
                            session.add_message("assistant", full_response)
                            
                            # 保存到 Test 目录日志
                            log_chat(
                                session_id=session_id,
                                user_message=content,
                                assistant_response=full_response,
                                duration_ms=duration_ms,
                                chunks=token_count,
                                metadata={"source": "websocket"}
                            )
                        else:
                            # LLM 未配置时的默认响应
                            await websocket.send_json({
                                "type": "message",
                                "role": "assistant",
                                "content": f"[LLM 未配置] 收到消息: {content}",
                                "timestamp": datetime.now().isoformat()
                            })
                    except Exception as e:
                        logger.error(f"[WebSocket:{session_id[:8]}] 处理错误: {str(e)}")
                        await websocket.send_json({
                            "type": "error",
                            "content": str(e),
                            "timestamp": datetime.now().isoformat()
                        })
                
                elif message_data.get("type") == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})
                    
        except WebSocketDisconnect:
            logger.info(f"[WebSocket] 连接断开: {session_id}")
        except Exception as e:
            logger.error(f"[WebSocket] 错误: {str(e)}")
        finally:
            if session_id in self.active_connections:
                del self.active_connections[session_id]
    
    async def broadcast(self, message: Dict[str, Any], exclude: Optional[str] = None):
        """广播消息"""
        for session_id, ws in self.active_connections.items():
            if session_id != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass


def setup_gateway_routes(app) -> GatewayAPI:
    """配置 Gateway 路由"""
    gateway = GatewayAPI()
    app.include_router(gateway.get_router())
    
    @app.websocket("/ws/chat")
    async def websocket_endpoint(websocket: WebSocket):
        await gateway.websocket_handler(websocket)
    
    return gateway
