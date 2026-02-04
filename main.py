#!/usr/bin/env python3
"""
OpenClaw - 项目总入口

启动 OpenClaw 应用,包括:
- UI Web 服务器
- Gateway API
- 阶段验证
"""

import asyncio
import sys
from pathlib import Path

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
║                   AI Agent Platform v1.0.0                    ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_stage_info():
    """打印阶段信息"""
    print("=" * 60)
    print("【第一阶段】项目骨架初始化")
    print("=" * 60)
    print()


async def run_verification():
    """运行阶段验证"""
    from Test.stage_tracker import StageTracker
    
    print("正在运行第一阶段验证...")
    print()
    
    tracker = StageTracker(str(PROJECT_ROOT))
    
    # 运行验证 (不检查 UI,因为服务还未启动)
    result = await tracker.run_stage1_verification(
        check_ui=False,
        check_llm=True
    )
    
    # 写入验证日志
    tracker.write_verification_log(result)
    
    # 打印结果摘要
    print(result.to_markdown())
    print()
    
    return result


def create_app():
    """创建 FastAPI 应用"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    from UI.web_server import setup_ui_routes
    from Gateway.api import setup_gateway_routes
    from Config.manager import get_config
    
    config = get_config()
    
    app = FastAPI(
        title="OpenClaw",
        description="AI Agent Platform",
        version="1.0.0"
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
    
    # 设置 Gateway 路由
    gateway = setup_gateway_routes(app)
    
    # 配置 LLM 客户端
    try:
        from LLM.client import OllamaClient
        llm_client = OllamaClient(
            host=config.config.ollama.host,
            model=config.config.ollama.model
        )
        gateway.planner.set_llm_client(llm_client)
    except Exception as e:
        print(f"警告: LLM 客户端初始化失败: {e}")
    
    @app.on_event("startup")
    async def startup_event():
        """启动事件"""
        from Logging import info
        info("OpenClaw 服务启动")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """关闭事件"""
        from Logging import info
        info("OpenClaw 服务关闭")
    
    return app


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenClaw - AI Agent Platform")
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
    print("正在启动 OpenClaw 服务...")
    print()
    print("=" * 60)
    print(f"  🌐 UI 访问地址: http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}")
    print(f"  📡 API 地址: http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}/api")
    print(f"  📚 API 文档: http://{args.host if args.host != '0.0.0.0' else 'localhost'}:{args.port}/docs")
    print("=" * 60)
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    import uvicorn
    
    uvicorn.run(
        "main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
