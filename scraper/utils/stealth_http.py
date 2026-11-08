"""HTTP client for JSON endpoints that rotates proxies and browser-like headers.

Proxies come from the ``proxy_list`` argument or, failing that, from the
``ROTATING_PROXY_URL`` environment variable, which may hold one URL or several
separated by commas or whitespace.

Each attempt opens its own ``httpx.Client`` bound to one proxy. On a 403/429 or a
network error the client is closed, a different proxy is picked from the pool
and a fresh client is opened for the next attempt. httpx fixes a client's proxy
at construction time, so swapping proxies means building a new client.
"""

from __future__ import annotations

import logging
import os
import random
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# HTTP/2 needs the optional "h2" package; fall back to HTTP/1.1 when it is absent
# instead of failing on every request.
try:
    import h2  # noqa: F401

    _HTTP2_AVAILABLE = True
except ImportError:
    _HTTP2_AVAILABLE = False

BLOCKED_STATUS_CODES = frozenset({403, 429})

_USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
)


def _parse_proxies(proxy_list: list[str] | None) -> list[str]:
    """Return a clean, de-duplicated proxy list from the argument or the environment."""
    if proxy_list is None:
        raw = os.getenv("ROTATING_PROXY_URL", "")
        candidates = raw.replace(",", " ").split()
    else:
        candidates = proxy_list
    seen: dict[str, None] = {}
    for proxy in candidates:
        proxy = (proxy or "").strip()
        if proxy:
            seen.setdefault(proxy, None)
    return list(seen)


class StealthHTTPClient:
    def __init__(
        self,
        proxy_list: list[str] | None = None,
        *,
        max_attempts: int = 3,
        timeout: float = 15.0,
        min_delay: float = 3.0,
        max_delay: float = 7.0,
    ) -> None:
        self.proxies = _parse_proxies(proxy_list)
        self.max_attempts = max(1, max_attempts)
        self.timeout = timeout
        self.min_delay = min_delay
        self.max_delay = max_delay

    def _get_random_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="130", "Google Chrome";v="130"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

    def _pick_proxy(self, exclude: str | None = None) -> str | None:
        """Pick a random proxy, avoiding ``exclude`` when another one is available."""
        if not self.proxies:
            return None
        pool = [p for p in self.proxies if p != exclude] or self.proxies
        return random.choice(pool)

    def _new_client(self, proxy: str | None) -> httpx.Client:
        return httpx.Client(
            http2=_HTTP2_AVAILABLE,
            proxy=proxy,
            headers=self._get_random_headers(),
            timeout=self.timeout,
        )

    @staticmethod
    def _blocked_wait(response: httpx.Response, attempt: int) -> float:
        """Seconds to wait after a 403/429; honours a numeric Retry-After, capped at 60s."""
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(float(retry_after), 60.0)
        return 5.0 * (attempt + 1)

    def _send(self, method: str, url: str, kwargs: dict[str, Any]) -> httpx.Response:
        """Run the retry loop and return the final ``httpx.Response``.

        Sleeps a random human-like delay first. Retries on 403/429 and on network
        errors, each time on a new client with a different proxy. If every attempt
        was blocked, returns the last blocked response; if every attempt failed on
        the network, re-raises the last network error. Any other status is returned
        as it is, without retrying.
        """
        time.sleep(random.uniform(self.min_delay, self.max_delay))

        proxy: str | None = None
        last_error: httpx.TransportError | None = None
        last_blocked: httpx.Response | None = None

        for attempt in range(self.max_attempts):
            proxy = self._pick_proxy(exclude=proxy)
            is_last = attempt == self.max_attempts - 1
            try:
                with self._new_client(proxy) as client:
                    response = client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning(
                    "stealth_http: network error on attempt %d/%d: %s",
                    attempt + 1, self.max_attempts, type(exc).__name__,
                )
                if not is_last:
                    time.sleep(2.0)
                continue

            if response.status_code in BLOCKED_STATUS_CODES:
                last_error = None
                last_blocked = response
                logger.warning(
                    "stealth_http: HTTP %d on attempt %d/%d, switching proxy",
                    response.status_code, attempt + 1, self.max_attempts,
                )
                if not is_last:
                    time.sleep(self._blocked_wait(response, attempt))
                continue

            return response

        if last_error is not None:
            raise last_error
        assert last_blocked is not None
        return last_blocked

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Drop-in for ``httpx.request``: same keyword arguments, real ``httpx.Response``.

        Like httpx, a non-2xx status is returned, not raised; network errors raise
        ``httpx.TransportError`` subclasses. Headers passed by the caller override the
        rotating browser headers.
        """
        return self._send(method, url, kwargs)

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Drop-in for ``httpx.get``."""
        return self._send("GET", url, kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Drop-in for ``httpx.post``."""
        return self._send("POST", url, kwargs)

    def fetch(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``url`` and return the decoded JSON body.

        Returns ``{}`` if every attempt was blocked, re-raises the last network
        error if every attempt failed on the network, and raises
        ``httpx.HTTPStatusError`` for any other non-2xx status.
        """
        response = self._send("GET", url, {"params": params})
        if response.status_code in BLOCKED_STATUS_CODES:
            return {}
        response.raise_for_status()
        return response.json()
