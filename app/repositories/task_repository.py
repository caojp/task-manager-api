"""任务仓储 —— 基于内存字典的实现。

使用 UUID 作为主键，支持标准的 CRUD 操作。
接口设计保持抽象，便于后续迁移到数据库实现。
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate


class TaskRepository:
    """任务内存仓储。

    使用线程安全的锁保护共享字典，支持并发请求。
    """

    def __init__(self) -> None:
        self._tasks: dict[uuid.UUID, TaskResponse] = {}
        self._lock = threading.Lock()

    def create(self, data: TaskCreate) -> TaskResponse:
        """创建新任务。"""
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        task = TaskResponse(
            id=task_id,
            title=data.title,
            description=data.description,
            status=data.status,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get_by_id(self, task_id: uuid.UUID) -> Optional[TaskResponse]:
        """根据 ID 获取单个任务，不存在返回 None。"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_all(self) -> list[TaskResponse]:
        """获取所有任务列表。"""
        with self._lock:
            return list(self._tasks.values())

    def update(
        self, task_id: uuid.UUID, data: TaskUpdate
    ) -> Optional[TaskResponse]:
        """更新任务，不存在返回 None。仅更新提供的字段。"""
        with self._lock:
            existing = self._tasks.get(task_id)
            if existing is None:
                return None

            update_data = data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(existing, field, value)
            existing.updated_at = datetime.now(timezone.utc)
            self._tasks[task_id] = existing
            return existing

    def delete(self, task_id: uuid.UUID) -> bool:
        """删除任务，返回是否删除成功。"""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False


# 全局单例实例，供路由层注入使用
task_repository = TaskRepository()
