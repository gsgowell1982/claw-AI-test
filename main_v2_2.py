#!/usr/bin/env python3
"""
OpenClaw - 项目总入口 v2.2

版本: v2.2
更新:
- 实现完整的流式对话链路
- 添加详细的交互日志
- 修复 aiohttp session 未关闭警告
- 优化服务启动和关闭流程

启动 OpenClaw 应用,包括:
- UI Web 服务器
- Gateway API (支持流式响应)
- LLM 连接管理
"""

import asyncio
import sys
import signal
from pathlib import Path
from contextlib import asynccontextmanager

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_banner():
    """打印启动横幅"""
    banner = """
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║     ██████╗ ██████╗ ███████╗███╗   ██╗ ██████╗██╗      █████╗ ║
║    ██╔═══██╗██╔══██╗██╔════╝████╗  ██║██╔════╝██║     ██╔══██╗║
║    ██║   ██║██████╔╝█████╗  ██╔██╗ ██║██║     ██║     ███████║║
║    ██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║██║     ██║     ██╔══██║║
║    ╚██████╔╝██║     ███████╗██║ ╚████║╚██████╗███████╗██║  ██║║
║     ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝ ╚═════╝╚══════╝╚═╝  ╚═╝║
║                                                               ║
║              AI Agent Platform v2.2.0 (Streaming)             ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_stage_info():
    """打印阶段信息"""
    print("=" * 60)
    print("【第二阶段】全链路对话 (End-to-End Chat Loop)")
    print("=" * 60)
    print()


async def run_verification():
    """运行阶段验证"""
    from Test.stage_tracker import StageTracker
    
    print("正在运行验证...")
    print()
    
    tracker = StageTracker(str(PROJECT_ROOT))
    
    result = await tracker.run_stage1_verification(
        check_ui=False,
        check_llm=True
    )
    
    tracker.write_verification_log(result)
    print(result.to_markdown())
    print()
    
    return result


# 全局 LLM 客户端引用 (用于优雅关闭)
_llm_client = None


def create_app():
    """创建 FastAPI 应用"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    from UI.web_server_v2_2 import setup_ui_routes
    from Gateway.api_v2_2 import setup_gateway_routes  # 使用 v2.2 版本
    from Config.manager import get_config
    from Logging import get_logger, setup_logging
    
    # 配置日志
    setup_logging(level="INFO")
    logger = get_logger("OpenClaw")
    
    config = get_config()
    
    # 使用 lifespan 管理应用生命周期
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        global _llm_client
        
        logger.info("OpenClaw 服务启动 (v2.2)")
        logger.info(f"LLM 模型: {config.config.ollama.model}")
        
        # 启动时初始化
        yield
        
        # 关闭时清理
        logger.info("正在关闭服务...")
        if _llm_client:
            logger.info("关闭 LLM 客户端连接...")
            await _llm_client.close()
            logger.info("LLM 客户端已关闭")
        logger.info("OpenClaw 服务已停止")
    
    app = FastAPI(
        title="OpenClaw",
        description="AI Agent Platform - 智能代理平台 (支持流式响应)",
        version="2.2.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan
    )
    
    # 配置 CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.config.security.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 设置 UI 路由
    setup_ui_routes(app)
    
    # 设置 Gateway 路由 (v2.2)
    gateway = setup_gateway_routes(app)
    
    # 配置 LLM 客户端
    global _llm_client
    try:
        from LLM.client import OllamaClient
        _llm_client = OllamaClient(
            host=config.config.ollama.host,
            model=config.config.ollama.model
        )
        gateway.set_llm_client(_llm_client)
        logger.info(f"LLM 客户端已初始化: {config.config.ollama.model}")
    except Exception as e:
        logger.error(f"LLM 客户端初始化失败: {e}")
    
    return app


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenClaw - AI Agent Platform v2.2")
    parser.add_argument("--host", default="0.0.0.0", help="服务器主机地址")
    parser.add_argument("--port", type=int, default=8000, help="服务器端口")
    parser.add_argument("--reload", action="store_true", help="启用热重载")
    parser.add_argument("--verify-only", action="store_true", help="仅运行验证")
    parser.add_argument("--skip-verify", action="store_true", help="跳过验证")
    
    args = parser.parse_args()
    
    # 打印横幅
    print_banner()
    print_stage_info()
    
    # 运行验证
    if not args.skip_verify:
        result = asyncio.run(run_verification())
        
        if args.verify_only:
            print("验证日志已写入: Test/verification_logs.md")
            sys.exit(0 if result.all_passed else 1)
        
        print()
        print("-" * 60)
        print()
    
    # 启动服务器
    print("正在启动 OpenClaw 服务 (v2.2 - 支持流式响应)...")
    print()
    
    host_display = args.host if args.host != '0.0.0.0' else 'localhost'
    
    print("=" * 60)
    print(f"  🌐 UI 访问地址:   http://{host_display}:{args.port}")
    print(f"  📡 API 根地址:    http://{host_display}:{args.port}/api")
    print(f"  💬 聊天接口:      POST /api/chat")
    print(f"  🌊 流式聊天:      POST /api/chat/stream (SSE)")
    print(f"  🔌 WebSocket:     ws://{host_display}:{args.port}/ws/chat")
    print(f"  📚 API 文档:      http://{host_display}:{args.port}/docs")
    print("=" * 60)
    print()
    print("功能说明:")
    print("  - WebSocket 支持流式响应 (stream_start -> stream_chunk -> stream_end)")
    print("  - 详细的交互日志记录")
    print("  - 会话历史管理")
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    import uvicorn
    
    uvicorn.run(
        "main_v2_2:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
