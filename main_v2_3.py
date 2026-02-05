#!/usr/bin/env python3
"""
OpenClaw - 项目总入口 v2.3

版本: v2.3
更新:
- 工具调用支持 (Agentic Tool-Use Loop)
- 文件操作工具 (list_files, read_file, write_file)
- GitHub 集成 (create_repo, list_repos)
- 自动决策是否使用工具

启动 OpenClaw 应用
"""

import asyncio
import sys
import os
from pathlib import Path
from contextlib import asynccontextmanager

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
║           AI Agent Platform v2.3.0 (Tool-Use Loop)            ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_stage_info():
    """打印阶段信息"""
    print("=" * 60)
    print("【第三阶段】工具调用与自动化决策 (Agentic Tool-Use Loop)")
    print("=" * 60)
    print()


async def run_verification():
    """运行验证"""
    from Test.stage_tracker import StageTracker
    
    print("正在运行验证...")
    tracker = StageTracker(str(PROJECT_ROOT))
    result = await tracker.run_stage1_verification(check_ui=False, check_llm=True)
    tracker.write_verification_log(result)
    print(result.to_markdown())
    print()
    return result


_llm_client = None


def create_app():
    """创建 FastAPI 应用"""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    from UI.web_server_v2_3 import setup_ui_routes
    from Gateway.api_v2_3 import setup_gateway_routes
    from Gateway.runtime_v2_3 import get_runtime
    from Config.manager import get_config
    from Logging import get_logger, setup_logging
    
    setup_logging(level="INFO")
    logger = get_logger("OpenClaw")
    config = get_config()
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        global _llm_client
        
        logger.info("OpenClaw 服务启动 (v2.3 - Tool-Use Loop)")
        
        # 打印已注册的工具
        runtime = get_runtime()
        tools = runtime.list_tools()
        logger.info(f"已注册 {len(tools)} 个工具:")
        for tool in tools:
            logger.info(f"  - {tool.name}: {tool.description}")
        
        yield
        
        logger.info("正在关闭服务...")
        if _llm_client:
            await _llm_client.close()
        logger.info("OpenClaw 服务已停止")
    
    app = FastAPI(
        title="OpenClaw",
        description="AI Agent Platform - 支持工具调用",
        version="2.3.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    setup_ui_routes(app)
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
    
    parser = argparse.ArgumentParser(description="OpenClaw v2.3 - Tool-Use Loop")
    parser.add_argument("--host", default="0.0.0.0", help="服务器主机")
    parser.add_argument("--port", type=int, default=8000, help="端口")
    parser.add_argument("--reload", action="store_true", help="热重载")
    parser.add_argument("--skip-verify", action="store_true", help="跳过验证")
    
    args = parser.parse_args()
    
    print_banner()
    print_stage_info()
    
    # 检查 GitHub Token
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        print(f"✅ GitHub Token 已配置")
    else:
        print(f"⚠️  GitHub Token 未配置 (设置环境变量 GITHUB_TOKEN 以启用 GitHub 功能)")
    print()
    
    if not args.skip_verify:
        asyncio.run(run_verification())
        print("-" * 60)
        print()
    
    print("正在启动 OpenClaw 服务 (v2.3 - 支持工具调用)...")
    print()
    
    host_display = args.host if args.host != '0.0.0.0' else 'localhost'
    
    print("=" * 60)
    print(f"  🌐 UI 访问地址:   http://{host_display}:{args.port}")
    print(f"  📡 API 根地址:    http://{host_display}:{args.port}/api")
    print(f"  🔧 工具列表:      http://{host_display}:{args.port}/api/tools")
    print(f"  📚 API 文档:      http://{host_display}:{args.port}/docs")
    print(f"  🔌 WebSocket:     ws://{host_display}:{args.port}/ws/chat")
    print("=" * 60)
    print()
    print("可用工具:")
    print("  📂 list_files    - 列出目录内容")
    print("  📄 read_file     - 读取文件内容")
    print("  ✏️  write_file    - 写入文件 (保存到 Test 目录)")
    print("  🐙 github_create_repo - 创建 GitHub 仓库")
    print("  📋 github_list_repos  - 列出 GitHub 仓库")
    print("  ℹ️  github_get_repo    - 获取仓库信息")
    print()
    print("测试示例:")
    print('  "列出当前项目根目录的文件"')
    print('  "帮我读取 requirements.txt 的内容"')
    print('  "写一个 hello.py 脚本并保存"')
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    import uvicorn
    uvicorn.run(
        "main_v2_3:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
