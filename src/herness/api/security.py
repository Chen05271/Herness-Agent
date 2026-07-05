"""API 安全 — Key 鉴权与用户级 rate limit。"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from herness.config import Settings


def extract_api_key(
    *,
    authorization: str | None,
    x_api_key: str | None,
) -> str | None:
    """从 Authorization: Bearer 或 X-API-Key 提取密钥。"""
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def require_api_key(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """FastAPI 依赖：配置 API_KEY 时校验请求密钥。"""
    settings: Settings = request.app.state.settings
    expected = settings.api_key.strip()
    if not expected:
        return

    provided = extract_api_key(authorization=authorization, x_api_key=x_api_key)
    if not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或缺失 API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )


class RateLimiter:
    """滑动窗口 rate limiter（进程内，按 user_id 计数）。"""

    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self._limit > 0

    def check(self, key: str) -> bool:
        """尝试占用配额；返回 False 表示超限。"""
        if not self.enabled:
            return True

        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self._window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._limit:
                return False
            bucket.append(now)
            return True


def check_user_rate_limit(request: Request, user_id: str) -> None:
    """校验 user_id 是否超出提交配额。"""
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None or not limiter.enabled:
        return
    if not limiter.check(user_id):
        settings: Settings = request.app.state.settings
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"用户 {user_id!r} 超出速率限制："
                f"{settings.rate_limit_per_user} 次 / {settings.rate_limit_window_seconds}s"
            ),
        )
