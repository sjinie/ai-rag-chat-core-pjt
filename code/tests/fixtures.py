"""그래프·서비스 테스트가 함께 쓰는 Deps. 가짜 임베딩 Chroma + 메모리 SQLite, 네트워크 없음."""
from datetime import datetime

from langchain_core.embeddings import DeterministicFakeEmbedding

from domain.weather_db import connect, save_baselines, save_obs
from rag.cache import connect_cache
from rag.graph import Deps
from rag.store import get_store

NOW = datetime(2026, 10, 23, 15, 0)
TODAY = {"office": "109", "tmfc": "202610231100", "summary": "□ (종합) 오늘 맑음 ○ (오늘) 맑음",
         "body": "□ (종합) 오늘 맑음\n○ (오늘) 맑음\n○ (내일) 오후부터 비"}
OBS = {"ta_avg": 15.0, "ta_max": 21.0, "ta_min": 9.0, "hm_avg": 55.0, "ws_avg": 2.0, "rn_day": 0.0}
BASE = {"ta_avg": 14.0, "ta_max": 19.0, "ta_min": 9.0, "hm_avg": 63.0, "ws_avg": 2.0, "rn_day": 1.0,
        "ta_avg_sd": 2.0, "ta_max_sd": 2.0, "ta_min_sd": 2.0, "hm_avg_sd": 10.0, "ws_avg_sd": 0.5, "rn_day_sd": 3.0,
        "n": 150, "years": 10}
NO_PLAN = '{"need_cases": false, "queries": {}}'
STATIONS = {"108": {"name": "서울", "fct_id": "11B10101", "address": "서울특별시 종로구 송월동", "sido": "서울특별시"},
            "105": {"name": "강릉", "fct_id": "11D20501", "address": "강원특별자치도 강릉시 용강동", "sido": "강원특별자치도"},
            "172": {"name": "고창", "fct_id": "21F10601", "address": "전북특별자치도 고창군 대산면 매산리", "sido": "전북특별자치도"},
            "251": {"name": "고창군", "fct_id": "21F10601", "address": "전북특별자치도 고창군 고창읍 덕산리",
                    "sido": "전북특별자치도"}}


def make_deps(tmpdir: str, llm) -> Deps:
    emb = DeterministicFakeEmbedding(size=64)
    stores = {name: get_store(name, emb, tmpdir)
              for name in ("station_meta", "forecast_texts", "climate_docs", "live_forecasts")}
    stores["station_meta"].add_texts(
        [f"{s['name']}({stn}) 관측소 · {s['address']}" for stn, s in STATIONS.items()], ids=list(STATIONS),
        metadatas=[{"title": f"{s['name']}({stn}) 지점 정보 · 최근 10년 기준값", "url": "u", "name": s["name"]}
                   for stn, s in STATIONS.items()])
    stores["forecast_texts"].add_texts(
        ["□ (종합) 오늘 맑음 ○ (오늘) 맑음", "□ (종합) 오늘 비"], ids=["fcst:109:20241023", "fcst:109:20231023"],
        metadatas=[{"office": "109", "date": "20241023", "title": "수도권 개황 2024", "url": "u"},
                   {"office": "109", "date": "20231023", "title": "수도권 개황 2023", "url": "u"}])
    db = connect(":memory:")
    save_obs(db, [{"stn": "108", "date": d, **OBS} for d in ("20241023", "20231023")])
    save_baselines(db, {"108": {(10, 23): BASE}})
    return Deps(llm=llm, station_meta=stores["station_meta"], forecast_texts=stores["forecast_texts"],
                climate_docs=stores["climate_docs"], live_forecasts=stores["live_forecasts"], db=db,
                cache=connect_cache(":memory:"), stations=STATIONS, on_step=lambda s: None)
