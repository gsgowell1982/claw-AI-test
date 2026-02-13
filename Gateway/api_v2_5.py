"""
Gateway API v2.5 - 集成记忆系统的 API 接口

版本: v2.5.3
更新: 
- 短期记忆：避免重复工具调用
- 长期记忆：检索历史错误和解决方案
- 语义级记忆检索：基于 Embedding 的相似度搜索
- 智能错误分析：分析失败原因并建议修复
- 智能包管理：区分"包未安装"和"代码导入错误"
- 执行历史自动清理：30天过期

负责:
- HTTP REST API 端点
- WebSocket 实时通信 + 流式响应
- 工具调用与执行（带缓存）
- 记忆管理
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

# 导入记忆模块
from Memory.short_term import get_session_memory, ShortTermMemory
from Memory.long_term import get_long_term_memory, LongTermMemory
from Memory.error_analyzer import analyze_error, ErrorAnalysis

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
    cache_hits: int = 0  # 缓存命中次数
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class APIInfo(BaseModel):
    """API 信息模型"""
    name: str
    version: str
    description: str
    current_model: str
    model_type: str
    features: List[str]
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
    memory_stats: Dict[str, Any]
    timestamp: str


# ============== Gateway API 类 ==============

class GatewayAPIV25:
    """
    Gateway API v2.5 - 集成记忆系统
    """
    
    VERSION = "2.5.3"
    MAX_TOOL_ITERATIONS = 5
    
    def __init__(self):
        self.router = APIRouter(prefix="/api", tags=["Gateway API v2.5"])
        self.session_manager = SessionManager()
        self.channel = Channel()
        self.runtime = get_runtime()
        self.active_connections: Dict[str, WebSocket] = {}
        self._llm_client = None
        self.long_term_memory = get_long_term_memory()
        
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
    
    def _get_system_prompt(self, session_memory: ShortTermMemory, user_query: str = "") -> str:
        """获取包含工具描述和记忆上下文的系统提示"""
        model_info = self._get_current_model_info()
        model_desc = f"当前使用模型: {model_info['name']} ({'云端' if model_info['type'] == 'cloud' else '本地'})"
        
        base_prompt = f"""你是 OpenClaw，一个智能 AI 助手。{model_desc}

你具备工具调用能力和记忆能力，可以帮助用户完成各种任务。

## 重要规则

### 1. 使用记忆避免重复操作
在调用工具之前，请先检查下方的"当前会话已知信息"，如果已经有相关信息，直接使用而不要重复查询。

### 2. Python 包管理规则（非常重要）
- **安装前必须检查**：在安装任何包之前，先使用 `check_package` 检查是否已安装
- **已安装的包不要重复安装**：如果 check_package 返回 installed=true，直接使用该包，不要再调用 install_package
- **区分错误类型**：
  - `missing_package` 错误：包未安装，需要安装
  - `code_error` 或 `import_error`：包已安装，但代码有导入问题，需要修复代码而不是重新安装
- **告知用户包状态**：执行任务前，如果检测到包已安装，应告知用户"所需包已安装，正在执行..."

### 3. 文件转换规则
- 使用 convert_file 工具时，它会自动检查所需包
- 如果包已安装，会直接执行转换
- 如果包未安装，才会提示用户确认安装

### 4. 错误处理
- 如果代码执行失败，仔细阅读错误信息
- `cannot import name 'X' from 'Y'` 通常意味着包已安装，但导入路径或名称有误，需要修复代码
- `No module named 'X'` 才表示包未安装

