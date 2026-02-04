# LLM Layer - Large Language Model Module
"""
LLM 层负责:
- Ollama 异步调用实现
- Prompt 模板管理
- 模型适配器
"""

from .client import OllamaClient
from .prompt_tmplt import PromptTemplate, PromptManager
from .adapter import QwenVLAdapter

__all__ = ['OllamaClient', 'PromptTemplate', 'PromptManager', 'QwenVLAdapter']
