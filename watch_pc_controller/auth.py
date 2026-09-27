"""Who may call the API.

Requests from this PC itself are trusted: anything already running here can
do whatever the API does. Every other request must carry a token from
pairing. A handful of paths stay open, because a device needs them to pair.
"""

import ipaddress
import time
from collections import defaultdict, deque
from typing import Callable, Mapping, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

PAIR_PATH = "/api/pair"
PAIR_ATTEMPTS_PER_MINUTE = 10
OPEN_PATHS = frozenset({"/", "/pair", "/orb.js", "/watch-ui.js", PAIR_PATH})


def client_is_local(host: Optional[str]) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    mapped = getattr(address, "ipv4_mapped", None)
    return address.is_loopback or bool(mapped and mapped.is_loopback)


def bearer_token(headers: Mapping[str, str]) -> Optional[str]:
    value = headers.get("authorization", "") or ""
    if value[:7].lower() != "bearer ":
        return None
    return value[7:].strip() or None


class RateLimiter:
    """At most `limit` events per key in any `window_s` seconds."""

    def __init__(self, limit: int, window_s: float = 60.0, clock: Callable[[], float] = time.monotonic):
        self._limit = limit
        self._window = window_s
        self._clock = clock
        self._events: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        events = self._events[key]
        while events and now - events[0] > self._window:
            events.popleft()
        if len(events) >= self._limit:
            return False
        events.append(now)
        return True


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, get_store: Callable, get_limiter: Callable):
        super().__init__(app)
        self._get_store = get_store
        self._get_limiter = get_limiter

    async def dispatch(self, request, call_next):
        path = request.url.path
        host = request.client.host if request.client else None

        if request.method == "OPTIONS":
            return await call_next(request)

        if path == PAIR_PATH and request.method == "POST":
            if not self._get_limiter().allow(host or "?"):
                return JSONResponse({"detail": "יותר מדי ניסיונות. נסה שוב בעוד דקה."}, status_code=429)
            return await call_next(request)

        if client_is_local(host) or path in OPEN_PATHS:
            return await call_next(request)

        if self._get_store().verify(bearer_token(request.headers)) is None:
            return JSONResponse({"detail": "המכשיר לא מצומד"}, status_code=401)
        return await call_next(request)
