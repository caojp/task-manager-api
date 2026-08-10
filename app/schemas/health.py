"""健康检查相关响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """GET /health 的响应体。"""

    status: str = Field(
        ...,
        description="服务健康状态",
        examples=["healthy"],
    )
    service: str = Field(
        ...,
        description="服务名称",
        examples=["Task Manager API"],
    )
    version: str = Field(
        ...,
        description="服务版本号",
        examples=["0.1.0"],
    )
    timestamp: datetime = Field(
        ...,
        description="响应生成时间（UTC，ISO 8601）",
    )
