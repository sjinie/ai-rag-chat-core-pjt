"""최근 10년 관측을 정형 DB에, 지점 프로필을 VectorDB에 저장한다.

    cd code
    python build_climate.py

1. API허브에서 연도별 전국 ASOS 일자료를 받는다 (data/raw에 캐시, 다시 실행하면 API를 부르지 않는다)
2. 지점별·날짜별 '최근 10년 ±N일' 평균·표준편차를 계산한다 (6개 항목)
3. SQLite data/weather.db : obs_daily(지점 × 날짜 실제 관측), baseline(지점 × MMDD 기준값)
   Chroma station_meta    : 지점 1건 = 지점 정보(주소·고도·관할 지방청) + 월별 평균 텍스트 (ID = 지점번호)
"""
from collections import Counter, defaultdict

from config import CONFIG
from domain.kma import ASOS_SOURCE_URL, fetch_daily_year, fetch_stations, parse_daily
from domain.stations import OFFICES, climate_traits, compute_baselines, monthly_summary, office_for, station_text
from domain.weather_db import connect, get_baseline, get_obs, save_baselines, save_obs
from rag.store import get_store, upsert_changed


def main() -> None:
    start, end = CONFIG["climate"]["start_year"], CONFIG["climate"]["end_year"]
    window = CONFIG["climate"]["window_days"]
    period = f"{start}~{end}"

    print(f"① 일자료 수집 {period}")
    rows = []
    for year in range(start, end + 1):
        year_rows = parse_daily(fetch_daily_year(year))
        rows += year_rows
        print(f"  {year}: {len(year_rows):,}행")

    # 항목 = 지금 운영 중인 지점. 폐쇄된 지점(예: 175 진도, 2019년 8월 종료)은 오늘 날씨와 비교할 수 없어 뺀다
    stations = fetch_stations()
    closed = sorted({r["stn"] for r in rows} - set(stations), key=int)
    if closed:
        print(f"  운영 중이 아니라 제외한 지점번호: {closed}")
    rows = [r for r in rows if r["stn"] in stations]

    print(f"② 최근 10년 ±{window}일 평균·표준편차 계산")
    baselines = compute_baselines(rows, window)
    short = {stn: b[(1, 1)]["years"] for stn, b in baselines.items() if b[(1, 1)]["years"] < end - start + 1}
    if short:
        print("  10년이 안 되는 지점(연도 수): " + ", ".join(f"{stations[s]['name']}({s}) {y}년" for s, y in short.items()))

    print("③ 정형 DB 저장")
    conn = connect()
    save_obs(conn, rows)
    save_baselines(conn, baselines)
    obs_count = conn.execute("SELECT COUNT(*) FROM obs_daily").fetchone()[0]
    base_count = conn.execute("SELECT COUNT(*) FROM baseline").fetchone()[0]
    assert obs_count == len(rows) and base_count == len(baselines) * 366, (obs_count, base_count)

    print("④ VectorDB 저장 (station_meta)")
    rows_by_stn = defaultdict(list)
    for r in rows:
        rows_by_stn[r["stn"]].append(r)
    ids, texts, metas = [], [], []
    for stn, daily in baselines.items():
        info = stations[stn]
        ids.append(stn)
        texts.append(station_text(stn, info, monthly_summary(daily), period, climate_traits(rows_by_stn[stn], info)))
        metas.append({"stn": stn, "name": info["name"], "sido": info["sido"], "address": info["address"],
                      "lat": info["lat"], "lon": info["lon"], "height": info["height"], "mountain": info["mountain"],
                      "fct_id": info["fct_id"], "office": office_for(info["fct_id"]), "period": period,
                      "source_type": "station_meta", "title": f"{info['name']}({stn}) 지점 정보 · 최근 10년 기준값",
                      "url": ASOS_SOURCE_URL})
    meta_store = get_store("station_meta")
    added = upsert_changed(meta_store, ids, texts, metas)
    meta_count = len(meta_store.get(include=[])["ids"])
    assert meta_count == len(ids), (meta_count, len(ids))  # 로드한 지점 수 = 색인 건수 (명세 4.1)

    print(f"\n완료 — obs_daily {obs_count:,}행, baseline {base_count:,}행, station_meta {meta_count}건(이번에 추가·갱신 {added})")
    print("관할 지방청별 지점 수: " + ", ".join(
        f"{OFFICES[o]} {n}" for o, n in Counter(m["office"] for m in metas).most_common()))
    print("\n예시 — 서울 10/22 기준값:", {k: v for k, v in get_baseline(conn, "108", "1022").items() if k != "stn"})
    print("예시 — 서울 2024-10-22 관측:", get_obs(conn, "108", ["20241022"]))


if __name__ == "__main__":
    main()
