"""Polite, cached HTTP GET. One honest User-Agent, a pause between live requests, and a disk cache so nothing is fetched twice."""
from __future__ import annotations

import hashlib
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

CACHE = pathlib.Path(__file__).resolve().parent.parent / "data" / "cache"
UA = "finn-prototype/0.1 (student project; read-only; contact via repository owner)"
_last = 0.0


class NotFound(RuntimeError):
    """HTTP 404: the page does not exist (as opposed to a transient failure)."""


HOST_PAUSE = {"www.screener.in": 4.0}  # seconds between live requests; screener.in answers 429 to anything faster


def get(url: str, ttl: float = 6 * 3600, pause: float | None = None, timeout: float = 60, tries: int = 4) -> bytes:
    """Fetch `url`, reusing a cached copy younger than `ttl` seconds (use ttl=float('inf') for immutable files such as PDFs)."""
    global _last
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / hashlib.sha256(url.encode()).hexdigest()[:24]
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return path.read_bytes()
    if pause is None:
        pause = HOST_PAUSE.get(urllib.parse.urlparse(url).netloc, 1.0)
    for attempt in range(tries):
        wait = pause - (time.time() - _last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
            _last = time.time()
            path.write_bytes(body)
            return body
        except urllib.error.HTTPError as err:
            _last = time.time()
            if err.code == 429 and attempt < tries - 1:  # slow down, as asked, then try again
                time.sleep(min(float(err.headers.get("Retry-After") or 0) or 15 * 2 ** attempt, 120))
                continue
            if path.exists():  # stale cache beats a failed refresh
                return path.read_bytes()
            if err.code == 404:
                raise NotFound(f"404 for {url}") from None
            raise RuntimeError(f"HTTP {err.code} for {url}") from None
    raise RuntimeError(f"gave up on {url}")
