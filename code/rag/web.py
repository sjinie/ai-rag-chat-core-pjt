"""허용 출처에만 요청하는 HTTP GET. User-Agent·호출 간격·재시도를 한곳에서 지킨다. (NF2006)"""
import os
import time
from urllib.parse import urljoin, urlparse

import requests

from config import CONFIG

ALLOWED_HOSTS = set(CONFIG["web"]["allowed_hosts"])
MIN_INTERVAL = 0.5
MAX_TRIES = 4
MAX_REDIRECTS = 3
_last_call: dict[str, float] = {}


class BlockedHost(Exception):
    """허용 목록 밖 호스트로 요청하려 했다."""


def user_agent() -> str:
    contact = os.environ.get("WIKI_CONTACT", "").strip()
    return f"WeatherRAG/0.1 ({contact}) python-requests" if contact else "WeatherRAG/0.1 python-requests"


def _check(url: str) -> str:
    host = urlparse(url).hostname or ""
    if host not in ALLOWED_HOSTS:
        raise BlockedHost(f"허용되지 않은 출처: {host}")
    return host


def _wait_turn(host: str) -> None:
    gap = time.monotonic() - _last_call.get(host, 0.0)
    if gap < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - gap)
    _last_call[host] = time.monotonic()


def get(url: str, params: dict | None = None, session=requests) -> requests.Response:
    """허용 호스트면 GET한다. 리다이렉트도 같은 검사를 거친다.

    429·5xx·연결 오류는 Retry-After(없으면 2초부터 두 배)만큼 기다려 최대 4번 시도한다.
    실패 메시지에는 URL·쿼리를 넣지 않는다 (NF2004).
    """
    host = _check(url)
    wait = 2.0
    for attempt in range(1, MAX_TRIES + 1):
        _wait_turn(host)
        try:
            response = session.get(url, params=params, headers={"User-Agent": user_agent()},
                                   allow_redirects=False, timeout=30)
            for _ in range(MAX_REDIRECTS):
                if response.status_code not in (301, 302, 303, 307, 308):
                    break
                url = urljoin(url, response.headers.get("Location", ""))
                host = _check(url)
                _wait_turn(host)
                response = session.get(url, headers={"User-Agent": user_agent()}, allow_redirects=False, timeout=30)
                params = None
        except requests.RequestException as e:
            if attempt == MAX_TRIES:
                raise RuntimeError(f"{host} 연결 실패: {type(e).__name__}") from None
            time.sleep(wait)
            wait *= 2
            continue
        if response.status_code == 429 or response.status_code >= 500:
            if attempt == MAX_TRIES:
                raise RuntimeError(f"{host} 연결 실패: HTTP {response.status_code}")
            time.sleep(float(response.headers.get("Retry-After") or wait))
            wait *= 2
            continue
        if response.status_code != 200:
            raise RuntimeError(f"{host} 연결 실패: HTTP {response.status_code}")
        return response
    raise RuntimeError(f"{host} 연결 실패")
