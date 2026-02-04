"""
LLM Client - Ollama 异步调用实现

负责:
- 与 Ollama 服务建立连接
- 异步消息发送与接收
- 流式响应处理
- 连接状态管理
"""

import asyncio
import json
import aiohttp
from typing import Optional, AsyncGenerator, Dict, Any, List
from dataclasses import dataclass


@dataclass
class ChatMessage:
    """聊天消息数据类"""
    role: str  # 'user', 'assistant', 'system'
    content: str
    images: Optional[List[str]] = None  # Base64 编码的图片列表


@dataclass
class ChatResponse:
    """聊天响应数据类"""
    content: str
    model: str
    done: bool
    total_duration: Optional[int] = None
    eval_count: Optional[int] = None


class OllamaClient:
    """
    Ollama 异步客户端
    
    支持与 Ollama 服务进行异步通信,包括:
    - 普通聊天请求
    - 流式响应
    - 模型管理
    """
    
    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5:7b"
    
    def __init__(
        self,
        host: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 300
    ):
        """
        初始化 Ollama 客户端
        
        Args:
            host: Ollama 服务地址,默认 http://localhost:11434
            model: 使用的模型名称,默认 qwen2.5:7b
            timeout: 请求超时时间(秒)
        """
        self.host = host or self.DEFAULT_HOST
        self.model = model or self.DEFAULT_MODEL
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP 会话"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session
    
    async def close(self) -> None:
        """关闭 HTTP 会话"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def chat(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> ChatResponse:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            model: 模型名称,不指定则使用默认模型
            stream: 是否使用流式响应
            **kwargs: 其他 Ollama API 参数
            
        Returns:
            ChatResponse 对象
        """
        session = await self._get_session()
        
        payload = {
            "model": model or self.model,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    **({"images": msg.images} if msg.images else {})
                }
                for msg in messages
            ],
            "stream": stream,
            **kwargs
        }
        
        url = f"{self.host}/api/chat"
        
        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            data = await response.json()
            
            return ChatResponse(
                content=data.get("message", {}).get("content", ""),
                model=data.get("model", self.model),
                done=data.get("done", True),
                total_duration=data.get("total_duration"),
                eval_count=data.get("eval_count")
            )
    
    async def chat_stream(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        发送流式聊天请求
        
        Args:
            messages: 消息列表
            model: 模型名称
            **kwargs: 其他参数
            
        Yields:
            响应内容片段
        """
        session = await self._get_session()
        
        payload = {
            "model": model or self.model,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    **({"images": msg.images} if msg.images else {})
                }
                for msg in messages
            ],
            "stream": True,
            **kwargs
        }
        
        url = f"{self.host}/api/chat"
        
        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            
            async for line in response.content:
                if line:
                    try:
                        data = json.loads(line.decode('utf-8'))
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        简单文本生成
        
        Args:
            prompt: 输入提示
            model: 模型名称
            system: 系统提示
            **kwargs: 其他参数
            
        Returns:
            生成的文本
        """
        messages = []
        if system:
            messages.append(ChatMessage(role="system", content=system))
        messages.append(ChatMessage(role="user", content=prompt))
        
        response = await self.chat(messages, model=model, **kwargs)
        return response.content
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试与 Ollama 服务的连接
        
        Returns:
            包含连接状态的字典
        """
        try:
            session = await self._get_session()
            
            # 测试 API 端点
            async with session.get(f"{self.host}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    return {
                        "success": True,
                        "host": self.host,
                        "available_models": models,
                        "target_model": self.model,
                        "target_model_available": self.model in models
                    }
                else:
                    return {
                        "success": False,
                        "host": self.host,
                        "error": f"HTTP {response.status}"
                    }
        except aiohttp.ClientError as e:
            return {
                "success": False,
                "host": self.host,
                "error": str(e)
            }
        except Exception as e:
            return {
                "success": False,
                "host": self.host,
                "error": f"Unexpected error: {str(e)}"
            }
    
    async def list_models(self) -> List[str]:
        """
        列出可用模型
        
        Returns:
            模型名称列表
        """
        session = await self._get_session()
        
        async with session.get(f"{self.host}/api/tags") as response:
            response.raise_for_status()
            data = await response.json()
            return [m.get("name", "") for m in data.get("models", [])]
    
    async def pull_model(self, model: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        拉取模型
        
        Args:
            model: 模型名称
            
        Yields:
            下载进度信息
        """
        session = await self._get_session()
        
        payload = {"name": model}
        url = f"{self.host}/api/pull"
        
        async with session.post(url, json=payload) as response:
            response.raise_for_status()
            
            async for line in response.content:
                if line:
                    try:
                        data = json.loads(line.decode('utf-8'))
                        yield data
                    except json.JSONDecodeError:
                        continue


# 便捷函数
async def create_client(
    host: Optional[str] = None,
    model: Optional[str] = None
) -> OllamaClient:
    """创建 Ollama 客户端的便捷函数"""
    return OllamaClient(host=host, model=model)


async def quick_chat(prompt: str, model: Optional[str] = None) -> str:
    """快速聊天的便捷函数"""
    async with OllamaClient(model=model) as client:
        return await client.generate(prompt)
