"""최근 10년 기후 기준값을 수집해 VectorDB에 저장한다.

    cd code
    python build_climate.py

1. API허브에서 연도별 전국 ASOS 일자료를 받는다 (data/raw에 캐시, 다시 실행하면 API를 부르지 않는다)
2. 지점별·날짜별 '최근 10년 ±N일 평균'을 계산한다 (6개 항목)
3. station_meta  : 지점 1건 = 시/도 + 월별 평균 텍스트 1개 (ID = 지점번호)
   weather_data  : 지점 × 366일 기준값 (ID = base:지점번호:MMDD)
"""
from collections import Counter

from config import CONFIG
from domain.kma import fetch_daily_year, parse_daily
from domain.stations import (STATIONS, VARIABLES, baseline_text, compute_baselines,
                             monthly_summary, station_text)
from rag.store import get_store, upsert_missing


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

    # 마지막 해에 자료가 없는 지점은 폐쇄된 것이므로 뺀다 (예: 175 진도 2019년 8월 종료) — 오늘 날씨와 비교할 수 없다
    active = {r["stn"] for r in rows if r["date"].startswith(str(end))}
    closed = sorted({r["stn"] for r in rows} - active, key=int)
    if closed:
        print(f"  {end}년 자료가 없어 제외한 지점번호: {closed}")
    rows = [r for r in rows if r["stn"] in active]

    unknown = sorted(active - set(STATIONS), key=int)
    if unknown:
        raise SystemExit(f"STATIONS에 없는 지점번호: {unknown} — domain/stations.py에 추가하세요.")

    print(f"② 최근 10년 ±{window}일 평균 계산")
    baselines = compute_baselines(rows, window)
    short = {stn: b[(1, 1)]["years"] for stn, b in baselines.items() if b[(1, 1)]["years"] < end - start + 1}
    if short:
        print(f"  10년이 안 되는 지점(연도 수): " + ", ".join(f"{STATIONS[s][0]}({s}) {y}년" for s, y in short.items()))

    print("③ VectorDB 저장")
    meta_ids, meta_texts, meta_metas = [], [], []
    base_ids, base_texts, base_metas = [], [], []
    for stn, daily in baselines.items():
        name, sido = STATIONS[stn]
        meta_ids.append(stn)
        meta_texts.append(station_text(stn, monthly_summary(daily), period))
        meta_metas.append({"stn": stn, "name": name, "sido": sido, "period": period})
        for (m, d), entry in daily.items():
            base_ids.append(f"base:{stn}:{m:02d}{d:02d}")
            base_texts.append(baseline_text(stn, m, d, entry, period, window))
            # 숫자는 메타데이터에도 넣어 코드가 텍스트를 파싱하지 않고 바로 쓰게 한다 (Chroma는 None 불가 → 생략)
            values = {v: entry[v] for v in VARIABLES if entry[v] is not None}
            base_metas.append({"kind": "baseline", "stn": stn, "name": name, "sido": sido, "mmdd": f"{m:02d}{d:02d}",
                               "period": period, "window": window, "n": entry["n"], "years": entry["years"], **values})

    meta_store, base_store = get_store("station_meta"), get_store("weather_data")
    added_meta = upsert_missing(meta_store, meta_ids, meta_texts, meta_metas)
    added_base = upsert_missing(base_store, base_ids, base_texts, base_metas)

    # 검증: 로드한 지점 수 = 색인 건수, 다시 실행해도 늘지 않는다 (명세 4.1)
    meta_count = len(meta_store.get(include=[])["ids"])
    base_count = len(base_store.get(include=[], where={"kind": "baseline"})["ids"])
    assert meta_count == len(meta_ids), (meta_count, len(meta_ids))
    assert base_count == len(base_ids), (base_count, len(base_ids))

    print(f"\n완료 — station_meta {meta_count}건(이번에 추가 {added_meta}), "
          f"weather_data 기준값 {base_count:,}건(이번에 추가 {added_base:,})")
    print("시/도별 지점 수: " + ", ".join(f"{s} {n}" for s, n in Counter(STATIONS[s][1] for s in baselines).most_common()))
    print("\n예시 —", base_store.get(ids=["base:108:1022"])["documents"][0])


if __name__ == "__main__":
    main()
