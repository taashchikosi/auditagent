"""Edge protection for the paid endpoints — token gate + rate limiter.

The `/review` and `/compare` routes call a real LLM, so an unauthenticated,
unthrottled public deployment is a direct cost/abuse vector (anyone can run up
the API bill). This module adds two FastAPI dependencies, deliberately
dependency-light (no slowapi) so the container stays slim:

  * require_token  — if AUDITAGENT_API_TOKEN is set, the request must carry
                     `Authorization: Bearer <token>`; otherwise 401. If the env
                     var is UNSET, the gate is open (local dev / tests / the
                     zero-config demo) — fail-open is intentional for DX, and
                     production sets the token.
  * rate_limit     — in-memory fixed-window cap per client (token or IP).
                     Defaults: 20 requests / 60 s. Returns 429 when exceeded.

In-memory state is per-process: correct for the single always-on container this
ships as. A multi-replica deployment would move the window to Redis — the
dependency interface stays identical.
"""

from __future__ import annotations

import hmac
import os
import threading
import time

from fastapi import Header, HTTPException, Request


def _expected_token() -> str | None:
    tok = os.environ.get("AUDITAGENT_API_TOKEN", "").strip()
    return tok or None


def require_token(authorization: str | None = Header(default=None)) -> None:
    """Reject the request unless it carries the configured bearer token.

    Fail-open when no token is configured so local/demo use needs zero setup;
    enforced the moment AUDITAGENT_API_TOKEN is present in the environment.
    """
    expected = _expected_token()
    if expected is None:
        return  # gate disabled (dev / demo)
    prefix = "Bearer "
    supplied = authorization[len(prefix):] if (authorization or "").startswith(prefix) else ""
    # Constant-time compare so a timing side-channel can't leak the token.
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="missing or invalid API token")


class _FixedWindowLimiter:
    """Per-key fixed-window counter. Thread-safe, in-process."""

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Return (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window_s:
                start, count = now, 0  # window rolled over
            count += 1
            self._hits[key] = (start, count)
            if count > self.limit:
                return False, int(self.window_s - (now - start)) + 1
            return True, 0


def _build_limiter() -> _FixedWindowLimiter:
    limit = int(os.environ.get("AUDITAGENT_RATE_LIMIT", "20"))
    window = float(os.environ.get("AUDITAGENT_RATE_WINDOW_SEC", "60"))
    return _FixedWindowLimiter(limit, window)


_LIMITER = _build_limiter()


def _client_key(request: Request, authorization: str | None) -> str:
    """Rate-limit by token when present (stable across IPs), else client IP.

    Behind the shared VPS reverse proxy, `request.client.host` is the PROXY's
    IP for every caller — which would collapse all clients into one bucket. So
    when an `X-Forwarded-For` is present we key on its left-most (original
    client) entry instead. Trust this header only because the proxy sets it; a
    direct-to-app deployment falls back to the socket peer.
    """
    if authorization and authorization.startswith("Bearer "):
        return "tok:" + authorization[7:][:16]
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return "ip:" + fwd.split(",")[0].strip()
    client = request.client
    return "ip:" + (client.host if client else "unknown")


def rate_limit(
    request: Request, authorization: str | None = Header(default=None)
) -> None:
    """Throttle a client to AUDITAGENT_RATE_LIMIT requests per window."""
    allowed, retry_after = _LIMITER.check(_client_key(request, authorization))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="rate limit exceeded — slow down",
            headers={"Retry-After": str(retry_after)},
        )


def reset_limiter_for_tests() -> None:
    """Test hook: rebuild the limiter so each test starts from a clean window."""
    global _LIMITER
    _LIMITER = _build_limiter()
