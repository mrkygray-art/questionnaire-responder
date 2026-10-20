"""Usage limits: a per-visitor hourly limit and a whole-site daily cap.

The counters live in Upstash Redis (shared by every Vercel server instance) when
UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN are set. The Vercel integration may name them
KV_REST_API_URL / KV_REST_API_TOKEN, which are accepted too. If Redis is not configured or cannot
be reached, the limiter falls back to counting in this instance's memory: weaker, but the demo
keeps working. Visitor IPs are hashed before they are used as keys; raw IPs are never stored.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone

log = logging.getLogger("responder.ratelimit")

HOUR, DAY_TTL = 3600, 25 * 3600  # the daily key outlives its UTC day a little, then expires on its own


class LimitExceeded(Exception):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason, self.message = reason, message


HOURLY_MESSAGE = "Hourly limit reached for your connection. Please try again later."
DAILY_MESSAGE = "The live demo has reached today's limit. The recorded replay on the portfolio still works."


def find_store(environ) -> tuple[str | None, str | None]:
    """Find the Redis REST URL and token. Vercel's Marketplace lets you add a prefix to the variable
    names (for example STORAGE_KV_REST_API_URL), so match on the name's ending and pair the token
    that shares the same prefix. The read-only token is never used."""
    for url_name in ("UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"):
        token_name = url_name.replace("URL", "TOKEN")
        for name, value in environ.items():
            if name.endswith(url_name) and value:
                token = environ.get(name[: -len(url_name)] + token_name)
                if token:
                    return value, token
    return None, None


class Limiter:
    def __init__(self, hourly: int = 20, daily: int = 300, url: str | None = None,
                 token: str | None = None, salt: str = "", timeout: float = 1.5):
        self.hourly, self.daily = hourly, daily
        self.url, self.token, self.salt, self.timeout = (url or "").rstrip("/"), token, salt, timeout
        self._mem_ip: dict[str, deque] = defaultdict(deque)
        self._mem_day: dict[str, int] = {}

    @classmethod
    def from_env(cls, environ=None) -> "Limiter":
        environ = os.environ if environ is None else environ
        url, token = find_store(environ)
        return cls(
            hourly=int(environ.get("HOURLY_LIMIT", "20")),
            daily=int(environ.get("DAILY_LIMIT", "300")),
            url=url, token=token,
            salt=environ.get("RL_SALT", "questionnaire-responder"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.url and self.token)

    # --- Redis over Upstash's REST API: POST a JSON array [COMMAND, arg, ...], read {"result": ...} ---
    def _redis(self, *cmd):
        req = urllib.request.Request(
            self.url, data=json.dumps(list(cmd)).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read())["result"]

    def _incr(self, key: str, ttl: int) -> int:
        n = int(self._redis("INCR", key))
        if n == 1:  # first hit in this window: start the clock
            self._redis("EXPIRE", key, ttl)
        return n

    def status(self) -> str:
        """'shared' only if the shared store actually answers right now."""
        if not self.configured:
            return "memory (shared store not configured)"
        try:
            return "shared" if self._redis("PING") == "PONG" else "memory (shared store unreachable)"
        except Exception:
            return "memory (shared store unreachable)"

    def _ip_key(self, ip: str) -> str:
        return "rl:h:" + hashlib.sha256(f"{self.salt}:{ip}".encode()).hexdigest()[:16]

    def check(self, ip: str) -> None:
        """Count one question. Raises LimitExceeded when the visitor or the whole site is over."""
        if self.configured:
            try:
                return self._check_shared(ip)
            except LimitExceeded:
                raise
            except Exception as exc:  # network, auth, or Redis trouble: do not break the demo
                log.warning("shared limiter failed (%s: %s); using memory", type(exc).__name__, str(exc)[:200])
        self._check_memory(ip)

    def _check_shared(self, ip: str) -> None:
        if self._incr(self._ip_key(ip), HOUR) > self.hourly:
            raise LimitExceeded("hourly", HOURLY_MESSAGE)  # blocked visitors do not use up the site's daily budget
        day = "rl:d:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._incr(day, DAY_TTL) > self.daily:
            raise LimitExceeded("daily", DAILY_MESSAGE)

    def _check_memory(self, ip: str) -> None:
        now, window, key = time.time(), self._mem_ip[self._ip_key(ip)], datetime.now(timezone.utc).strftime("%Y-%m-%d")
        while window and now - window[0] > HOUR:
            window.popleft()
        if len(window) >= self.hourly:
            raise LimitExceeded("hourly", HOURLY_MESSAGE)
        if self._mem_day.get(key, 0) >= self.daily:
            raise LimitExceeded("daily", DAILY_MESSAGE)
        window.append(now)
        self._mem_day = {key: self._mem_day.get(key, 0) + 1}
