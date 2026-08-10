"""统一错误响应模型。

所有错误响应（4xx / 5xx）均使用此模型，保证响应结构一致，
便于前端/客户端统一处理。
"""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """单条校验错误详情（用于 422 输入校验）。"""

    loc: list[str] = Field(..., description="错误位置（如 [body, title]）")
    msg: str = Field(..., description="错误信息")
    type: str = Field(..., description="错误类型标识")


class ErrorResponse(BaseModel):
    """统一错误响应体。

    - detail 为字符串时表示业务/系统错误描述；
    - detail 为列表时表示输入校验错误集合（422 场景）。
    - request_id 用于关联服务端日志，便于问题排查。
    """

    detail: Union[str, list[ErrorDetail]] = Field(
        ...,
        description="错误详情：字符串或校验错误列表",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="请求追踪 ID，可用于关联服务端日志",
    )

    @classmethod
    def from_validation_error(
        cls, errors: list[dict[str, Any]], request_id: Optional[str] = None
    ) -> "ErrorResponse":
        """从 FastAPI 校验错误列表构造响应。"""
        details = [
            ErrorDetail(
                loc=err.get("loc", []),
                msg=err.get("msg", ""),
                type=err.get("type", ""),
            )
            for err in errors
        ]
        return cls(detail=details, request_id=request_id)
