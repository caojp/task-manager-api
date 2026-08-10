"""FastAPI 应用入口。

通过工厂函数创建应用实例，便于在测试与生产环境中复用。

启动方式：
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

from app.api.routers import health, tasks
from app.core.config import settings
from app.core.rate_limit import rate_limit_middleware

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(settings.NAME)


# ---------------------------------------------------------------------------
# 限流中间件 —— 基于 Starlette BaseHTTPMiddleware，保证与 TestClient 兼容
# ---------------------------------------------------------------------------
class RateLimitStarletteMiddleware(BaseHTTPMiddleware):
    """按客户端 IP 执行全局限流。

    触发时返回 429 + Retry-After + 统一 JSON 响应体。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> StarletteResponse:
        client_ip = request.client.host if request.client else "127.0.0.1"
        allowed, retry_after = rate_limit_middleware.check_and_hit(client_ip)
        if allowed:
            return await call_next(request)

        logger.warning(
            "rate_limited ip=%s path=%s retry_after=%ss",
            client_ip,
            request.url.path,
            retry_after,
        )
        resp = JSONResponse(
            status_code=429,
            content={"detail": "请求过于频繁，请稍后再试"},
        )
        resp.headers["Retry-After"] = str(retry_after)
        return resp


# ---------------------------------------------------------------------------
# 中间件：请求日志 + 请求 ID + 耗时追踪
# ---------------------------------------------------------------------------
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个请求的方法、路径、状态码与耗时。"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> StarletteResponse:
        request_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()

        # 将 request_id 放入 state，供路由内日志引用
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "req=%s %s %s -> %d (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# 全局异常处理器
# ---------------------------------------------------------------------------
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """捕获未处理异常，返回统一 500 响应并记录错误日志。"""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "req=%s unhandled exception: %s: %s",
        request_id,
        type(exc).__name__,
        str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "内部服务器错误",
            "request_id": request_id,
        },
    )


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title=settings.NAME,
        version=settings.VERSION,
        description="任务管理 RESTful API 服务",
        debug=settings.DEBUG,
    )

    # 中间件：FastAPI/Starlette 以"注册顺序反向"执行，
    # 先注册的在外层。顺序：限流 -> 日志。
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitStarletteMiddleware)

    # 异常处理器
    app.add_exception_handler(Exception, global_exception_handler)

    # 路由
    app.include_router(health.router)
    app.include_router(tasks.router)

    # 启动日志
    limit_cfg = (
        "disabled"
        if not rate_limit_middleware.enabled
        else f"{settings.RATE_LIMIT_REQUESTS} req / {settings.RATE_LIMIT_WINDOW_SECONDS}s"
    )
    logger.info("%s v%s 已就绪（限流策略: %s）", settings.NAME, settings.VERSION, limit_cfg)
    return app


app = create_app()
