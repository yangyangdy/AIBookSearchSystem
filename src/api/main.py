"""FastAPI应用入口"""
from pathlib import Path

from src.utils import logger as logger_module

logger_module.setup_logger("api")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger

from src.api.routes import search, health
from src.utils.config import get_settings

# 项目根目录下的 static（与 run_api.py 工作目录一致时可用）
_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"

# 获取配置
settings = get_settings()
api_config = settings.api

# 创建FastAPI应用
app = FastAPI(
    title=api_config.title,
    version=api_config.version,
    description="基于向量检索的书籍封面相似性查找系统"
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(search.router)
app.include_router(health.router)

if _STATIC_DIR.is_dir():
    app.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="static",
    )

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """浏览器默认请求 /favicon.ico，避免无路由时刷 404 日志。"""
    ico = _STATIC_DIR / "favicon.ico"
    if ico.is_file():
        return FileResponse(ico, media_type="image/x-icon")
    svg = _STATIC_DIR / "favicon.svg"
    if svg.is_file():
        return FileResponse(svg, media_type="image/svg+xml")
    return Response(status_code=204)

@app.get("/")
async def serve_search_page():
    """图片检索页（上传 / URL）"""
    index = _STATIC_DIR / "index.html"
    if not index.is_file():
        return JSONResponse(
            status_code=503,
            content={"detail": "检索页未找到，请确认 static/index.html 存在"},
        )
    return FileResponse(index, media_type="text/html; charset=utf-8")


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info(f"{api_config.title} v{api_config.version} 启动成功")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info(f"{api_config.title} 关闭")
