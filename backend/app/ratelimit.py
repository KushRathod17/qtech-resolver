"""
A small in-process throttle for the login endpoint.

Login was completely unthrottled: no rate limit, no lockout, no captcha. With
five known accounts all on `password123`, that is brute-forceable in seconds.

Deliberately dependency-free and in-memory. Two honest caveats:

  * It is PER PROCESS. Run several uvicorn workers and each keeps its own
    counters, so the effective limit multiplies by the worker count. For a
    single-worker dev/small-team deployment that is fine; the moment this is
    scaled out, this should move to Redis (which is what a shared counter store
    is for).
  * It resets on restart. An attacker who can restart your server has already
    won, so this costs nothing real.

Both are acceptable trade-offs *today* and are called out rather than hidden.
"""
import threading
import time
from collections import defaultdict


class FixedWindowLimiter:
    """Count failures per key inside a rolling window; block when they pile up.

    Only FAILURES are counted. A correct password never counts against you, so
    a busy legitimate user is never locked out by their own success.
    """

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        fresh = [t for t in self._hits[key] if now - t < self.window_seconds]
        self._hits[key] = fresh
        return fresh

    def retry_after(self, key: str) -> int:
        """Seconds until this key may try again. 0 means it may try now."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) < self.max_attempts:
                return 0
            oldest = min(hits)
            return max(1, int(self.window_seconds - (now - oldest)))

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._prune(key, now)
            self._hits[key].append(now)

    def reset(self, key: str) -> None:
        """A successful login clears the slate for that key."""
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        """Tests only — otherwise one test's failures throttle the next."""
        with self._lock:
            self._hits.clear()
