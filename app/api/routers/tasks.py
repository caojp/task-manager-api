"""任务 CRUD 路由。

路径：/tasks
方法：
    GET    /tasks          列出所有任务
    GET    /tasks/{id}    根据 ID 获取单个任务
    POST   /tasks         创建新任务
    PUT    /tasks/{id}    更新任务
    DELETE /tasks/{id}    删除任务
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.repositories.task_repository import task_repository
from app.schemas.task import (
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get(
    "",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
    summary="获取所有任务列表",
    description="返回系统中所有任务的列表。",
)
async def list_tasks() -> TaskListResponse:
    """列出所有任务。"""
    items = task_repository.list_all()
    return TaskListResponse(items=items, total=len(items))


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="获取单个任务",
    description="根据 UUID 获取单个任务详情。",
)
async def get_task(task_id: uuid.UUID) -> TaskResponse:
    """根据 ID 获取单个任务。"""
    task = task_repository.get_by_id(task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}",
        )
    return task


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新任务",
    description="创建一个新的任务，返回任务详情（含自动生成的 UUID 和时间戳）。",
)
async def create_task(data: TaskCreate) -> TaskResponse:
    """创建新任务。"""
    task = task_repository.create(data)
    return task


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="更新任务",
    description="根据 UUID 更新任务内容。支持部分更新（仅提供需要修改的字段）。",
)
async def update_task(
    task_id: uuid.UUID, data: TaskUpdate
) -> TaskResponse:
    """更新任务。"""
    task = task_repository.update(task_id, data)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}",
        )
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除任务",
    description="根据 UUID 删除任务。删除成功返回 204 无响应体。",
)
async def delete_task(task_id: uuid.UUID) -> None:
    """删除任务。"""
    deleted = task_repository.delete(task_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_id}",
        )
