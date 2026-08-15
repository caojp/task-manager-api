"""统一异常处理器集合。

将 FastAPI/Starlette 各类异常转换为统一 ErrorResponse 格式，
并记录相应级别的日志（4xx -> WARNING, 5xx -> ERROR）。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.error import ErrorResponse

logger = logging.getLogger("Task Manager API")


def _get_request_id(request: Request) -> str:
    """从 request.state 获取请求 ID（可能未设置，如早期 404）。"""
    return getattr(request.state, "request_id", "unknown")


def _client_ip(request: Request) -> str:
    """获取客户端 IP。"""
    return request.client.host if request.client else "unknown"


def _log_context(request: Request) -> str:
    """构造请求上下文日志前缀。"""
    return (
        f"req={_get_request_id(request)} "
        f"{request.method} {request.url.path} "
        f"ip={_client_ip(request)}"
    )


# ---------------------------------------------------------------------------
# 1. 输入校验错误（422）
# ---------------------------------------------------------------------------
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """处理 Pydantic 输入校验错误，返回统一 422 响应。"""
    request_id = _get_request_id(request)
    logger.warning(
        "%s 422 输入校验失败: %s",
        _log_context(request),
        exc.errors(),
    )
    body = ErrorResponse.from_validation_error(exc.errors(), request_id)
    return JSONResponse(
        status_code=422,
        content=body.model_dump(),
    )


# ---------------------------------------------------------------------------
# 2. HTTPException（业务层主动抛出的 4xx/5xx，如 404 任务不存在）
# ---------------------------------------------------------------------------
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """统一处理 HTTPException，响应体加入 request_id。"""
    request_id = _get_request_id(request)
    status_code = exc.status_code
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    # 按状态码分级记录日志
    if status_code >= 500:
        logger.error("%s %d %s", _log_context(request), status_code, detail)
    elif status_code >= 400:
        logger.warning("%s %d %s", _log_context(request), status_code, detail)

    body = ErrorResponse(detail=detail, request_id=request_id)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
        headers=getattr(exc, "headers", None),
    )


# ---------------------------------------------------------------------------
# 3. 路由不存在（404）& 方法不允许（405）
# ---------------------------------------------------------------------------
async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """处理 Starlette 层的 HTTP 异常（404 路由不存在、405 方法不允许等）。

    FastAPI 的 HTTPException 继承自 StarletteHTTPException，
    此处理器作为兜底，确保所有 HTTP 异常响应格式统一。
    """
    request_id = _get_request_id(request)
    status_code = exc.status_code
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)

    if status_code >= 500:
        logger.error("%s %d %s", _log_context(request), status_code, detail)
    elif status_code >= 400:
        logger.warning("%s %d %s", _log_context(request), status_code, detail)

    body = ErrorResponse(detail=detail, request_id=request_id)
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(),
        headers=getattr(exc, "headers", None),
    )


# ---------------------------------------------------------------------------
# 4. 未捕获异常（500）
# ---------------------------------------------------------------------------
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """捕获所有未处理异常，返回统一 500 响应并记录错误日志（含堆栈）。"""
    request_id = _get_request_id(request)
    # 记录带堆栈的错误日志
    logger.exception(
        "%s 500 未捕获异常: %s",
        _log_context(request),
        type(exc).__name__,
    )
    body = ErrorResponse(
        detail="内部服务器错误",
        request_id=request_id,
    )
    return JSONResponse(
        status_code=500,
        content=body.model_dump(),
    )


# ---------------------------------------------------------------------------
# 注册入口
# ---------------------------------------------------------------------------
def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI 应用上注册所有异常处理器。

    注册顺序：先具体后通用。
    - RequestValidationError 最具体（422 校验）；
    - HTTPException 处理业务层抛出的异常；
    - StarletteHTTPException 兜底处理 404/405 等；
    - Exception 兜底处理所有未捕获异常。

    注意：FastAPI 的 HTTPException 继承自 StarletteHTTPException，
    因此 HTTPException 处理器必须后于 StarletteHTTPException 注册，
    否则会被后者拦截。这里通过分别注册保证优先级正确。
    """
    # FastAPI 的 HTTPException（业务层）
    app.add_exception_handler(HTTPException, http_exception_handler)
    # Starlette 兜底（404 路由不存在、405 方法不允许）
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    # Pydantic 输入校验
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # 未捕获异常
    app.add_exception_handler(Exception, unhandled_exception_handler)
