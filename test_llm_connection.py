#!/usr/bin/env python3
"""
测试 LLM (Ollama) 连接
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from LLM.client import OllamaClient, ChatMessage


async def test_connection():
    """测试 Ollama 连接"""
    print("=" * 60)
    print("OpenClaw LLM 连接测试")
    print("=" * 60)
    print()
    
    client = OllamaClient()
    
    print(f"目标服务: {client.host}")
    print(f"目标模型: {client.model}")
    print()
    
    # 测试连接
    print("1. 测试服务连接...")
    result = await client.test_connection()
    
    if result.get("success"):
        print(f"   ✅ 连接成功!")
        print(f"   可用模型: {result.get('available_models', [])}")
        print(f"   目标模型可用: {result.get('target_model_available', False)}")
    else:
        print(f"   ❌ 连接失败: {result.get('error')}")
        await client.close()
        return False
    
    print()
    
    # 测试简单对话
    print("2. 测试简单对话...")
    try:
        messages = [
            ChatMessage(role="user", content="你好,请用一句话介绍你自己。")
        ]
        
        response = await client.chat(messages)
        print(f"   ✅ 对话成功!")
        print(f"   回复: {response.content[:200]}...")
    except Exception as e:
        print(f"   ❌ 对话失败: {e}")
        await client.close()
        return False
    
    print()
    
    # 测试流式响应
    print("3. 测试流式响应...")
    try:
        messages = [
            ChatMessage(role="user", content="数数1到5")
        ]
        
        print("   回复: ", end="", flush=True)
        async for chunk in client.chat_stream(messages):
            print(chunk, end="", flush=True)
        print()
        print("   ✅ 流式响应成功!")
    except Exception as e:
        print(f"   ❌ 流式响应失败: {e}")
    
    await client.close()
    
    print()
    print("=" * 60)
    print("测试完成!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
