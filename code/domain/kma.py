"""기상청 API허브 호출과 응답 파싱."""
import time

import requests

from config import DATA_DIR, require_env

API_URL = "https://apihub.kma.go.kr/api/typ01/url"
RAW_DIR = DATA_DIR / "raw"

# kma_sfcdd3 응답의 열 위치(0부터). 전체 목록은 help=1로 확인할 수 있다.
COLUMNS = {"ta_avg": 10, "ta_max": 11, "ta_min": 13, "hm_avg": 18, "ws_avg": 2, "rn_day": 38}


def request_kma(path: str, params: dict, max_retries: int = 4) -> str:
    """API허브를 호출해 본문을 돌려준다. 429·5xx는 기다렸다가 다시 시도한다. (NF2006)"""
    wait = 2.0
    for attempt in range(1, max_retries + 1):
        response = requests.get(
            f"{API_URL}/{path}", params={**params, "authKey": require_env("KMA_API_KEY")}, timeout=180
        )
        if response.status_code == 200:
            text = response.content.decode("euc-kr")
            if text.lstrip().startswith("{"):  # 오류도 200 대신 JSON 본문으로 오는 경우가 있다
                raise RuntimeError(f"{path} 호출 실패: {text[:200]}")
            return text
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(float(response.headers.get("Retry-After") or wait))
            wait *= 2
            continue
        # 키가 URL에 들어 있으므로 응답 본문만 보여 준다.
        raise RuntimeError(f"{path} 호출 실패 ({response.status_code}): {response.text[:200]}")
    raise RuntimeError(f"{path} 호출이 계속 실패했습니다. 잠시 뒤 다시 실행해 주세요.")


def fetch_daily_year(year: int) -> str:
    """전국 ASOS 지점의 1년치 일자료 원문. 한 번 받은 해는 data/raw에서 읽는다. (NF2002)"""
    cache = RAW_DIR / f"sfcdd_{year}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    text = request_kma("kma_sfcdd3.php", {"tm1": f"{year}0101", "tm2": f"{year}1231", "stn": 0, "help": 0})
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    time.sleep(0.5)
    return text


def parse_daily(text: str) -> list[dict]:
    """일자료 원문 → [{"date": "20161015", "stn": "108", "ta_avg": 19.1, ...}]. 결측은 None."""
    rows = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split()
        row = {"date": fields[0], "stn": fields[1]}
        for name, index in COLUMNS.items():
            value = float(fields[index])
            if name == "rn_day" and value == -9.0:
                value = 0.0  # 일강수량 -9.0 = 강수 없음
            row[name] = None if value <= -9 else value
        rows.append(row)
    return rows
