"""错误处理与日志输出单元测试。

覆盖：
1. 统一错误响应格式（所有 4xx/5xx 均含 detail + request_id）
2. 输入校验错误（422）的统一格式
3. 404 路由不存在 / 405 方法不允许
4. 404 业务错误（任务不存在）
5. 422 路径参数格式错误（非法 UUID）
6. 500 内部错误统一格式
7. 日志输出验证（请求日志、错误日志、状态码分级）
8. X-Request-ID 响应头
"""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 统一错误响应格式
# ---------------------------------------------------------------------------


def test_404_route_not_found_has_unified_format(client: TestClient) -> None:
    """访问不存在的路由应返回 404 + 统一格式（detail + request_id）。"""
    resp = client.get("/nonexistent-path")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert "request_id" in body
    assert isinstance(body["detail"], str)


def test_405_method_not_allowed_has_unified_format(client: TestClient) -> None:
    """对 /tasks 使用不支持的方法（PATCH）应返回 405 + 统一格式。"""
    resp = client.patch("/tasks")
    assert resp.status_code == 405
    body = resp.json()
    assert "detail" in body
    assert "request_id" in body


def test_404_task_not_found_has_unified_format(client: TestClient) -> None:
    """获取不存在的任务应返回 404 + 统一格式。"""
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/tasks/{fake_id}")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert "request_id" in body
    assert "任务不存在" in body["detail"]


# ---------------------------------------------------------------------------
# 输入校验（422）
# ---------------------------------------------------------------------------


def test_422_missing_title_unified_format(client: TestClient) -> None:
    """缺少必填字段 title 应返回 422 + 统一格式（detail 为列表）。"""
    resp = client.post("/tasks", json={"description": "无标题"})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert "request_id" in body
    # 校验错误 detail 为列表
    assert isinstance(body["detail"], list)
    assert len(body["detail"]) >= 1
    # 每条错误含 loc / msg / type
    err = body["detail"][0]
    assert "loc" in err
    assert "msg" in err
    assert "type" in err


def test_422_empty_title_unified_format(client: TestClient) -> None:
    """空字符串 title 应返回 422。"""
    resp = client.post("/tasks", json={"title": ""})
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body["detail"], list)


def test_422_invalid_status_enum_unified_format(client: TestClient) -> None:
    """非法 status 枚举值应返回 422。"""
    resp = client.post("/tasks", json={"title": "测试", "status": "invalid_status"})
    assert resp.status_code == 422
    body = resp.json()
    assert isinstance(body["detail"], list)


def test_422_invalid_uuid_path_param(client: TestClient) -> None:
    """路径参数 UUID 格式错误应返回 422 + 统一格式。"""
    resp = client.get("/tasks/not-a-uuid")
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert "request_id" in body
    assert isinstance(body["detail"], list)
    # 错误位置应在 path
    locs = [err["loc"] for err in body["detail"]]
    assert any("path" in loc for loc in locs)


def test_422_title_too_long(client: TestClient) -> None:
    """title 超过 200 字符应返回 422。"""
    resp = client.post("/tasks", json={"title": "x" * 201})
    assert resp.status_code == 422


def test_422_description_too_long(client: TestClient) -> None:
    """description 超过 2000 字符应返回 422。"""
    resp = client.post("/tasks", json={"title": "ok", "description": "x" * 2001})
    assert resp.status_code == 422


def test_422_loc_with_int_index_handled(client: TestClient) -> None:
    """loc 含 int 索引（如 [body, 1]）不应导致 500。

    回归测试：ErrorDetail.loc 原定义为 list[str]，当 FastAPI 校验
    失败的 loc 包含 int（如 JSON 解析错误的字节偏移、数组索引）时，
    构造 ErrorDetail 会二次抛出 ValidationError，把 422 变成 500。
    """
    from app.schemas.error import ErrorResponse

    # 直接验证：loc 含 int 时能正常构造（不抛异常）
    errors = [{"loc": ["body", 1], "msg": "test", "type": "test_error"}]
    body = ErrorResponse.from_validation_error(errors, request_id="test-req")
    assert body.detail[0].loc == ["body", 1]
    dumped = body.model_dump()
    assert dumped["detail"][0]["loc"] == ["body", 1]


# ---------------------------------------------------------------------------
# 500 内部错误
# ---------------------------------------------------------------------------


def test_500_unhandled_exception_unified_format() -> None:
    """未捕获异常应返回 500 + 统一格式（不泄露堆栈）。

    注意：TestClient 默认 raise_server_exceptions=True 会把服务端异常
    重新抛出而不经过异常处理器，这里显式关闭以验证异常处理器行为。
    """
    # 通过 monkeypatch 让仓储抛异常
    from app.api.routers import tasks as tasks_router

    original = tasks_router.task_repository.get_by_id

    def boom(_task_id):
        raise RuntimeError("模拟内部错误")

    tasks_router.task_repository.get_by_id = boom  # type: ignore
    try:
        client = TestClient(app, raise_server_exceptions=False)
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/tasks/{fake_id}")
        assert resp.status_code == 500
        body = resp.json()
        assert body["detail"] == "内部服务器错误"
        assert "request_id" in body
        # 不应泄露内部错误信息
        assert "模拟内部错误" not in str(body)
    finally:
        tasks_router.task_repository.get_by_id = original  # type: ignore


