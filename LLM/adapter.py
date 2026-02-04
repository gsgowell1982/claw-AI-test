"""
LLM Adapter - Qwen-VL-30b 专门适配器

负责:
- Qwen-VL 模型的特定配置
- 视觉-语言多模态处理
- 模型参数优化
"""

from typing import Optional, List, Dict, Any, AsyncGenerator
from dataclasses import dataclass
import base64
from pathlib import Path

from .client import OllamaClient, ChatMessage, ChatResponse


@dataclass
class ImageInput:
    """图片输入数据类"""
    data: str  # Base64 编码的图片数据
    mime_type: str = "image/jpeg"
    
    @classmethod
    def from_file(cls, path: str) -> "ImageInput":
        """从文件加载图片"""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")
        
        # 根据扩展名确定 MIME 类型
        ext = file_path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        mime_type = mime_types.get(ext, "image/jpeg")
        
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        
        return cls(data=data, mime_type=mime_type)
    
    @classmethod
    def from_base64(cls, data: str, mime_type: str = "image/jpeg") -> "ImageInput":
        """从 Base64 字符串创建"""
        return cls(data=data, mime_type=mime_type)
    
    @classmethod
    def from_url(cls, url: str) -> "ImageInput":
        """从 URL 加载图片(需要网络请求)"""
        import urllib.request
        
        with urllib.request.urlopen(url) as response:
            data = base64.b64encode(response.read()).decode("utf-8")
            content_type = response.headers.get("Content-Type", "image/jpeg")
        
        return cls(data=data, mime_type=content_type)


class QwenVLAdapter:
    """
    Qwen-VL 模型适配器
    
    专门针对 Qwen-VL (Vision-Language) 模型的适配器,
    支持多模态输入处理
    """
    
    MODEL_NAME = "qwen2.5-vl:32b"
    
    # 推荐的生成参数
    DEFAULT_OPTIONS = {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "num_predict": 2048,
        "repeat_penalty": 1.1
    }
    
    def __init__(
        self,
        client: Optional[OllamaClient] = None,
        host: Optional[str] = None,
        **options
    ):
        """
        初始化适配器
        
        Args:
            client: 可选的 OllamaClient 实例
            host: Ollama 服务地址
            **options: 生成参数覆盖
        """
        if client:
            self.client = client
        else:
            self.client = OllamaClient(host=host, model=self.MODEL_NAME)
        
        self.options = {**self.DEFAULT_OPTIONS, **options}
    
    async def close(self) -> None:
        """关闭客户端连接"""
        await self.client.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def chat(
        self,
        message: str,
        images: Optional[List[ImageInput]] = None,
        history: Optional[List[ChatMessage]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> ChatResponse:
        """
        发送聊天消息
        
        Args:
            message: 用户消息
            images: 可选的图片列表
            history: 对话历史
            system_prompt: 系统提示
            **kwargs: 其他参数
            
        Returns:
            ChatResponse
        """
        messages = []
        
        # 添加系统提示
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        
        # 添加历史消息
        if history:
            messages.extend(history)
        
        # 添加当前消息
        image_data = [img.data for img in images] if images else None
        messages.append(ChatMessage(
            role="user",
            content=message,
            images=image_data
        ))
        
        # 合并参数
        options = {**self.options, **kwargs}
        
        return await self.client.chat(
            messages=messages,
            model=self.MODEL_NAME,
            options=options
        )
    
    async def chat_stream(
        self,
        message: str,
        images: Optional[List[ImageInput]] = None,
        history: Optional[List[ChatMessage]] = None,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天
        
        Args:
            message: 用户消息
            images: 可选的图片列表
            history: 对话历史
            system_prompt: 系统提示
            
        Yields:
            响应内容片段
        """
        messages = []
        
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        
        if history:
            messages.extend(history)
        
        image_data = [img.data for img in images] if images else None
        messages.append(ChatMessage(
            role="user",
            content=message,
            images=image_data
        ))
        
        options = {**self.options, **kwargs}
        
        async for chunk in self.client.chat_stream(
            messages=messages,
            model=self.MODEL_NAME,
            options=options
        ):
            yield chunk
    
    async def analyze_image(
        self,
        image: ImageInput,
        prompt: str = "请描述这张图片的内容。",
        **kwargs
    ) -> str:
        """
        分析图片内容
        
        Args:
            image: 图片输入
            prompt: 分析提示
            
        Returns:
            分析结果
        """
        response = await self.chat(
            message=prompt,
            images=[image],
            **kwargs
        )
        return response.content
    
    async def extract_text_from_image(
        self,
        image: ImageInput,
        **kwargs
    ) -> str:
        """
        从图片中提取文字 (OCR)
        
        Args:
            image: 图片输入
            
        Returns:
            提取的文字
        """
        prompt = "请仔细识别并提取图片中的所有文字内容,保持原有格式。"
        return await self.analyze_image(image, prompt, **kwargs)
    
    async def compare_images(
        self,
        images: List[ImageInput],
        prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        比较多张图片
        
        Args:
            images: 图片列表
            prompt: 比较提示
            
        Returns:
            比较结果
        """
        if not prompt:
            prompt = "请比较这些图片,描述它们的相同点和不同点。"
        
        response = await self.chat(
            message=prompt,
            images=images,
            **kwargs
        )
        return response.content
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        测试连接和模型可用性
        
        Returns:
            测试结果
        """
        result = await self.client.test_connection()
        
        # 添加适配器特定信息
        result["adapter"] = "QwenVLAdapter"
        result["model_name"] = self.MODEL_NAME
        result["options"] = self.options
        
        return result
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息"""
        return {
            "name": self.MODEL_NAME,
            "type": "Vision-Language",
            "capabilities": [
                "text_generation",
                "image_analysis",
                "ocr",
                "multi_image_comparison"
            ],
            "context_length": 32768,
            "options": self.options
        }


# 便捷函数
async def create_qwen_adapter(
    host: Optional[str] = None,
    **options
) -> QwenVLAdapter:
    """创建 Qwen-VL 适配器"""
    return QwenVLAdapter(host=host, **options)


async def quick_image_analysis(
    image_path: str,
    prompt: str = "请描述这张图片。"
) -> str:
    """快速图片分析"""
    image = ImageInput.from_file(image_path)
    async with QwenVLAdapter() as adapter:
        return await adapter.analyze_image(image, prompt)
