"""健康检查路由。

GET /health —— 返回服务运行状态，供探针与监控使用。
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=200,
    summary="健康检查",
    description="健康检查端点，返回服务运行状态。",
)
async def health_check() -> HealthResponse:
    """返回当前服务的健康状态。"""
    return HealthResponse(
        status="healthy",
        service=settings.NAME,
        version=settings.VERSION,
        timestamp=datetime.now(timezone.utc),
    )
