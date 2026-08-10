"""限流中间件 —— 基于 limits 库按客户端 IP 计数。

采用 ASGI 中间件方式实现，无需修改路由函数签名，
避免了装饰器签名不匹配导致的 422 / 500 问题。
"""

from __future__ import annotations

import time
from typing import Callable

from limits import RateLimitItemPerMinute
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

from app.core.config import settings


class RateLimitMiddleware:
    """全局限流中间件（按 IP 计数）。

    当 APP_RATE_LIMIT_ENABLED 为 False 时直接放行。
    触发限流时返回 429 并附带 Retry-After 响应头。

    设计：
    - 每次 check_and_hit 都会根据 settings 计算当前 limit，
      允许通过环境变量或 monkeypatch 动态调整阈值。
    """

    def __init__(self) -> None:
        self._storage = MemoryStorage()
        self._strategy = FixedWindowRateLimiter(storage=self._storage)

    # 直接读 settings，支持 monkeypatch 后立即生效
    @property
    def enabled(self) -> bool:
        return settings.RATE_LIMIT_ENABLED

    @property
    def window_seconds(self) -> int:
        return settings.RATE_LIMIT_WINDOW_SECONDS

    @property
    def requests_per_window(self) -> int:
        return settings.RATE_LIMIT_REQUESTS

    def _make_limit_item(self):
        return RateLimitItemPerMinute(self.requests_per_window)

    def reset_storage(self) -> None:
        """重置内存存储 —— 用于测试之间隔离。"""
        self._storage = MemoryStorage()
        self._strategy = FixedWindowRateLimiter(storage=self._storage)

    def check_and_hit(self, client_ip: str) -> tuple[bool, int]:
        """检查并消耗一次请求配额。

        返回:
            (是否允许通过, 剩余可用秒数的 Retry-After；允许通过时为 0)
        """
        if not self.enabled:
            return True, 0

        limit_item = self._make_limit_item()
        key = f"rl:{client_ip}"
        if self._strategy.hit(limit_item, key, cost=1):
            return True, 0

        # 被限流：计算多少秒后重置
        now = int(time.time())
        window = self.window_seconds
        reset_at = ((now // window) + 1) * window
        retry_after = max(1, reset_at - now)
        return False, retry_after


# ---------------------------------------------------------------------------
# ASGI 中间件工厂
# ---------------------------------------------------------------------------


def build_rate_limit_asgi_app(
    app: Callable, middleware: RateLimitMiddleware
) -> Callable:
    """包装 ASGI app，在进入路由前执行限流检查。

    注意：每次请求都会读取 middleware 实例，
    因此替换/修改传入的 middleware 实例（或其内部设置）都会立即生效。
    """

    async def asgi_app(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        client = scope.get("client") or ("127.0.0.1", 0)
        client_ip: str = client[0]

        allowed, retry_after = middleware.check_and_hit(client_ip)
        if allowed:
            await app(scope, receive, send)
            return

        body = (
            b'{"detail":"\xe8\xaf\xb7\xe6\xb1\x82\xe8\xbf\x87\xe4\xba\x8e\xe9\xa2\x91\xe7\xb9\x81'
            b'\xef\xbc\x8c\xe8\xaf\xb7\xe7\xa8\x8d\xe5\x90\x8e\xe5\x86\x8d\xe8\xaf\x95"}'
        )
        retry_after_bytes = str(retry_after).encode("ascii")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
            (b"retry-after", retry_after_bytes),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body})

    return asgi_app


# 全局单例
rate_limit_middleware = RateLimitMiddleware()
