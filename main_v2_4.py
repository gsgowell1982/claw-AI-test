#!/usr/bin/env python3
"""
OpenClaw - 项目总入口 v2.4

版本: v2.4
更新:
- 支持本地/云端模型切换
- 命令行模型选择
- 运行时模型切换 API
- 模型状态显示

支持的模型:
- qwen2.5:7b (本地，默认)
- gpt-oss:120b-cloud (云端)

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
║        AI Agent Platform v2.4.0 (Multi-Model Support)         ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_stage_info():
    """打印阶段信息"""
    print("=" * 60)
    print("【第四阶段】多模型支持 (Local + Cloud LLM)")
    print("=" * 60)
    print()


def print_model_info(model: str, is_cloud: bool):
    """打印模型信息"""
    model_type = "☁️  云端" if is_cloud else "💻 本地"
    print(f"当前模型: {model_type} - {model}")
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


def create_app(model: str = None, use_cloud: bool = False):
    """
    创建 FastAPI 应用
    
    Args:
        model: 指定模型名称
        use_cloud: 是否使用云端模型
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    from UI.web_server_v2_4 import setup_ui_routes
    from Gateway.api_v2_4 import setup_gateway_routes
    from Gateway.runtime_v2_3 import get_runtime
    from Config.manager import get_config
    from Logging import get_logger, setup_logging
    from LLM.client_v2_4 import OllamaClientV24, get_default_model, get_cloud_model, PRESET_MODELS
    
    setup_logging(level="INFO")
    logger = get_logger("OpenClaw")
    config = get_config()
    
    # 确定使用的模型
    if model:
        selected_model = model
    elif use_cloud:
        selected_model = get_cloud_model()
    else:
        # 从环境变量或配置获取
        selected_model = os.environ.get("OPENCLAW_MODEL", config.config.ollama.model)
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        global _llm_client
        
        # 获取模型配置
        model_config = PRESET_MODELS.get(selected_model)
        model_type = "云端" if model_config and model_config.type.value == "cloud" else "本地"
        
        logger.info(f"OpenClaw 服务启动 (v2.4 - Multi-Model)")
        logger.info(f"当前模型: {selected_model} ({model_type})")
        
        # 打印已注册的工具
        runtime = get_runtime()
        tools = runtime.list_tools()
        logger.info(f"已注册 {len(tools)} 个工具")
        
        yield
        
        logger.info("正在关闭服务...")
        if _llm_client:
            await _llm_client.close()
        logger.info("OpenClaw 服务已停止")
    
    app = FastAPI(
        title="OpenClaw",
        description="AI Agent Platform v2.4 - 支持多模型选择",
        version="2.4.0",
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
        _llm_client = OllamaClientV24(
            host=config.config.ollama.host,
            model=selected_model
        )
        gateway.set_llm_client(_llm_client)
        
        model_config = PRESET_MODELS.get(selected_model)
        model_type = "云端" if model_config and model_config.type.value == "cloud" else "本地"
        logger.info(f"LLM 客户端已初始化: {selected_model} ({model_type})")
    except Exception as e:
        logger.error(f"LLM 客户端初始化失败: {e}")
    
    return app


# 用于存储命令行参数
_cli_args = {
    "model": None,
    "use_cloud": False
}


def create_app_factory():
    """工厂函数，用于 uvicorn"""
    return create_app(model=_cli_args["model"], use_cloud=_cli_args["use_cloud"])


def main():
    """主函数"""
    import argparse
    from LLM.client_v2_4 import PRESET_MODELS, get_default_model, get_cloud_model
    
    # 列出可用模型
    available_models = list(PRESET_MODELS.keys())
    
    parser = argparse.ArgumentParser(
        description="OpenClaw v2.4 - Multi-Model Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
可用模型:
  {get_default_model()} (默认, 本地)
  {get_cloud_model()} (云端)

示例:
  python3 main_v2_4.py                     # 使用默认本地模型
  python3 main_v2_4.py --cloud             # 使用云端模型
  python3 main_v2_4.py --model qwen2.5:7b  # 指定模型
        """
    )
    parser.add_argument("--host", default="0.0.0.0", help="服务器主机")
    parser.add_argument("--port", type=int, default=8000, help="端口")
    parser.add_argument("--reload", action="store_true", help="热重载")
    parser.add_argument("--skip-verify", action="store_true", help="跳过验证")
    
    # 模型选择参数
    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument(
        "--model", "-m",
        type=str,
        help=f"指定使用的模型 (可选: {', '.join(available_models)})"
    )
    model_group.add_argument(
        "--cloud", "-c",
        action="store_true",
        help=f"使用云端模型 ({get_cloud_model()})"
    )
    model_group.add_argument(
        "--local", "-l",
        action="store_true",
        help=f"使用本地模型 ({get_default_model()}) [默认]"
    )
    
    args = parser.parse_args()
    
    print_banner()
    print_stage_info()
    
    # 确定使用的模型
    if args.model:
        selected_model = args.model
        is_cloud = PRESET_MODELS.get(args.model, {})
        is_cloud = is_cloud.type.value == "cloud" if hasattr(is_cloud, 'type') else "cloud" in args.model
    elif args.cloud:
        selected_model = get_cloud_model()
        is_cloud = True
    else:
        selected_model = os.environ.get("OPENCLAW_MODEL", get_default_model())
        model_config = PRESET_MODELS.get(selected_model)
        is_cloud = model_config and model_config.type.value == "cloud"
    
    print_model_info(selected_model, is_cloud)
    
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
    
    print("正在启动 OpenClaw 服务 (v2.4 - 多模型支持)...")
    print()
    
    host_display = args.host if args.host != '0.0.0.0' else 'localhost'
    model_type_display = "☁️ 云端" if is_cloud else "💻 本地"
    
    print("=" * 60)
    print(f"  🌐 UI 访问地址:   http://{host_display}:{args.port}")
    print(f"  📡 API 根地址:    http://{host_display}:{args.port}/api")
    print(f"  🤖 当前模型:      {selected_model} ({model_type_display})")
    print(f"  📋 模型列表:      http://{host_display}:{args.port}/api/models")
    print(f"  🔧 工具列表:      http://{host_display}:{args.port}/api/tools")
    print(f"  📚 API 文档:      http://{host_display}:{args.port}/docs")
    print(f"  🔌 WebSocket:     ws://{host_display}:{args.port}/ws/chat")
    print("=" * 60)
    print()
    print("模型切换:")
    print(f"  POST /api/models/switch  - 切换模型")
    print(f"  GET  /api/models         - 查看可用模型")
    print()
    print("可用工具:")
    print("  📂 list_files           - 列出目录内容")
    print("  📄 read_file            - 读取文件内容")
    print("  ✏️  write_file           - 写入文件")
    print("  🐙 github_create_repo   - 创建 GitHub 仓库")
    print("  🗑️  github_delete_repo   - 删除 GitHub 仓库")
    print("  📋 github_list_repos    - 列出 GitHub 仓库")
    print("  🚀 github_create_release- 创建 GitHub Release")
    print("  📦 github_list_releases - 列出 Release")
    print()
    print("测试示例:")
    print('  "你好，你是什么模型？"')
    print('  "帮我在 GitHub 创建一个 test-v2.4 仓库"')
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    # 存储参数供工厂函数使用
    _cli_args["model"] = selected_model
    _cli_args["use_cloud"] = is_cloud
    
    import uvicorn
    uvicorn.run(
        "main_v2_4:create_app_factory",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