# ---------------------------------------------------------------------------
# X-Request-ID 响应头
# ---------------------------------------------------------------------------


def test_response_has_request_id_header(client: TestClient) -> None:
    """所有响应应包含 X-Request-ID 响应头。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert "x-request-id" in resp.headers
    assert len(resp.headers["x-request-id"]) > 0


def test_error_response_has_request_id_header(client: TestClient) -> None:
    """错误响应也应包含 X-Request-ID 响应头。"""
    resp = client.get("/nonexistent")
    assert resp.status_code == 404
    assert "x-request-id" in resp.headers
    # 响应头与响应体的 request_id 应一致
    body = resp.json()
    assert body["request_id"] == resp.headers["x-request-id"]


# ---------------------------------------------------------------------------
# 日志输出验证
# ---------------------------------------------------------------------------


def test_request_log_emitted_at_info_for_success(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """成功请求（2xx）应在 INFO 级别记录请求日志。"""
    with caplog.at_level(logging.INFO, logger="Task Manager API"):
        resp = client.get("/health")
    assert resp.status_code == 200
    # 至少有一条包含 GET /health 的日志
    health_logs = [
        r for r in caplog.records if "GET" in r.message and "/health" in r.message
    ]
    assert len(health_logs) >= 1
    assert health_logs[-1].levelno == logging.INFO


def test_request_log_emitted_at_warning_for_4xx(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """4xx 请求应在 WARNING 级别记录请求日志。"""
    with caplog.at_level(logging.DEBUG, logger="Task Manager API"):
        resp = client.get("/nonexistent")
    assert resp.status_code == 404
    # 应有 WARNING 级别的请求日志
    warning_logs = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "/nonexistent" in r.message
    ]
    assert len(warning_logs) >= 1


def test_error_log_emitted_for_404_business_error(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """任务不存在的 404 业务错误应记录 WARNING 日志。"""
    fake_id = str(uuid.uuid4())
    with caplog.at_level(logging.DEBUG, logger="Task Manager API"):
        resp = client.get(f"/tasks/{fake_id}")
    assert resp.status_code == 404
    # 应有包含 "任务不存在" 的 WARNING 日志
    not_found_logs = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "任务不存在" in r.message
    ]
    assert len(not_found_logs) >= 1


def test_error_log_emitted_for_422_validation_error(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """输入校验失败应记录 WARNING 日志。"""
    with caplog.at_level(logging.DEBUG, logger="Task Manager API"):
        resp = client.post("/tasks", json={"description": "无标题"})
    assert resp.status_code == 422
    validation_logs = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "输入校验失败" in r.message
    ]
    assert len(validation_logs) >= 1


def test_error_log_emitted_for_500_with_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """500 错误应记录 ERROR 日志并包含堆栈信息。"""
    from app.api.routers import tasks as tasks_router

    original = tasks_router.task_repository.get_by_id

    def boom(_task_id):
        raise RuntimeError("模拟内部错误")

    tasks_router.task_repository.get_by_id = boom  # type: ignore
    try:
        client = TestClient(app, raise_server_exceptions=False)
        fake_id = str(uuid.uuid4())
        with caplog.at_level(logging.ERROR, logger="Task Manager API"):
            resp = client.get(f"/tasks/{fake_id}")
        assert resp.status_code == 500
        # 应有 ERROR 级别日志
        error_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.ERROR and "未捕获异常" in r.message
        ]
        assert len(error_logs) >= 1
        # 日志应包含异常类型，堆栈信息通过 exc_info 输出
        assert "RuntimeError" in error_logs[0].message
        # caplog.text 会包含完整的日志文本（含 exc_info 输出的堆栈）
        full_log_text = caplog.text
        assert "RuntimeError: 模拟内部错误" in full_log_text
    finally:
        tasks_router.task_repository.get_by_id = original  # type: ignore


def test_request_log_includes_client_ip(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """请求日志应包含客户端 IP 字段。"""
    with caplog.at_level(logging.INFO, logger="Task Manager API"):
        resp = client.get("/health")
    assert resp.status_code == 200
    health_logs = [
        r for r in caplog.records if "GET" in r.message and "/health" in r.message
    ]
    assert len(health_logs) >= 1
    assert "ip=" in health_logs[-1].message


def test_rate_limit_log_emitted_at_warning(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """限流触发应记录 WARNING 日志。"""
    from unittest.mock import patch

    from app.core import config as config_mod
    from app.core.rate_limit import rate_limit_middleware

    rate_limit_middleware.reset_storage()
    with (
        patch.object(config_mod.settings, "RATE_LIMIT_REQUESTS", 1),
        patch.object(config_mod.settings, "RATE_LIMIT_WINDOW_SECONDS", 60),
        caplog.at_level(logging.DEBUG, logger="Task Manager API"),
    ):
        client.get("/health")  # 消耗配额
        resp = client.get("/health")  # 触发限流
        assert resp.status_code == 429
        rl_logs = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "限流触发" in r.message
        ]
        assert len(rl_logs) >= 1
