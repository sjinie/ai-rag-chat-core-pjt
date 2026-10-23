"""기상청 API허브 호출과 응답 파싱."""
import re
import time
from datetime import date, datetime, timedelta

import requests

from config import DATA_DIR, require_env

API_URL = "https://apihub.kma.go.kr/api/typ01/url"
RAW_DIR = DATA_DIR / "raw"

# 근거에 보여 줄 원문 출처. API 주소에는 키가 들어 있어 화면에 쓸 수 없다. (F2008, NF2004)
ASOS_SOURCE_URL = "https://data.kma.go.kr/data/grnd/selectAsosRltmList.do?pgmNo=36"
# shortcut: 과거 개황마다 열어 볼 공개 주소를 아직 못 찾아 API허브 첫 화면을 쓴다. 찾으면 개황별 주소로 바꾼다.
FORECAST_SOURCE_URL = "https://apihub.kma.go.kr/"

# kma_sfcdd3 응답의 열 위치(0부터). 전체 목록은 help=1로 확인할 수 있다.
COLUMNS = {"ta_avg": 10, "ta_max": 11, "ta_min": 13, "hm_avg": 18, "ws_avg": 2, "rn_day": 38}


def request_kma(path: str, params: dict, max_retries: int = 4) -> str:
    """API허브를 호출해 본문을 돌려준다. 429·5xx·연결 오류는 기다렸다가 다시 시도한다. (NF2006)"""
    wait = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                f"{API_URL}/{path}", params={**params, "authKey": require_env("KMA_API_KEY")}, timeout=180
            )
        except requests.RequestException as e:
            # requests 예외 메시지에는 키가 든 URL 전체가 들어 있으므로 종류만 남긴다 (NF2004)
            if attempt == max_retries:
                raise RuntimeError(f"{path} 연결 실패: {type(e).__name__}") from None
            time.sleep(wait)
            wait *= 2
            continue
        if response.status_code == 200:
            text = response.content.decode("cp949")  # EUC-KR 상위 호환. 개황 원문에는 EUC-KR 밖의 한글이 섞여 있다
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


def cached_request(name: str, path: str, params: dict, keep: bool = True) -> tuple[str, str]:
    """원문과 수집일(YYYY-MM-DD)을 돌려준다. 한 번 받은 원문은 data/raw/{name}에서 읽는다. (NF2002)

    keep=False(아직 끝나지 않은 올해 자료)는 저장하지 않는다. 저장하면 다음 달에도 그 시점 자료만 남는다.
    """
    cache = RAW_DIR / name
    if cache.exists():
        return cache.read_text(encoding="utf-8"), date.fromtimestamp(cache.stat().st_mtime).isoformat()
    text = request_kma(path, params)
    if keep:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
    time.sleep(0.5)
    return text, date.today().isoformat()


def fetch_daily_year(year: int) -> str:
    """전국 ASOS 지점의 1년치 일자료 원문."""
    return cached_request(f"sfcdd_{year}.txt", "kma_sfcdd3.php",
                          {"tm1": f"{year}0101", "tm2": f"{year}1231", "stn": 0, "help": 0},
                          keep=year < date.today().year)[0]


def fetch_stations() -> dict:
    """현재 운영 중인 ASOS 지점 정보. data/raw/stn_inf.txt를 지우면 새로 받는다."""
    return parse_stations(cached_request("stn_inf.txt", "stn_inf.php", {"inf": "SFC", "stn": "", "help": 0})[0])


