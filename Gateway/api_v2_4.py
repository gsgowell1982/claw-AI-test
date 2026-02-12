"""
Gateway API v2.4 - 支持多模型选择的 API 接口

版本: v2.4
更新: 
- 支持本地/云端模型切换
- 模型列表和信息查询
- 运行时模型切换
- 模型状态显示

负责:
- HTTP REST API 端点
- WebSocket 实时通信 + 流式响应
- 工具调用与执行
- 模型管理
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
    model: Optional[str] = Field(None, description="指定使用的模型（可选）")


class ChatResponse(BaseModel):
    """聊天响应模型"""
    success: bool
    response: Optional[str] = None
    session_id: Optional[str] = None
    error: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    model_used: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ModelInfo(BaseModel):
    """模型信息"""
    name: str
    display_name: str
    type: str  # local / cloud
    description: str
    is_current: bool = False


class ModelSwitchRequest(BaseModel):
    """模型切换请求"""
    model: str = Field(..., description="要切换到的模型名称")


class APIInfo(BaseModel):
    """API 信息模型"""
    name: str
    version: str
    description: str
    current_model: str
    model_type: str
    endpoints: List[Dict[str, str]]
    tools: List[str]


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    active_sessions: int
    active_connections: int
    llm_status: str
    current_model: str
    model_type: str
    tools_count: int
    timestamp: str


# ============== Gateway API 类 ==============

class GatewayAPIV24:
    """
    Gateway API v2.4 - 支持多模型选择
    """
    
    VERSION = "2.4.0"
    MAX_TOOL_ITERATIONS = 5
    
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["Gateway API v2.4"])
        self.session_manager = SessionManager()
        self.channel = Channel()
        self.runtime = get_runtime()
        self.active_connections: Dict[str, WebSocket] = {}
        self._llm_client = None
        
        self._setup_routes()
    
    def set_llm_client(self, client) -> None:
        """设置 LLM 客户端"""
        self._llm_client = client
        if client:
            model_info = f"{client.model}"
            if hasattr(client, 'is_cloud_model'):
                model_info += f" ({'云端' if client.is_cloud_model else '本地'})"
            logger.info(f"[Gateway] LLM 客户端已配置: {model_info}")
    
    def _get_current_model_info(self) -> Dict[str, str]:
        """获取当前模型信息"""
        if not self._llm_client:
            return {"name": "未配置", "type": "unknown"}
        
        model_type = "cloud" if getattr(self._llm_client, 'is_cloud_model', False) else "local"
        return {
            "name": self._llm_client.model,
            "type": model_type
        }
    
    def _get_system_prompt(self) -> str:
        """获取包含工具描述的系统提示"""
        model_info = self._get_current_model_info()
        model_desc = f"当前使用模型: {model_info['name']} ({'云端' if model_info['type'] == 'cloud' else '本地'})"
        
        base_prompt = f"""你是 OpenClaw，一个智能 AI 助手。{model_desc}

你具备工具调用能力，可以帮助用户完成各种任务。

