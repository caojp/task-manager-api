"""GET /health 端点单元测试。"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check_returns_200() -> None:
    """健康检查应返回 200 状态码。"""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_check_returns_healthy_status() -> None:
    """健康检查响应体应包含 healthy 状态。"""
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"


def test_health_check_includes_service_metadata() -> None:
    """健康检查响应应包含服务名称、版本与时间戳。"""
    response = client.get("/health")
    data = response.json()
    assert data["service"] == "Task Manager API"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data
