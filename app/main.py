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
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response as StarletteResponse

from app.api.routers import health, tasks
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
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
            "req=%s %s %s ip=%s 429 限流触发 retry_after=%ss",
            getattr(request.state, "request_id", "unknown"),
            request.method,
            request.url.path,
            client_ip,
            retry_after,
        )
        from fastapi.responses import JSONResponse

        resp = JSONResponse(
            status_code=429,
            content={
                "detail": "请求过于频繁，请稍后再试",
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        resp.headers["Retry-After"] = str(retry_after)
        return resp


# ---------------------------------------------------------------------------
# 中间件：请求日志 + 请求 ID + 耗时追踪 + 客户端 IP + 状态码分级
# ---------------------------------------------------------------------------
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """记录每个请求的方法、路径、状态码、耗时、客户端 IP。

    根据响应状态码分级记录日志：
        2xx / 3xx -> INFO
        4xx       -> WARNING
        5xx       -> ERROR
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> StarletteResponse:
        request_id = uuid.uuid4().hex[:8]
        started = time.perf_counter()

        # 将 request_id 放入 state，供路由/异常处理器日志引用
        request.state.request_id = request_id
        client_ip = request.client.host if request.client else "unknown"

        response = await call_next(request)

        duration_ms = (time.perf_counter() - started) * 1000
        status_code = response.status_code

        log_msg = (
            "req=%s %s %s ip=%s -> %d (%.1fms)"
            % (request_id, request.method, request.url.path, client_ip, status_code, duration_ms)
        )

        if status_code >= 500:
            logger.error(log_msg)
        elif status_code >= 400:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        response.headers["X-Request-ID"] = request_id
        return response


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

    # 异常处理器（统一错误响应格式 + 分级日志）
    register_exception_handlers(app)

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