"""
        tools_prompt = self.runtime.get_system_prompt()
        return base_prompt + tools_prompt
    
    async def _process_with_tools(
        self,
        user_message: str,
        session: Session,
        websocket: Optional[WebSocket] = None,
        model_override: Optional[str] = None
    ) -> tuple[str, List[Dict]]:
        """
        处理带工具调用的对话
        
        Args:
            user_message: 用户消息
            session: 会话对象
            websocket: WebSocket 连接
            model_override: 临时使用的模型
        """
        from LLM.client_v2_4 import ChatMessage
        
        tool_calls_made = []
        iteration = 0
        
        messages = [ChatMessage(role="system", content=self._get_system_prompt())]
        
        for msg in session.get_history(limit=10):
            messages.append(ChatMessage(role=msg.role, content=msg.content))
        
        messages.append(ChatMessage(role="user", content=user_message))
        
        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1
            logger.info(f"[Agent] 迭代 {iteration}, 消息数: {len(messages)}")
            
            full_response = ""
            
            if websocket and iteration == 1:
                await websocket.send_json({
                    "type": "stream_start",
                    "model": model_override or self._llm_client.model,
                    "timestamp": datetime.now().isoformat()
                })
            
            # 使用指定模型或默认模型
            async for chunk in self._llm_client.chat_stream(messages, model=model_override):
                full_response += chunk
                if websocket and iteration == 1:
                    await websocket.send_json({
                        "type": "stream_chunk",
                        "content": chunk
                    })
            
            logger.info(f"[Agent] LLM 响应: {full_response[:200]}...")
            
            # 检查是否包含工具调用标记
            has_tool_marker = "tool_calls" in full_response or '"name"' in full_response
            logger.info(f"[Agent] 响应包含工具调用标记: {has_tool_marker}")
            
            tool_calls = self.runtime.parse_tool_calls(full_response)
            logger.info(f"[Agent] 解析到的工具调用数量: {len(tool_calls)}")
            
            if not tool_calls:
                if websocket and iteration == 1:
                    await websocket.send_json({
                        "type": "stream_end",
                        "timestamp": datetime.now().isoformat()
                    })
                return full_response, tool_calls_made
            
            if websocket and iteration == 1:
                await websocket.send_json({
                    "type": "stream_end",
                    "timestamp": datetime.now().isoformat()
                })
                await websocket.send_json({
                    "type": "tool_call",
                    "tools": [{"name": tc.name, "arguments": tc.arguments} for tc in tool_calls],
                    "timestamp": datetime.now().isoformat()
                })
            
            logger.info(f"[Agent] 检测到 {len(tool_calls)} 个工具调用")
            
            messages.append(ChatMessage(role="assistant", content=full_response))
            
            for tc in tool_calls:
                logger.info(f"[Agent] 执行工具: {tc.name}")
                result = await self.runtime.execute_tool(tc)
                
                tool_calls_made.append({
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": result.result,
                    "success": result.success
                })
                
                result_content = json.dumps(result.result, ensure_ascii=False) if result.success else f"错误: {result.error}"
                messages.append(ChatMessage(
                    role="user",
                    content=f"工具 {tc.name} 执行结果:\n{result_content}\n\n请基于以上结果回答用户的问题。"
                ))
                
                if websocket:
                    await websocket.send_json({
                        "type": "tool_result",
                        "tool": tc.name,
                        "success": result.success,
                        "timestamp": datetime.now().isoformat()
                    })
        
        return "抱歉，处理过程中遇到了问题。请稍后重试。", tool_calls_made
    
    def _setup_routes(self) -> None:
        """配置路由"""
        
        @self.router.get("", response_model=APIInfo)
        @self.router.get("/", include_in_schema=False)
        async def api_root():
            """API 根端点"""
            tools = [t.name for t in self.runtime.list_tools()]
            model_info = self._get_current_model_info()
            
            return APIInfo(
                name="OpenClaw Gateway API",
                version=self.VERSION,
                description="OpenClaw AI Agent Platform v2.4 - 支持多模型选择",
                current_model=model_info["name"],
                model_type=model_info["type"],
                endpoints=[
                    {"method": "GET", "path": "/api", "description": "API 信息"},
                    {"method": "GET", "path": "/api/health", "description": "健康检查"},
                    {"method": "GET", "path": "/api/models", "description": "可用模型列表"},
                    {"method": "POST", "path": "/api/models/switch", "description": "切换模型"},
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
            model_info = self._get_current_model_info()
            llm_status = "未配置"
            
            if self._llm_client:
                try:
                    result = await self._llm_client.test_connection()
                    llm_status = "正常" if result.get("success") else "异常"
                except:
                    llm_status = "异常"
            
            return HealthResponse(
                status="healthy",
                service="gateway",
                active_sessions=self.session_manager.count(),
                active_connections=len(self.active_connections),
                llm_status=llm_status,
                current_model=model_info["name"],
                model_type=model_info["type"],
                tools_count=len(self.runtime.list_tools()),
                timestamp=datetime.now().isoformat()
            )
        
        @self.router.get("/models")
        async def list_models():
            """列出可用模型"""
            if not self._llm_client:
                return {"success": False, "error": "LLM 客户端未配置"}
            
            try:
                # 获取 Ollama 中的可用模型
                available_models = await self._llm_client.list_models()
                current_model = self._llm_client.model
                
                # 获取预设模型配置
                from LLM.client_v2_4 import PRESET_MODELS
                
                models = []
                for m in available_models:
                    name = m.get("name", m) if isinstance(m, dict) else m
                    preset = PRESET_MODELS.get(name)
                    
                    models.append({
                        "name": name,
                        "display_name": preset.display_name if preset else name,
                        "type": preset.type.value if preset else "local",
                        "description": preset.description if preset else "",
                        "is_current": name == current_model,
                        "context_length": preset.context_length if preset else 4096
                    })
                
                return {
                    "success": True,
                    "current_model": current_model,
                    "count": len(models),
                    "models": models
                }
            except Exception as e:
                logger.error(f"[Models] 获取模型列表失败: {e}")
                return {"success": False, "error": str(e)}
        
        @self.router.post("/models/switch")
        async def switch_model(request: ModelSwitchRequest):
            """切换当前模型"""
            if not self._llm_client:
                raise HTTPException(status_code=500, detail="LLM 客户端未配置")
            
            old_model = self._llm_client.model
            
            try:
                # 验证模型是否可用
                available = await self._llm_client.list_models()
                available_names = [m.get("name", m) if isinstance(m, dict) else m for m in available]
                
                if request.model not in available_names:
                    raise HTTPException(
                        status_code=400,
                        detail=f"模型 {request.model} 不可用。可用模型: {available_names}"
                    )
                
                # 切换模型
                self._llm_client.switch_model(request.model)
                
                from LLM.client_v2_4 import PRESET_MODELS
                preset = PRESET_MODELS.get(request.model)
                
                logger.info(f"[Models] 模型切换: {old_model} -> {request.model}")
                
                return {
                    "success": True,
                    "message": f"模型已切换: {old_model} -> {request.model}",
                    "old_model": old_model,
                    "new_model": request.model,
                    "model_type": preset.type.value if preset else "unknown",
                    "display_name": preset.display_name if preset else request.model
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"[Models] 切换失败: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
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
            model_info = self._get_current_model_info()
            return {
                "endpoint": "/api/chat",
                "method": "POST",
                "description": "发送消息到 AI（支持工具调用和模型选择）",
                "current_model": model_info["name"],
                "model_type": model_info["type"],
                "features": [
                    "支持本地/云端模型切换",
                    "自动识别用户意图",
                    "自主决定是否使用工具",
                    "支持文件操作和 GitHub 操作"
                ],
                "parameters": {
                    "message": "消息内容 (必填)",
                    "model": "指定模型 (可选，临时使用)",
                    "enable_tools": "是否启用工具 (默认 true)"
                }
            }
        
        @self.router.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            """处理聊天请求"""
            logger.info(f"[Chat] 收到消息: {request.message[:50]}...")
            start_time = time.time()
            
            try:
                session = self.session_manager.get_or_create(request.session_id)
                
                if not self._llm_client:
                    return ChatResponse(success=False, error="LLM 未配置")
                
                # 确定使用的模型
                model_to_use = request.model  # 可以为 None，使用默认
                
                if request.enable_tools:
                    response_content, tool_calls = await self._process_with_tools(
                        request.message, session, model_override=model_to_use
                    )
                else:
                    from LLM.client_v2_4 import ChatMessage
                    messages = []
                    for msg in session.get_history(limit=10):
                        messages.append(ChatMessage(role=msg.role, content=msg.content))
                    messages.append(ChatMessage(role="user", content=request.message))
                    
                    response = await self._llm_client.chat(messages, model=model_to_use)
                    response_content = response.content
                    tool_calls = []
                
                duration_ms = (time.time() - start_time) * 1000
                
                session.add_message("user", request.message)
                session.add_message("assistant", response_content)
                
                log_chat(
                    session_id=session.session_id,
                    user_message=request.message,
                    assistant_response=response_content,
                    duration_ms=duration_ms,
                    metadata={
                        "tool_calls": tool_calls,
                        "source": "http",
                        "model": model_to_use or self._llm_client.model
                    }
                )
                
                return ChatResponse(
                    success=True,
                    response=response_content,
                    session_id=session.session_id,
                    tool_calls=tool_calls if tool_calls else None,
                    model_used=model_to_use or self._llm_client.model
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
        """WebSocket 处理器 - 支持模型选择"""
        await websocket.accept()
        
        session = self.session_manager.create()
        session_id = session.session_id
        self.active_connections[session_id] = websocket
        
        logger.info(f"[WebSocket] 连接建立: {session_id}")
        
        try:
            model_info = self._get_current_model_info()
            
            await websocket.send_json({
                "type": "connected",
                "session_id": session_id,
                "tools": [t.name for t in self.runtime.list_tools()],
                "current_model": model_info["name"],
                "model_type": model_info["type"],
                "message": f"已连接，当前模型: {model_info['name']} ({'云端' if model_info['type'] == 'cloud' else '本地'})"
            })
            
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                if message_data.get("type") == "message":
                    content = message_data.get("content", "")
                    enable_tools = message_data.get("enable_tools", True)
                    model_override = message_data.get("model")  # 可选的模型指定
                    
                    logger.info(f"[WebSocket:{session_id[:8]}] 收到消息: {content[:50]}...")
                    start_time = time.time()
                    
                    try:
                        if self._llm_client:
                            if enable_tools:
                                response_content, tool_calls = await self._process_with_tools(
                                    content, session, websocket, model_override
                                )
                                
                                if tool_calls:
                                    await websocket.send_json({
                                        "type": "message",
                                        "role": "assistant",
                                        "content": response_content,
                                        "tool_calls": tool_calls,
                                        "model": model_override or self._llm_client.model,
                                        "timestamp": datetime.now().isoformat()
                                    })
                            else:
                                from LLM.client_v2_4 import ChatMessage
                                messages = [ChatMessage(role="user", content=content)]
                                
                                await websocket.send_json({
                                    "type": "stream_start",
                                    "model": model_override or self._llm_client.model
                                })
                                
                                full_response = ""
                                async for chunk in self._llm_client.chat_stream(messages, model=model_override):
                                    full_response += chunk
                                    await websocket.send_json({
                                        "type": "stream_chunk",
                                        "content": chunk
                                    })
                                
                                await websocket.send_json({"type": "stream_end"})
                                response_content = full_response
                                tool_calls = []
                            
                            duration_ms = (time.time() - start_time) * 1000
                            
                            session.add_message("user", content)
                            session.add_message("assistant", response_content)
                            
                            log_chat(
                                session_id=session_id,
                                user_message=content,
                                assistant_response=response_content,
                                duration_ms=duration_ms,
                                metadata={
                                    "tool_calls": tool_calls,
                                    "source": "websocket",
                                    "model": model_override or self._llm_client.model
                                }
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
                
                elif message_data.get("type") == "switch_model":
                    # 处理模型切换请求
                    new_model = message_data.get("model")
                    if new_model and self._llm_client:
                        try:
                            self._llm_client.switch_model(new_model)
                            from LLM.client_v2_4 import PRESET_MODELS
                            preset = PRESET_MODELS.get(new_model)
                            
                            await websocket.send_json({
                                "type": "model_switched",
                                "model": new_model,
                                "model_type": preset.type.value if preset else "unknown",
                                "display_name": preset.display_name if preset else new_model,
                                "message": f"模型已切换到: {new_model}"
                            })
                        except Exception as e:
                            await websocket.send_json({
                                "type": "error",
                                "content": f"模型切换失败: {e}"
                            })
                
                elif message_data.get("type") == "get_models":
                    # 获取模型列表
                    if self._llm_client:
                        try:
                            models = await self._llm_client.list_models()
                            await websocket.send_json({
                                "type": "models_list",
                                "current": self._llm_client.model,
                                "models": models
                            })
                        except Exception as e:
                            await websocket.send_json({
                                "type": "error",
                                "content": f"获取模型列表失败: {e}"
                            })
                
                elif message_data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            logger.info(f"[WebSocket] 连接断开: {session_id}")
        finally:
            if session_id in self.active_connections:
                del self.active_connections[session_id]


def setup_gateway_routes(app) -> GatewayAPIV24:
    """配置 Gateway 路由"""
    gateway = GatewayAPIV24()
    app.include_router(gateway.get_router())
    
    @app.websocket("/ws/chat")
    async def websocket_endpoint(websocket: WebSocket):
        await gateway.websocket_handler(websocket)
    
    return gateway
