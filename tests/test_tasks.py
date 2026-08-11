"""任务 CRUD 端点单元测试。"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.task import TaskStatus

client = TestClient(app)

# ---------------------------------------------------------------------------
# 列表 & 创建
# ---------------------------------------------------------------------------


def test_list_tasks_empty() -> None:
    """初始状态应返回空列表。"""
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_create_task() -> None:
    """创建任务应返回 201 且包含生成的字段。"""
    payload = {"title": "测试任务", "description": "测试描述", "status": "todo"}
    response = client.post("/tasks", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "测试任务"
    assert data["description"] == "测试描述"
    assert data["status"] == "todo"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    # 新任务的两个时间戳应基本相等
    assert data["created_at"] == data["updated_at"]


def test_create_task_default_status() -> None:
    """未指定 status 时默认为 todo。"""
    response = client.post("/tasks", json={"title": "默认状态任务"})
    assert response.status_code == 201
    assert response.json()["status"] == "todo"


def test_create_task_validation_missing_title() -> None:
    """缺少 title 应返回 422。"""
    response = client.post("/tasks", json={"description": "无标题"})
    assert response.status_code == 422


def test_create_task_validation_empty_title() -> None:
    """空 title 应返回 422。"""
    response = client.post("/tasks", json={"title": ""})
    assert response.status_code == 422


def test_create_task_validation_invalid_status() -> None:
    """非法 status 值应返回 422。"""
    response = client.post("/tasks", json={"title": "Bad", "status": "invalid"})
    assert response.status_code == 422


def test_list_tasks_after_create() -> None:
    """创建后列表应有对应条目。"""
    client.post("/tasks", json={"title": "任务 A"})
    client.post("/tasks", json={"title": "任务 B"})
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2


# ---------------------------------------------------------------------------
# 读取单个
# ---------------------------------------------------------------------------


def test_get_task_by_id() -> None:
    """根据 ID 获取存在的任务应返回 200。"""
    create_resp = client.post("/tasks", json={"title": "可获取任务"})
    task_id = create_resp.json()["id"]
    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "可获取任务"


def test_get_task_not_found() -> None:
    """不存在的任务 ID 应返回 404。"""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/tasks/{fake_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------


def test_update_task_full() -> None:
    """全量更新任务应返回 200 且字段已更新。"""
    create_resp = client.post(
        "/tasks",
        json={"title": "原标题", "description": "原描述", "status": "todo"},
    )
    task_id = create_resp.json()["id"]
    response = client.put(
        f"/tasks/{task_id}",
        json={
            "title": "新标题",
            "description": "新描述",
            "status": "in_progress",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "新标题"
    assert data["description"] == "新描述"
    assert data["status"] == "in_progress"


def test_update_task_partial() -> None:
    """部分更新（仅改 status）应保留其他字段。"""
    create_resp = client.post(
        "/tasks",
        json={"title": "部分更新", "description": "保留我", "status": "todo"},
    )
    task_id = create_resp.json()["id"]
    response = client.put(f"/tasks/{task_id}", json={"status": "done"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "部分更新"
    assert data["description"] == "保留我"
    assert data["status"] == "done"


def test_update_task_updates_timestamp() -> None:
    """更新后 updated_at 应变化。"""
    create_resp = client.post("/tasks", json={"title": "时间戳测试"})
    task_id = create_resp.json()["id"]
    original_updated_at = create_resp.json()["updated_at"]

    response = client.put(f"/tasks/{task_id}", json={"title": "时间戳测试-已更新"})
    assert response.status_code == 200
    assert response.json()["updated_at"] != original_updated_at


def test_update_task_not_found() -> None:
    """更新不存在的任务应返回 404。"""
    fake_id = str(uuid.uuid4())
    response = client.put(f"/tasks/{fake_id}", json={"title": "不会成功"})
    assert response.status_code == 404


def test_update_task_validation() -> None:
    """更新时非法 status 应返回 422。"""
    create_resp = client.post("/tasks", json={"title": "验证"})
    task_id = create_resp.json()["id"]
    response = client.put(f"/tasks/{task_id}", json={"status": "bad_status"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# 删除
# ---------------------------------------------------------------------------


def test_delete_task() -> None:
    """删除存在的任务应返回 204。"""
    create_resp = client.post("/tasks", json={"title": "待删除"})
    task_id = create_resp.json()["id"]
    response = client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204


def test_delete_task_not_found() -> None:
    """删除不存在的任务应返回 404。"""
    fake_id = str(uuid.uuid4())
    response = client.delete(f"/tasks/{fake_id}")
    assert response.status_code == 404


def test_delete_task_then_get_404() -> None:
    """删除后再获取应返回 404。"""
    create_resp = client.post("/tasks", json={"title": "删除后不可见"})
    task_id = create_resp.json()["id"]
    client.delete(f"/tasks/{task_id}")
    response = client.get(f"/tasks/{task_id}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 响应格式
# ---------------------------------------------------------------------------


def test_error_response_format_404() -> None:
    """404 响应应包含 detail 字段。"""
    fake_id = str(uuid.uuid4())
    response = client.get(f"/tasks/{fake_id}")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_crud_idempotent_flow() -> None:
    """完整 CRUD 流程验证：创建→读取→更新→删除→再读 404。"""
    # Create
    create_resp = client.post(
        "/tasks",
        json={
            "title": "端到端任务",
            "description": "完整流程测试",
            "status": "todo",
        },
    )
    assert create_resp.status_code == 201
    task_id = create_resp.json()["id"]

    # Read
    get_resp = client.get(f"/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == TaskStatus.TODO.value

    # Update
    update_resp = client.put(
        f"/tasks/{task_id}",
        json={"status": TaskStatus.IN_PROGRESS.value},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == TaskStatus.IN_PROGRESS.value

    # Delete
    delete_resp = client.delete(f"/tasks/{task_id}")
    assert delete_resp.status_code == 204

    # Verify deleted
    final_resp = client.get(f"/tasks/{task_id}")
    assert final_resp.status_code == 404
