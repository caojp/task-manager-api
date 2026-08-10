"""FastAPI 应用入口。

通过工厂函数创建应用实例，便于在测试与生产环境中复用。

启动方式：
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.routers import health
from app.core.config import settings


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title=settings.NAME,
        version=settings.VERSION,
        description="任务管理 RESTful API 服务",
        debug=settings.DEBUG,
    )

    app.include_router(health.router)

    return app


app = create_app()