"""
        # 添加短期记忆上下文
        memory_context = session_memory.get_context_summary()
        if memory_context:
            base_prompt += memory_context + "\n\n"
        
        # 添加语义相关的历史经验（如果有查询）
        if user_query:
            semantic_context = self.long_term_memory.get_relevant_context(user_query, max_items=2)
            if semantic_context:
                base_prompt += semantic_context + "\n\n"
        
        # 添加工具描述
        tools_prompt = self.runtime.get_system_prompt()
        
        return base_prompt + tools_prompt
    
    async def _check_cache_and_execute(
        self,
        tool_call: ToolCall,
        session_memory: ShortTermMemory
    ) -> tuple[Any, bool]:
        """
        检查缓存并执行工具
        
        Returns:
            (结果, 是否命中缓存)
        """
        # 检查缓存
        cached = session_memory.get_cached_result(tool_call.name, tool_call.arguments)
        if cached and cached.success:
            logger.info(f"[Agent] 缓存命中: {tool_call.name}")
            return cached.result, True
        
        # 执行工具
        result = await self.runtime.execute_tool(tool_call)
        
        # 保存到缓存
        session_memory.add_tool_result(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            result=result.result,
            success=result.success
        )
        
        # 如果失败，记录到长期记忆
        if not result.success and result.error:
            error_analysis = analyze_error(result.error)
            self.long_term_memory.record_error(
                error_type=error_analysis.error_type,
                error_message=error_analysis.error_message,
                context={"tool": tool_call.name, "arguments": tool_call.arguments}
            )
        
        # 记录执行历史
        self.long_term_memory.record_execution(
            tool_name=tool_call.name,
            arguments=tool_call.arguments,
            result=result.result,
            success=result.success,
            error_type=getattr(analyze_error(result.error or ""), 'error_type', None) if not result.success else None,
            error_message=result.error,
            duration_ms=result.execution_time_ms
        )
        
        return result, False
    
    def _analyze_and_enhance_error(
        self,
        error_output: str,
        original_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """分析错误并增强错误信息"""
        analysis = analyze_error(error_output, original_code)
        
        # 从长期记忆查找类似错误
        historical = self.long_term_memory.find_similar_error(
            analysis.error_type,
            analysis.error_message
        )
        
        enhanced = {
            "error_type": analysis.error_type,
            "error_message": analysis.error_message,
            "root_cause": analysis.root_cause,
            "suggestion": analysis.suggestion,
            "can_auto_fix": analysis.can_auto_fix,
            "fix_code": analysis.fix_code
        }
        
        if historical:
            enhanced["historical_solution"] = historical.solution
            enhanced["historical_success_rate"] = (
                historical.success_count / 
                max(1, historical.success_count + historical.fail_count)
            )
            enhanced["message"] = (
                f"❌ 执行失败\n\n"
                f"**错误类型**: {analysis.error_type}\n"
                f"**原因**: {analysis.root_cause}\n"
                f"**建议**: {analysis.suggestion}\n\n"
                f"💡 **历史经验**: {historical.solution}\n"
                f"(成功率: {enhanced['historical_success_rate']:.0%})"
            )
        else:
            enhanced["message"] = (
                f"❌ 执行失败\n\n"
                f"**错误类型**: {analysis.error_type}\n"
                f"**原因**: {analysis.root_cause}\n"
                f"**建议**: {analysis.suggestion}"
            )
        
        return enhanced
    
    async def _process_with_tools(
        self,
        user_message: str,
        session: Session,
        session_memory: ShortTermMemory,
        websocket: Optional[WebSocket] = None,
        model_override: Optional[str] = None
    ) -> tuple[str, List[Dict], int]:
        """
        处理带工具调用的对话（集成记忆系统）
        
        Returns:
            (最终回复, 工具调用记录, 缓存命中次数)
        """
        from LLM.client_v2_4 import ChatMessage
        
        tool_calls_made = []
        cache_hits = 0
        iteration = 0
        last_error_code = None  # 记录上次失败的代码，用于智能修复
        
        # 构建初始消息（包含记忆上下文和语义相关经验）
        messages = [ChatMessage(role="system", content=self._get_system_prompt(session_memory, user_message))]
        
        for msg in session.get_history(limit=10):
            messages.append(ChatMessage(role=msg.role, content=msg.content))
        
        messages.append(ChatMessage(role="user", content=user_message))
        
        while iteration < self.MAX_TOOL_ITERATIONS:
            iteration += 1
            logger.info(f"[Agent] 迭代 {iteration}, 消息数: {len(messages)}, 缓存命中: {cache_hits}")
            
            full_response = ""
            
            if websocket and iteration == 1:
                await websocket.send_json({
                    "type": "stream_start",
                    "model": model_override or self._llm_client.model,
                    "timestamp": datetime.now().isoformat()
                })
            
            async for chunk in self._llm_client.chat_stream(messages, model=model_override):
                full_response += chunk
                if websocket and iteration == 1:
                    await websocket.send_json({
                        "type": "stream_chunk",
                        "content": chunk
                    })
            
            logger.info(f"[Agent] LLM 响应: {full_response[:200]}...")
            
            # 检查是否包含工具调用
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
                return full_response, tool_calls_made, cache_hits
            
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
                
                # 使用缓存检查执行
                result, from_cache = await self._check_cache_and_execute(tc, session_memory)
                
                if from_cache:
                    cache_hits += 1
                    # 直接使用缓存结果
                    result_obj = type('Result', (), {
                        'result': result,
                        'success': True,
                        'error': None
                    })()
                else:
                    result_obj = result
                
                tool_calls_made.append({
                    "name": tc.name,
                    "arguments": tc.arguments,
                    "result": result_obj.result if hasattr(result_obj, 'result') else result,
                    "success": result_obj.success if hasattr(result_obj, 'success') else True,
                    "from_cache": from_cache
                })
                
                # 处理结果
                if hasattr(result_obj, 'success') and result_obj.success:
                    result_content = json.dumps(
                        result_obj.result if hasattr(result_obj, 'result') else result,
                        ensure_ascii=False
                    )
                    
                    # 如果是成功修复了之前的错误，记录解决方案
                    if last_error_code and tc.name == "execute_python":
                        # 记录成功的修复
                        self.long_term_memory.learn_from_success(
                            category="code_fix",
                            trigger=f"执行失败后重试",
                            action=f"修改代码: {tc.arguments.get('description', '')}",
                            outcome="执行成功"
                        )
                        last_error_code = None
                else:
                    error_msg = result_obj.error if hasattr(result_obj, 'error') else str(result)
                    
                    # 增强错误分析
                    if tc.name == "execute_python":
                        last_error_code = tc.arguments.get("code", "")
                        enhanced = self._analyze_and_enhance_error(error_msg, last_error_code)
                        result_content = json.dumps(enhanced, ensure_ascii=False)
                    else:
                        result_content = f"错误: {error_msg}"
                
                messages.append(ChatMessage(
                    role="user",
                    content=f"工具 {tc.name} 执行结果:\n{result_content}\n\n请基于以上结果{'分析错误原因并修复代码' if not (result_obj.success if hasattr(result_obj, 'success') else True) else '回答用户的问题'}。"
                ))
                
                if websocket:
                    await websocket.send_json({
                        "type": "tool_result",
                        "tool": tc.name,
                        "success": result_obj.success if hasattr(result_obj, 'success') else True,
                        "from_cache": from_cache,
                        "timestamp": datetime.now().isoformat()
                    })
        
        return "抱歉，处理过程中遇到了问题。请稍后重试。", tool_calls_made, cache_hits
    
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
                description="OpenClaw AI Agent Platform v2.5.3 - 语义级记忆检索",
                current_model=model_info["name"],
                model_type=model_info["type"],
                features=[
                    "短期记忆：避免重复工具调用",
                    "长期记忆：检索历史错误和解决方案",
                    "语义级检索：基于 Embedding 的相似度搜索",
                    "智能错误分析：分析失败原因并建议修复",
                    "自动清理：执行历史 30 天过期",
                    "智能截断：保留代码核心结构",
                    "多模型支持"
                ],
                endpoints=[
                    {"method": "GET", "path": "/api", "description": "API 信息"},
                    {"method": "GET", "path": "/api/health", "description": "健康检查"},
                    {"method": "GET", "path": "/api/models", "description": "可用模型列表"},
                    {"method": "POST", "path": "/api/models/switch", "description": "切换模型"},
                    {"method": "GET", "path": "/api/tools", "description": "可用工具列表"},
                    {"method": "POST", "path": "/api/chat", "description": "发送聊天消息"},
                    {"method": "GET", "path": "/api/memory/stats", "description": "记忆统计"},
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
            
            # 获取记忆统计
            memory_stats = self.long_term_memory.get_error_statistics()
            
            return HealthResponse(
                status="healthy",
                service="gateway",
                active_sessions=self.session_manager.count(),
                active_connections=len(self.active_connections),
                llm_status=llm_status,
                current_model=model_info["name"],
                model_type=model_info["type"],
                tools_count=len(self.runtime.list_tools()),
                memory_stats=memory_stats,
                timestamp=datetime.now().isoformat()
            )
        
        @self.router.get("/memory/stats")
        async def memory_stats():
            """获取记忆统计信息"""
            from Memory.embeddings import get_backend_info
            
            return {
                "success": True,
                "long_term": self.long_term_memory.get_error_statistics(),
                "tool_usage": self.long_term_memory.get_tool_usage_stats(days=7),
                "embedding_backend": get_backend_info(),
                "active_sessions": self.session_manager.count()
            }
        
        @self.router.post("/memory/vacuum")
        async def vacuum_memory():
            """手动触发记忆清理"""
            result = self.long_term_memory.vacuum_old_records()
            return {
                "success": True,
                "message": f"清理完成，删除 {result['deleted_history']} 条过期记录",
                "details": result
            }
        
        @self.router.post("/memory/search")
        async def semantic_search(request: dict):
            """语义搜索历史经验"""
            query = request.get("query", "")
            top_k = request.get("top_k", 5)
            
            if not query:
                raise HTTPException(status_code=400, detail="缺少 query 参数")
            
            experiences = self.long_term_memory.search_experiences_semantic(query, top_k=top_k)
            
            return {
                "success": True,
                "query": query,
                "count": len(experiences),
                "results": [
                    {
                        "id": exp.id,
                        "category": exp.category,
                        "trigger": exp.trigger_pattern,
                        "action": exp.action,
                        "outcome": exp.outcome,
                        "confidence": exp.confidence,
                        "use_count": exp.use_count
                    }
                    for exp in experiences
                ]
            }
        
        @self.router.get("/models")
        async def list_models():
            """列出可用模型"""
            if not self._llm_client:
                return {"success": False, "error": "LLM 客户端未配置"}
            
            try:
                available_models = await self._llm_client.list_models()
                current_model = self._llm_client.model
                
                from LLM.client_v2_4 import PRESET_MODELS
                
                models = []
                for m in available_models:
                    name = m.get("name", m) if isinstance(m, dict) else m
                    preset = PRESET_MODELS.get(name)
                    
                    models.append({
                        "name": name,
                        "display_name": preset.display_name if preset else name,
                        "type": preset.type.value if preset else "local",
                        "is_current": name == current_model
                    })
                
                return {
                    "success": True,
                    "current_model": current_model,
                    "count": len(models),
                    "models": models
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        @self.router.post("/models/switch")
        async def switch_model(request: dict):
            """切换当前模型"""
            if not self._llm_client:
                raise HTTPException(status_code=500, detail="LLM 客户端未配置")
            
            model = request.get("model")
            if not model:
                raise HTTPException(status_code=400, detail="缺少 model 参数")
            
            old_model = self._llm_client.model
            self._llm_client.switch_model(model)
            
            return {
                "success": True,
                "message": f"模型已切换: {old_model} -> {model}",
                "old_model": old_model,
                "new_model": model
            }
        
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
                        "category": t.category
                    }
                    for t in tools
                ]
            }
        
        @self.router.post("/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            """处理聊天请求"""
            logger.info(f"[Chat] 收到消息: {request.message[:50]}...")
            start_time = time.time()
            
            try:
                session = self.session_manager.get_or_create(request.session_id)
                session_memory = get_session_memory(session.session_id)
                
                if not self._llm_client:
                    return ChatResponse(success=False, error="LLM 未配置")
                
                if request.enable_tools:
                    response_content, tool_calls, cache_hits = await self._process_with_tools(
                        request.message, session, session_memory, model_override=request.model
                    )
                else:
                    from LLM.client_v2_4 import ChatMessage
                    messages = []
                    for msg in session.get_history(limit=10):
                        messages.append(ChatMessage(role=msg.role, content=msg.content))
                    messages.append(ChatMessage(role="user", content=request.message))
                    
                    response = await self._llm_client.chat(messages, model=request.model)
                    response_content = response.content
                    tool_calls = []
                    cache_hits = 0
                
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
                        "cache_hits": cache_hits,
                        "source": "http"
                    }
                )
                
                return ChatResponse(
                    success=True,
                    response=response_content,
                    session_id=session.session_id,
                    tool_calls=tool_calls if tool_calls else None,
                    model_used=request.model or self._llm_client.model,
                    cache_hits=cache_hits
                )
            except Exception as e:
                logger.error(f"[Chat] 错误: {str(e)}")
                return ChatResponse(success=False, error=str(e))
    
    def get_router(self) -> APIRouter:
        """获取路由器"""
        return self.router
    
    async def websocket_handler(self, websocket: WebSocket):
        """WebSocket 处理器"""
        await websocket.accept()
        
        session = self.session_manager.create()
        session_id = session.session_id
        session_memory = get_session_memory(session_id)
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
                "features": ["short_term_memory", "long_term_memory", "semantic_search", "auto_cleanup"],
                "message": f"已连接 (v2.5.3)，当前模型: {model_info['name']}"
            })
            
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                
                if message_data.get("type") == "message":
                    content = message_data.get("content", "")
                    enable_tools = message_data.get("enable_tools", True)
                    model_override = message_data.get("model")
                    
                    logger.info(f"[WebSocket:{session_id[:8]}] 收到消息: {content[:50]}...")
                    start_time = time.time()
                    
                    try:
                        if self._llm_client:
                            if enable_tools:
                                response_content, tool_calls, cache_hits = await self._process_with_tools(
                                    content, session, session_memory, websocket, model_override
                                )
                                
                                if tool_calls:
                                    await websocket.send_json({
                                        "type": "message",
                                        "role": "assistant",
                                        "content": response_content,
                                        "tool_calls": tool_calls,
                                        "cache_hits": cache_hits,
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
                                cache_hits = 0
                            
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
                                    "cache_hits": cache_hits,
                                    "source": "websocket"
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
                    new_model = message_data.get("model")
                    if new_model and self._llm_client:
                        self._llm_client.switch_model(new_model)
                        await websocket.send_json({
                            "type": "model_switched",
                            "model": new_model,
                            "message": f"模型已切换到: {new_model}"
                        })
                
                elif message_data.get("type") == "clear_memory":
                    session_memory.clear()
                    await websocket.send_json({
                        "type": "memory_cleared",
                        "message": "会话记忆已清除"
                    })
                
                elif message_data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            logger.info(f"[WebSocket] 连接断开: {session_id}")
        finally:
            if session_id in self.active_connections:
                del self.active_connections[session_id]


def setup_gateway_routes(app) -> GatewayAPIV25:
    """配置 Gateway 路由"""
    gateway = GatewayAPIV25()
    app.include_router(gateway.get_router())
    
    @app.websocket("/ws/chat")
    async def websocket_endpoint(websocket: WebSocket):
        await gateway.websocket_handler(websocket)
    
    return gateway
