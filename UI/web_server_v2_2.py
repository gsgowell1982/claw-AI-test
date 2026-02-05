"""
UI Web Server v2.2 - FastAPI 静态资源挂载与路由配置

版本: v2.2.1
更新:
- 使用 v2.2 模板
- 支持流式响应的前端
- 添加静态文件缓存控制

负责:
- 静态资源挂载 (CSS, JS, 图标等)
- 模板页面渲染
- 网络访问地址映射
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse

# 获取 UI 目录路径
UI_DIR = Path(__file__).parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"


class NoCacheStaticFiles(StaticFiles):
    """禁用缓存的静态文件服务"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    async def __call__(self, scope, receive, send):
        # 添加禁用缓存的响应头
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                # 添加禁用缓存的头部
                headers.append((b"cache-control", b"no-cache, no-store, must-revalidate"))
                headers.append((b"pragma", b"no-cache"))
                headers.append((b"expires", b"0"))
                message["headers"] = headers
            await send(message)
        
        await super().__call__(scope, receive, send_wrapper)


def setup_ui_routes(app: FastAPI) -> None:
    """
    配置 UI 相关的路由和静态资源挂载
    
    Args:
        app: FastAPI 应用实例
    """
    # 确保静态目录存在
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "css").mkdir(exist_ok=True)
    (STATIC_DIR / "js").mkdir(exist_ok=True)
    
    # 挂载静态资源 (禁用缓存，开发模式)
    app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")
    
    # 配置模板引擎
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """主页 - Chat UI v2.2"""
        # 优先使用 v2.2 模板
        template_name = "index_v2_2.html"
        if not (TEMPLATES_DIR / template_name).exists():
            template_name = "index.html"
        
        response = templates.TemplateResponse(
            template_name,
            {"request": request}
        )
        # 禁用页面缓存
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    
    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        return {"status": "healthy", "service": "ui", "version": "2.2.1"}


def get_ui_info() -> dict:
    """获取 UI 服务信息"""
    return {
        "templates_dir": str(TEMPLATES_DIR),
        "static_dir": str(STATIC_DIR),
        "templates_exist": TEMPLATES_DIR.exists(),
        "static_exist": STATIC_DIR.exists(),
        "version": "2.2.0"
    }