def parse_stations(text: str) -> dict:
    """지점 정보 원문 → {"108": {"name": "서울", "sido": "서울특별시", "address": ..., "lat", "lon", "height", "mountain"}}"""
    stations = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split()
        # 영문명에 공백이 있는 행(Jeongseon Gun)은 열이 밀리므로, 예보구역코드는 모양으로, 주소는 첫 한글 단어부터 찾는다
        fct_id = next(t for t in f[12:] if re.fullmatch(r"\d{2}[A-Z]\w+", t))
        start = next(i for i in range(12, len(f)) if any("가" <= ch <= "힣" for ch in f[i]))
        address = " ".join(f[start:])
        mountain = address.startswith("(산지)")
        address = address.removeprefix("(산지)")
        stations[f[0]] = {"name": f[10], "sido": address.split()[0], "address": address, "lat": float(f[2]),
                          "lon": float(f[1]), "height": float(f[4]), "mountain": mountain, "fct_id": fct_id}
    return stations


def fetch_forecast_year(office: str, year: int) -> tuple[str, str]:
    """관할 지방청 하나의 1년치 개황 원문(하루 05·11·17시 3회)과 수집일."""
    return cached_request(f"fct_afs_ds_{office}_{year}.txt", "fct_afs_ds.php",
                          {"stn": office, "tmfc1": f"{year}01010000", "tmfc2": f"{year}12312359", "disp": 0, "help": 0},
                          keep=year < date.today().year)


def parse_forecasts(text: str) -> list[dict]:
    """개황 원문 → [{"office": "156", "tmfc": "202110220500", "body": "□ (종합) ..."}]"""
    docs = []
    for m in re.finditer(r"^\$0#(\d+)#(\d{12})#.*?\n\$1#\n(.*?)#\s*\n\$2#", text, re.M | re.S):
        docs.append({"office": m.group(1), "tmfc": m.group(2), "body": m.group(3).strip()})
    return docs


def today_summary(body: str) -> str:
    """개황에서 '종합'과 '오늘' 문단만 남긴다. 내일·모레 문장이 섞이면 다른 날과 비슷하다고 잘못 잡힌다."""
    kept, keep = [], False
    for line in body.splitlines():
        s = line.strip()
        if s.startswith(("□", "○", "*")):
            keep = s.startswith("□ (종합)") or s.startswith("○ (오늘")
        if keep and s:
            kept.append(s)
    text = " ".join(kept)
    text = re.sub(r"\(오늘[^)]*\)", "(오늘)", text)
    return re.sub(r"\d{1,2}일", "", text)  # 날짜 숫자는 유사도에 잡음만 된다


def fetch_latest_forecast(office: str, now: datetime) -> dict | None:
    """관할 지방청의 가장 최근 개황. 05시 이전이거나 오늘 05시분이 아직 없으면 전날 17시분을 쓴다."""
    def latest(tmfc1: str, tmfc2: str) -> dict | None:
        docs = parse_forecasts(request_kma("fct_afs_ds.php", {"stn": office, "tmfc1": tmfc1, "tmfc2": tmfc2,
                                                              "disp": 0, "help": 0}))
        return max(docs, key=lambda d: d["tmfc"]) if docs else None

    yesterday_17 = (now - timedelta(days=1)).strftime("%Y%m%d") + "1700"
    found = None if now.hour < 5 else latest(now.strftime("%Y%m%d") + "0000", now.strftime("%Y%m%d%H%M"))
    found = found or latest(yesterday_17, yesterday_17)
    return {**found, "summary": today_summary(found["body"])} if found else None


def live_forecast_doc(f: dict, office_name: str) -> tuple[str, str, dict]:
    """오늘 개황을 live_forecasts 컬렉션에 넣을 (ID, 오늘 문단, 메타데이터). 항목 자체 문서는 항상 색인한다 (F2004)."""
    t = f["tmfc"]
    doc_id = f"live:{f['office']}:{t}"
    return doc_id, f["summary"], {
        "source_type": "kma_forecast_live", "doc_id": doc_id, "office": f["office"], "tmfc": t,
        "title": f"{office_name} 단기예보 개황 · {t[:4]}-{t[4:6]}-{t[6:8]} {t[8:10]}시 발표",
        "url": FORECAST_SOURCE_URL, "body": f["body"], "collected_at": date.today().isoformat()}


