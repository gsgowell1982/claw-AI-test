#!/usr/bin/env python3
"""
OpenClaw - 项目总入口 v2.5.3

版本: v2.5.3
更新:
- 语义级记忆检索：基于 Embedding 的相似度搜索
- 执行历史自动清理：30天过期或超过10000条
- 智能代码截断：保留核心结构（导入、函数签名）

记忆系统:
- 短期记忆：会话内工具调用结果缓存
- 长期记忆：SQLite 存储 + 语义向量索引
- 语义检索：支持逻辑错误等无明确 error_type 的场景
- 自动清理：VACUUM 优化数据库

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
║       AI Agent Platform v2.5.3 (Semantic Memory Retrieval)    ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_stage_info():
    """打印阶段信息"""
    print("=" * 60)
    print("【第五阶段】语义级记忆检索与自动清理")
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
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    
    from UI.web_server_v2_4 import setup_ui_routes
    from Gateway.api_v2_5 import setup_gateway_routes
    from Gateway.runtime_v2_3 import get_runtime
    from Config.manager import get_config
    from Logging import get_logger, setup_logging
    from LLM.client_v2_4 import OllamaClientV24, get_default_model, get_cloud_model, PRESET_MODELS
    from Memory import get_long_term_memory, get_backend_info
    
    setup_logging(level="INFO")
    logger = get_logger("OpenClaw")
    config = get_config()
    
    # 确定使用的模型
    if model:
        selected_model = model
    elif use_cloud:
        selected_model = get_cloud_model()
    else:
        selected_model = os.environ.get("OPENCLAW_MODEL", config.config.ollama.model)
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """应用生命周期管理"""
        global _llm_client
        
        model_config = PRESET_MODELS.get(selected_model)
        model_type = "云端" if model_config and model_config.type.value == "cloud" else "本地"
        
        logger.info(f"OpenClaw 服务启动 (v2.5.3 - Semantic Memory)")
        logger.info(f"当前模型: {selected_model} ({model_type})")
        
        # 初始化记忆系统
        long_term = get_long_term_memory()
        stats = long_term.get_error_statistics()
        logger.info(f"长期记忆: {stats['total_patterns']} 个错误模式, "
                   f"{stats['solved_patterns']} 个已解决, "
                   f"{stats['total_experiences']} 个经验")
        
        # 显示 Embedding 后端信息
        backend_info = get_backend_info()
        logger.info(f"Embedding 后端: {backend_info['backend']} (维度: {backend_info['dimension']})")
        
        # 执行自动清理
        cleanup_result = long_term.vacuum_old_records()
        if cleanup_result['deleted_history'] > 0:
            logger.info(f"自动清理: 删除 {cleanup_result['deleted_history']} 条过期记录")
        
        # 打印已注册的工具
        runtime = get_runtime()
        tools = runtime.list_tools()
        logger.info(f"已注册 {len(tools)} 个工具")
        
        # 按类别统计
        categories = {}
        for t in tools:
            cat = t.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(t.name)
        
        for cat, names in categories.items():
            logger.info(f"  [{cat}]: {', '.join(names)}")
        
        yield
        
        logger.info("正在关闭服务...")
        if _llm_client:
            await _llm_client.close()
        logger.info("OpenClaw 服务已停止")
    
    app = FastAPI(
        title="OpenClaw",
        description="AI Agent Platform v2.5.3 - 语义级记忆检索",
        version="2.5.3",
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
    
    available_models = list(PRESET_MODELS.keys())
    
    parser = argparse.ArgumentParser(
        description="OpenClaw v2.5.3 - Semantic Memory Retrieval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
v2.5.3 新特性:
  🔍 语义检索 - 基于 Embedding 的相似度搜索
  🧹 自动清理 - 执行历史 30 天过期
  ✂️  智能截断 - 保留代码核心结构

示例:
  python3 main_v2_5_3.py                   # 使用默认本地模型
  python3 main_v2_5_3.py --cloud           # 使用云端模型
        """
    )
    parser.add_argument("--host", default="0.0.0.0", help="服务器主机")
    parser.add_argument("--port", type=int, default=8000, help="端口")
    parser.add_argument("--reload", action="store_true", help="热重载")
    parser.add_argument("--skip-verify", action="store_true", help="跳过验证")
    
    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument("--model", "-m", type=str, help="指定使用的模型")
    model_group.add_argument("--cloud", "-c", action="store_true", help="使用云端模型")
    model_group.add_argument("--local", "-l", action="store_true", help="使用本地模型 [默认]")
    
    args = parser.parse_args()
    
    print_banner()
    print_stage_info()
    
    # 确定使用的模型
    if args.model:
        selected_model = args.model
        model_config = PRESET_MODELS.get(args.model)
        is_cloud = model_config and model_config.type.value == "cloud"
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
        print(f"⚠️  GitHub Token 未配置")
    print()
    
    if not args.skip_verify:
        asyncio.run(run_verification())
        print("-" * 60)
        print()
    
    print("正在启动 OpenClaw 服务 (v2.5.3)...")
    print()
    
    host_display = args.host if args.host != '0.0.0.0' else 'localhost'
    model_type_display = "☁️ 云端" if is_cloud else "💻 本地"
    
    print("=" * 60)
    print(f"  🌐 UI 访问地址:   http://{host_display}:{args.port}")
    print(f"  📡 API 根地址:    http://{host_display}:{args.port}/api")
    print(f"  🤖 当前模型:      {selected_model} ({model_type_display})")
    print(f"  📚 API 文档:      http://{host_display}:{args.port}/docs")
    print("=" * 60)
    print()
    print("🔍 语义级记忆 (v2.5.3 新特性):")
    print("   Embedding 检索 - 即使无 error_type 也能找到相关经验")
    print("   自动清理 - 执行历史 30 天过期，数据库自动 VACUUM")
    print("   智能截断 - 保留导入语句和函数签名")
    print()
    print("🧠 记忆系统:")
    print("   短期记忆 - 会话内工具结果缓存")
    print("   长期记忆 - SQLite + 向量索引")
    print("   语义搜索 - POST /api/memory/search")
    print("   手动清理 - POST /api/memory/vacuum")
    print()
    print("📂 工具列表:")
    print("   文件: list_files, read_file, write_file")
    print("   GitHub: github_set_token, create/delete_repo, create_release...")
    print("   Python: check_package, analyze_packages, install_package,")
    print("           execute_python, convert_file")
    print()
    print("按 Ctrl+C 停止服务")
    print()
    
    _cli_args["model"] = selected_model
    _cli_args["use_cloud"] = is_cloud
    
    import uvicorn
    uvicorn.run(
        "main_v2_5_3:create_app_factory",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
