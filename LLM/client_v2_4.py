"""
LLM Client v2.4 - 支持多模型选择的 Ollama 客户端

版本: v2.4
更新:
- 支持本地模型和云端模型切换
- 预设模型配置
- 运行时模型切换
- 模型信息查询

支持的模型:
- qwen2.5:7b (本地，默认)
- gpt-oss:120b-cloud (云端)
"""

import asyncio
import json
import aiohttp
from typing import Optional, AsyncGenerator, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger("OpenClaw.LLM")


class ModelType(Enum):
    """模型类型"""
    LOCAL = "local"
    CLOUD = "cloud"


@dataclass
class ModelConfig:
    """模型配置"""
    name: str
    display_name: str
    type: ModelType
    description: str
    context_length: int = 4096
    is_default: bool = False


# 预设模型配置
PRESET_MODELS: Dict[str, ModelConfig] = {
    "qwen2.5:7b": ModelConfig(
        name="qwen2.5:7b",
        display_name="Qwen 2.5 7B (本地)",
        type=ModelType.LOCAL,
        description="通义千问 2.5 7B 参数本地模型，响应快速",
        context_length=4096,
        is_default=True
    ),
    "gpt-oss:120b-cloud": ModelConfig(
        name="gpt-oss:120b-cloud",
        display_name="GPT-OSS 120B (云端)",
        type=ModelType.CLOUD,
        description="云端大模型，120B 参数，能力更强",
        context_length=32768,
        is_default=False
    ),
    "qwen2.5:14b": ModelConfig(
        name="qwen2.5:14b",
        display_name="Qwen 2.5 14B (本地)",
        type=ModelType.LOCAL,
        description="通义千问 2.5 14B 参数本地模型",
        context_length=8192,
        is_default=False
    ),
    "llama3:8b": ModelConfig(
        name="llama3:8b",
        display_name="Llama 3 8B (本地)",
        type=ModelType.LOCAL,
        description="Meta Llama 3 8B 参数本地模型",
        context_length=8192,
        is_default=False
    ),
}


@dataclass
class ChatMessage:
    """聊天消息数据类"""
    role: str  # 'user', 'assistant', 'system'
    content: str
    images: Optional[List[str]] = None


@dataclass
class ChatResponse:
    """聊天响应数据类"""
    content: str
    model: str
    done: bool
    total_duration: Optional[int] = None
    eval_count: Optional[int] = None


class OllamaClientV24:
    """
    Ollama 异步客户端 v2.4
    
    支持多模型选择和动态切换
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
            host: Ollama 服务地址
            model: 使用的模型名称
            timeout: 请求超时时间(秒)
        """
        self.host = host or self.DEFAULT_HOST
        self.model = model or self.DEFAULT_MODEL
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # 记录当前模型配置
        self._current_config = PRESET_MODELS.get(self.model)
        
        logger.info(f"[LLM] 初始化客户端: {self.model}")
        if self._current_config:
            logger.info(f"[LLM] 模型类型: {self._current_config.type.value}")
    
    @property
    def current_model(self) -> str:
        """获取当前模型名称"""
        return self.model
    
    @property
    def current_model_config(self) -> Optional[ModelConfig]:
        """获取当前模型配置"""
        return self._current_config
    
    @property
    def is_cloud_model(self) -> bool:
        """是否为云端模型"""
        if self._current_config:
            return self._current_config.type == ModelType.CLOUD
        return "cloud" in self.model.lower()
    
    def switch_model(self, model: str) -> bool:
        """
        切换模型
        
        Args:
            model: 模型名称
            
        Returns:
            是否成功切换
        """
        old_model = self.model
        self.model = model
        self._current_config = PRESET_MODELS.get(model)
        
        logger.info(f"[LLM] 模型切换: {old_model} -> {model}")
        
        return True
    
    @staticmethod
    def list_preset_models() -> List[ModelConfig]:
        """列出所有预设模型"""
        return list(PRESET_MODELS.values())
    
    @staticmethod
    def get_model_config(model: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return PRESET_MODELS.get(model)
    
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
            model: 模型名称
            stream: 是否使用流式响应
            **kwargs: 其他 Ollama API 参数
            
        Returns:
            ChatResponse 对象
        """
        session = await self._get_session()
        use_model = model or self.model
        
        logger.info(f"[LLM] 发送请求到模型: {use_model}")
        
        payload = {
            "model": use_model,
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
                model=data.get("model", use_model),
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
        use_model = model or self.model
        
        logger.info(f"[LLM] 流式请求到模型: {use_model}")
        
        payload = {
            "model": use_model,
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
        """简单文本生成"""
        messages = []
        if system:
            messages.append(ChatMessage(role="system", content=system))
        messages.append(ChatMessage(role="user", content=prompt))
        
        response = await self.chat(messages, model=model, **kwargs)
        return response.content
    
    async def test_connection(self) -> Dict[str, Any]:
        """测试与 Ollama 服务的连接"""
        try:
            session = await self._get_session()
            
            async with session.get(f"{self.host}/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    
                    # 标记哪些是云端模型
                    model_info = []
                    for m in models:
                        config = PRESET_MODELS.get(m)
                        model_info.append({
                            "name": m,
                            "type": config.type.value if config else "unknown",
                            "display_name": config.display_name if config else m
                        })
                    
                    return {
                        "success": True,
                        "host": self.host,
                        "available_models": model_info,
                        "current_model": self.model,
                        "current_model_type": self._current_config.type.value if self._current_config else "unknown",
                        "is_cloud": self.is_cloud_model
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
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型（带类型信息）"""
        session = await self._get_session()
        
        async with session.get(f"{self.host}/api/tags") as response:
            response.raise_for_status()
            data = await response.json()
            
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                config = PRESET_MODELS.get(name)
                models.append({
                    "name": name,
                    "type": config.type.value if config else "local",
                    "display_name": config.display_name if config else name,
                    "description": config.description if config else "",
                    "size": m.get("size", 0)
                })
            
            return models


# 便捷函数
def get_default_model() -> str:
    """获取默认模型"""
    for name, config in PRESET_MODELS.items():
        if config.is_default:
            return name
    return "qwen2.5:7b"


def get_cloud_model() -> str:
    """获取云端模型"""
    for name, config in PRESET_MODELS.items():
        if config.type == ModelType.CLOUD:
            return name
    return "gpt-oss:120b-cloud"


async def create_client(
    host: Optional[str] = None,
    model: Optional[str] = None,
    use_cloud: bool = False
) -> OllamaClientV24:
    """
    创建 Ollama 客户端
    
    Args:
        host: 服务地址
        model: 模型名称
        use_cloud: 是否使用云端模型
        
    Returns:
        OllamaClientV24 实例
    """
    if use_cloud and not model:
        model = get_cloud_model()
    
    return OllamaClientV24(host=host, model=model)
