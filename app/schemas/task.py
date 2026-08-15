"""任务（Task）相关数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态枚举。"""

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskBase(BaseModel):
    """任务通用字段（创建/更新共用）。"""

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="任务标题",
        examples=["完成项目文档"],
    )
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="任务描述",
        examples=["撰写 REST API 接口文档"],
    )
    status: TaskStatus = Field(
        default=TaskStatus.TODO,
        description="任务状态",
    )


class TaskCreate(TaskBase):
    """POST /tasks 请求体。"""


class TaskUpdate(BaseModel):
    """PUT /tasks/{id} 请求体（全部可选，支持部分更新）。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: TaskStatus | None = None


class TaskResponse(TaskBase):
    """任务响应体（含系统字段）。"""

    id: uuid.UUID = Field(..., description="任务唯一标识（UUID）")
    created_at: datetime = Field(..., description="创建时间（UTC，ISO 8601）")
    updated_at: datetime = Field(..., description="最后更新时间（UTC，ISO 8601）")


class TaskListResponse(BaseModel):
    """任务列表响应体。"""

    items: list[TaskResponse]
    total: int
