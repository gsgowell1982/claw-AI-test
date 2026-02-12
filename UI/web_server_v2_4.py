"""
UI Web Server v2.4 - 支持多模型选择的 Web 服务器

版本: v2.4
更新:
- 使用 v2.4 模板（含模型选择器）
- 禁用静态文件缓存
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from starlette.responses import Response
from pathlib import Path

import logging
logger = logging.getLogger("OpenClaw.UI")


# 获取目录路径
UI_DIR = Path(__file__).parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"


class NoCacheStaticFiles(StaticFiles):
    """禁用缓存的静态文件服务"""
    
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response


def setup_ui_routes(app: FastAPI) -> None:
    """
    配置 UI 路由
    
    Args:
        app: FastAPI 应用实例
    """
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    
    # 挂载静态文件（禁用缓存）
    app.mount(
        "/static",
        NoCacheStaticFiles(directory=str(STATIC_DIR)),
        name="static"
    )
    
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """渲染主页 - 优先使用 v2.4 模板"""
        # 检查模板文件
        v24_template = TEMPLATES_DIR / "index_v2_4.html"
        v23_template = TEMPLATES_DIR / "index_v2_3.html"
        
        if v24_template.exists():
            template_name = "index_v2_4.html"
        elif v23_template.exists():
            template_name = "index_v2_3.html"
        else:
            template_name = "index.html"
        
        logger.info(f"[UI] 使用模板: {template_name}")
        
        response = templates.TemplateResponse(template_name, {"request": request})
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    
    logger.info("[UI] v2.4 路由已配置 (多模型支持)")
