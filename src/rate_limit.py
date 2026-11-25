import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    """Allow at most `limit` requests per client IP in any `window` seconds."""

    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self.hits: dict[str, deque] = defaultdict(deque)

    async def __call__(self, request: Request) -> None:
        now = time.monotonic()
        client = request.client.host if request.client else "unknown"
        recent = self.hits[client]

        # Forget requests that fell out of the window.
        while recent and recent[0] <= now - self.window:
            recent.popleft()

        if len(recent) >= self.limit:
            retry_after = int(self.window - (now - recent[0])) + 1
            raise HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={"Retry-After": str(retry_after)},
            )

        recent.append(now)


login_limiter = RateLimiter(limit=5, window=60)
ask_limiter = RateLimiter(limit=20, window=60)