def fetch_today_obs(stn: str, today: date) -> dict | None:
    """오늘 일자료(하루가 끝나기 전이라 결측이 많다). 이 엔드포인트는 쉼표로 구분된다."""
    text = request_kma("kma_sfcdd.php", {"tm": today.strftime("%Y%m%d"), "stn": stn, "help": 0})
    rows = parse_daily("\n".join(line.replace(",", " ") for line in text.splitlines()))
    return rows[0] if rows else None


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
            # 기온 결측은 -99.0. -9 미만 기온은 실제 값이다(대관령 1월 -20.9℃). 습도·풍속은 -9.0이 결측
            row[name] = None if value <= -99 or (value <= -9 and not name.startswith("ta")) else value
        rows.append(row)
    return rows


if __name__ == "__main__":
    # 자체 점검: 영문명에 공백이 있는 행(정선군, 실제 응답)은 열이 밀리고, 산지 지점(대관령)은 주소 앞에 (산지)가 붙는다
    sample = (
        "  217  128.67312000   37.38071000 32300       312.00    312.00      1.50     10.00      0.50 105 정선군"
        "               Jeongseon Gun        11D10502 5177025024 ---- 강원특별자치도 정선군 정선읍 애산리\n"
        "  100  128.71834000   37.67713000 35400       772.43    773.43      1.70     10.00      1.40 100 대관령"
        "               Daegwallyeong        11D20201 5176038024 ---- (산지)강원특별자치도 평창군 대관령면 횡계리"
    )
    s = parse_stations(sample)
    assert s["217"]["address"] == "강원특별자치도 정선군 정선읍 애산리" and s["217"]["sido"] == "강원특별자치도"
    assert s["100"]["mountain"] and s["100"]["sido"] == "강원특별자치도" and s["100"]["height"] == 772.43
    assert s["217"]["fct_id"] == "11D10502" and s["100"]["fct_id"] == "11D20201"

    raw = ("$0#156#202610230500#202610230500#2#홍길동#\n$1#\n"
           "□ (종합) 오늘 오후부터 비\n  ○ (오늘, 23일) 구름많음, 밤부터 비\n"
           "                        곳에 따라 천둥.번개\n  ○ (내일, 24일) 비\n"
           "* 예상 강수량(23~25일)\n- 광주.전남: 20~60mm#\n$2#\n#\n$3#\n#\n=\n")
    f = parse_forecasts(raw)
    assert [(d["office"], d["tmfc"]) for d in f] == [("156", "202610230500")]
    summary = today_summary(f[0]["body"])
    assert summary == "□ (종합) 오늘 오후부터 비 ○ (오늘) 구름많음, 밤부터 비 곳에 따라 천둥.번개", summary
    # 실제 응답: 2018-01-12 대관령. 영하 기온은 살리고, 결측 표시(-99.0, 습도·풍속 -9.0)만 None
    cold = ("20180112 100  5.0  4298  27  9.2 1455  27 12.8 1404 -15.6 -10.5 1347 -20.9  610 -23.9  -9.8 -23.7  51.6"
            "  31.0 1310   0.9   1.3   0.9 -9.00  931.1 1030.5 1033.1  843 1027.2 1347 -9.0  9.2  9.8 -9.0 11.94  2.00"
            " 1200   -9.0   -9.0 -9.00   -9.0   -9   -9.0   -9   -9.0   -9   -9.0   -9   -9.0   -9 -99.0 -99.0 -99.0")
    r = parse_daily(cold)[0]
    assert (r["ta_avg"], r["ta_max"], r["ta_min"], r["rn_day"]) == (-15.6, -10.5, -20.9, 0.0), r
    missing = cold.split()
    missing[10], missing[18], missing[2] = "-99.0", "-9.0", "-9.0"
    r = parse_daily(" ".join(missing))[0]
    assert r["ta_avg"] is None and r["hm_avg"] is None and r["ws_avg"] is None, r
    print("kma.py 자체 점검 통과")
