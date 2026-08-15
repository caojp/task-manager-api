"""API 限流功能单元测试。

通过 monkeypatch 修改 settings 中的限流阈值，并调用
rate_limit_middleware.reset_storage() 重置计数器隔离用例。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core import config as config_mod
from app.core.rate_limit import rate_limit_middleware
from app.main import app


@pytest.fixture(autouse=True)
def _reset_rate_limit_storage():
    """每个测试前后重置限流计数器，避免跨用例影响。"""
    rate_limit_middleware.reset_storage()
    yield
    rate_limit_middleware.reset_storage()


# ---------------------------------------------------------------------------
# 基础：正常请求不受影响
# ---------------------------------------------------------------------------


def test_health_under_default_limit() -> None:
    """默认阈值（100/60s）下单次 /health 请求应通过。"""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


# ---------------------------------------------------------------------------
# 触发 429
# ---------------------------------------------------------------------------


def test_rate_limit_returns_429_with_retry_after() -> None:
    """将阈值降到 2 次/窗口，第 3 次请求应返回 429 并带 Retry-After 头。"""
    client = TestClient(app)

    with (
        patch.object(config_mod.settings, "RATE_LIMIT_REQUESTS", 2),
        patch.object(config_mod.settings, "RATE_LIMIT_WINDOW_SECONDS", 60),
    ):
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        # 第 3 次 -> 429
        resp = client.get("/health")
        assert resp.status_code == 429, (
            f"unexpected {resp.status_code}: {resp.content!r}"
        )
        data = resp.json()
        assert "detail" in data
        assert "请求过于频繁" in data["detail"]
        assert "Retry-After" in resp.headers
        retry_after = int(resp.headers["Retry-After"])
        assert retry_after >= 1


def test_rate_limit_429_json_response_format() -> None:
    """429 响应体应是标准 JSON，包含 detail 字段。"""
    client = TestClient(app)
    with (
        patch.object(config_mod.settings, "RATE_LIMIT_REQUESTS", 1),
        patch.object(config_mod.settings, "RATE_LIMIT_WINDOW_SECONDS", 60),
    ):
        client.get("/health")
        resp = client.get("/health")
        assert resp.status_code == 429
        assert resp.headers["content-type"].startswith("application/json")
        assert isinstance(resp.json(), dict)


# ---------------------------------------------------------------------------
# 限流作用于所有端点
# ---------------------------------------------------------------------------


def test_rate_limit_shared_across_endpoints() -> None:
    """不同端点共享同一 IP 的配额。"""
    client = TestClient(app)
    with (
        patch.object(config_mod.settings, "RATE_LIMIT_REQUESTS", 2),
        patch.object(config_mod.settings, "RATE_LIMIT_WINDOW_SECONDS", 60),
    ):
        # 配额 1: /health
        assert client.get("/health").status_code == 200
        # 配额 2: /tasks
        assert client.get("/tasks").status_code == 200
        # 再来一个 /health 也被限流
        resp = client.get("/health")
        assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 关闭限流
# ---------------------------------------------------------------------------


def test_rate_limit_disabled_bypasses() -> None:
    """APP_RATE_LIMIT_ENABLED=False 时，不限制请求次数。"""
    client = TestClient(app)
    with (
        patch.object(config_mod.settings, "RATE_LIMIT_ENABLED", False),
        patch.object(config_mod.settings, "RATE_LIMIT_REQUESTS", 1),
    ):
        # 即使阈值设为 1，连续 10 次也应通过
        for _ in range(10):
            resp = client.get("/health")
            assert resp.status_code == 200, (
                f"expected 200 when disabled, got {resp.status_code}"
            )


# ---------------------------------------------------------------------------
# 状态码正确：CRUD 端点在正常时不被限流
# ---------------------------------------------------------------------------


def test_crud_works_with_tiny_limit_only_when_quota_left() -> None:
    """配额内 CRUD 端点正常，配额耗尽后任意端点 429。"""
    client = TestClient(app)
    with (
        patch.object(config_mod.settings, "RATE_LIMIT_REQUESTS", 3),
        patch.object(config_mod.settings, "RATE_LIMIT_WINDOW_SECONDS", 60),
    ):
        # 配额 1: POST /tasks
        r1 = client.post("/tasks", json={"title": "t1"})
        assert r1.status_code == 201
        task_id = r1.json()["id"]
        # 配额 2: GET /tasks/{id}
        r2 = client.get(f"/tasks/{task_id}")
        assert r2.status_code == 200
        # 配额 3: DELETE
        r3 = client.delete(f"/tasks/{task_id}")
        assert r3.status_code == 204
        # 第 4 次: 429
        r4 = client.get("/tasks")
        assert r4.status_code == 429
