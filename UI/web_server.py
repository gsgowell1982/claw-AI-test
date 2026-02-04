"""
UI Web Server - FastAPI 静态资源挂载与路由配置

负责:
- 静态资源挂载 (CSS, JS, 图标等)
- 模板页面渲染
- 网络访问地址映射
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

# 获取 UI 目录路径
UI_DIR = Path(__file__).parent
TEMPLATES_DIR = UI_DIR / "templates"
STATIC_DIR = UI_DIR / "static"


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
    
    # 挂载静态资源
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    
    # 配置模板引擎
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """主页 - Chat UI"""
        return templates.TemplateResponse(
            "index.html",
            {"request": request}
        )
    
    @app.get("/health")
    async def health_check():
        """健康检查端点"""
        return {"status": "healthy", "service": "ui"}


def get_ui_info() -> dict:
    """
    获取 UI 服务信息
    
    Returns:
        包含 UI 配置信息的字典
    """
    return {
        "templates_dir": str(TEMPLATES_DIR),
        "static_dir": str(STATIC_DIR),
        "templates_exist": TEMPLATES_DIR.exists(),
        "static_exist": STATIC_DIR.exists()
    }


class UIServer:
    """UI 服务器管理类"""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self.app = None
    
    def create_app(self) -> FastAPI:
        """创建并配置 FastAPI 应用"""
        from fastapi import FastAPI
        
        self.app = FastAPI(
            title="OpenClaw UI",
            description="OpenClaw Chat Interface",
            version="1.0.0"
        )
        setup_ui_routes(self.app)
        return self.app
    
    def get_url(self) -> str:
        """获取服务访问 URL"""
        return f"http://{self.host}:{self.port}"
    
    def run(self):
        """启动 UI 服务器"""
        import uvicorn
        
        if self.app is None:
            self.create_app()
        
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port
        )


# 模块级别的便捷函数
def create_ui_app() -> FastAPI:
    """创建 UI FastAPI 应用的便捷函数"""
    server = UIServer()
    return server.create_app()
