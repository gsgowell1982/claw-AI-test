"""
UI Web Server v2.3 - FastAPI 静态资源挂载

版本: v2.3
"""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

UI_DIR = Path(__file__).parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"


class NoCacheStaticFiles(StaticFiles):
    """禁用缓存的静态文件"""
    async def __call__(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"cache-control", b"no-cache, no-store, must-revalidate"))
                message["headers"] = headers
            await send(message)
        await super().__call__(scope, receive, send_wrapper)


def setup_ui_routes(app: FastAPI) -> None:
    """配置 UI 路由"""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "css").mkdir(exist_ok=True)
    (STATIC_DIR / "js").mkdir(exist_ok=True)
    
    app.mount("/static", NoCacheStaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """主页"""
        template_name = "index_v2_3.html"
        if not (TEMPLATES_DIR / template_name).exists():
            template_name = "index_v2_2.html" if (TEMPLATES_DIR / "index_v2_2.html").exists() else "index.html"
        
        response = templates.TemplateResponse(template_name, {"request": request})
        response.headers["Cache-Control"] = "no-cache"
        return response
    
    @app.get("/health")
    async def health():
        return {"status": "healthy", "version": "2.3.0"}
