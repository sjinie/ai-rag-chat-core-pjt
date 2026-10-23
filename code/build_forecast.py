"""지방청별 단기예보 개황의 '종합·오늘' 문단을 VectorDB에 저장한다.

    cd code
    python build_forecast.py

오늘 개황과 문장이 비슷했던 과거 날짜를 찾고, 그 날짜의 실제 관측은 weather.db에서 조회하는 데 쓴다.
Chroma forecast_texts : ID = fcst:지방청:YYYYMMDD, 메타데이터에 날짜·연중 일자(doy)·원문 전체
"""
from collections import Counter
from datetime import date

from config import CONFIG
from domain.kma import FORECAST_SOURCE_URL, fetch_forecast_year, parse_forecasts, today_summary
from domain.stations import OFFICES, day_index
from rag.store import get_store, upsert_changed


def main() -> None:
    start, end, hour = (CONFIG["forecast"][k] for k in ("start_year", "end_year", "issue_hour"))
    ids, texts, metas = [], [], []
    for office, office_name in OFFICES.items():
        for year in range(start, end + 1):
            raw, collected = fetch_forecast_year(office, year)
            for doc in parse_forecasts(raw):
                if doc["tmfc"][8:10] != hour:
                    continue
                day = doc["tmfc"][:8]
                summary = today_summary(doc["body"])
                if not summary:
                    continue
                doc_id = f"fcst:{office}:{day}"
                ids.append(doc_id)
                texts.append(summary)
                metas.append({"source_type": "kma_forecast", "doc_id": doc_id, "office": office, "date": day,
                              "doy": day_index(int(day[4:6]), int(day[6:8])),
                              "title": f"{office_name} 단기예보 개황 · {day[:4]}-{day[4:6]}-{day[6:]} {hour}시",
                              "url": FORECAST_SOURCE_URL, "collected_at": collected, "body": doc["body"]})
        print(f"  {office_name}: {sum(1 for m in metas if m['office'] == office):,}일")

    expected = (date(end, 12, 31) - date(start, 1, 1)).days + 1
    missing = {OFFICES[o]: expected - n for o, n in Counter(m["office"] for m in metas).items() if n < expected}
    if missing:
        print(f"  {hour}시 발표분이 없는 날 수: {missing}")
    assert len(ids) == len(set(ids)), "같은 지방청·날짜가 두 번 나왔다"

    store = get_store("forecast_texts")
    added = upsert_changed(store, ids, texts, metas)
    count = len(store.get(include=[])["ids"])
    assert count == len(ids), (count, len(ids))
    print(f"\n완료 — forecast_texts {count:,}건(이번에 추가·갱신 {added:,})")
    print("예시 —", store.get(ids=[f"fcst:156:{end}1022"])["documents"])


if __name__ == "__main__":
    main()
