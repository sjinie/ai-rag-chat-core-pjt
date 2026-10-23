"""화면이 부르는 유일한 진입점. Streamlit과 나중의 FastAPI가 같은 함수를 쓴다.

    svc = service.create()           # 실제 LLM·스토어·DB 연결 (Streamlit은 @st.cache_resource로 한 번만)
    svc.ask("108", "오늘 서울 어때?", history)
"""
import os
import re
from dataclasses import dataclass, replace
from datetime import datetime

import chromadb
from langchain_openai import ChatOpenAI

from config import CONFIG, ROOT, require_env
from domain.kma import fetch_stations, fetch_today_obs
from domain.prompts import PLAIN_SYSTEM, ask_json, parse_selected, select_messages
from domain.stations import LABELS, VARIABLES, classify, match_stations
from domain.weather_db import DB_PATH, connect, get_baseline
from rag.cache import connect_cache
from rag.evidence import Evidence, cited
from rag.graph import Deps, build_graph
from rag.store import get_store

REPORT_QUESTION = "오늘 날씨를 최근 10년 기준값과 과거 유사 사례에 비추어 설명해줘"
CITATION = re.compile(r"\s*\[근거[^\]]*\]")
EXPLORE_K = 15
READY_CHECKS = [("station_meta", "지점 색인", "build_climate.py"), ("forecast_texts", "예보 개황 색인", "build_forecast.py"),
                ("climate_docs", "용어집 색인", "build_glossary.py")]


def now() -> datetime:
    return datetime.now()


@dataclass
class Answer:
    text: str
    cited: list[tuple[int, Evidence]]   # 답변이 실제로 인용한 근거만 (F2008)
    steps: list[str]
    has_cases: bool                     # 유사 사례가 문맥에 들어갔으면 "예보가 아님" 안내를 붙인다


def collection_counts() -> dict[str, int]:
    """컬렉션별 건수. 키 없이도 볼 수 있게 임베딩 없이 Chroma를 직접 연다."""
    try:
        client = chromadb.PersistentClient(path=str(ROOT / CONFIG["chroma"]["persist_dir"]))
        return {c.name: c.count() for c in client.list_collections()}
    except Exception:
        return {}


def check_ready() -> list[str]:
    """실행 전에 막히는 문제와 해결 방법. 키 값은 넣지 않는다. (F2012, NF2004)"""
    # WIKI_CONTACT는 외부 출처 User-Agent의 연락처 (NF2006). 없으면 위키백과가 분당 10회로 제한한다
    problems = [f"{key}가 설정되지 않았습니다. 프로젝트 루트의 .env에 {key}를 넣어 주세요."
                for key in ("GMS_KEY", "KMA_API_KEY", "WIKI_CONTACT") if not os.environ.get(key, "").strip()]
    if not DB_PATH.exists():
        problems.append("정형 날씨 DB가 없습니다. code 폴더에서 python build_climate.py를 실행해 주세요.")
    counts = collection_counts()
    problems += [f"{label}이 비어 있습니다. code 폴더에서 python {script}를 실행해 주세요."
                 for name, label, script in READY_CHECKS if not counts.get(name)]
    return problems


class Service:
    def __init__(self, deps: Deps):
        self.deps = deps

    def ask(self, stn: str, question: str, history: list[dict], on_step=lambda s: None,
            force_cases: bool = False) -> Answer:
        """RAG 채팅: retrieve → generate."""
        graph = build_graph(replace(self.deps, on_step=on_step))
        # 이전 답의 [근거 N]은 그때의 번호라, 남겨 두면 이번 답이 옛 번호를 베껴 다른 문서를 가리킬 수 있다
        history = [{**m, "content": CITATION.sub("", m["content"])} for m in history]
        out = graph.invoke({"stn": stn, "question": question, "history": history, "now": now(),
                            "force_cases": force_cases, "evidence": [], "steps": [], "answer": ""})
        return Answer(out["answer"], cited(out["answer"], out["evidence"]), out["steps"],
                      any(e.kind == "유사 사례" for e in out["evidence"]))

    def plain_chat(self, history: list[dict]) -> str:
        """단순 채팅: 전문가 역할과 대화 기록만. 근거·지점·날짜 정보 없음 (F2015 비교용)."""
        return self.deps.llm.invoke([{"role": "system", "content": PLAIN_SYSTEM}, *history]).content

    def today_report(self, stn: str, on_step=lambda s: None) -> tuple[list[dict], Answer]:
        """오늘 날씨 리포트(F2010): 기준값 비교표 + 유사 사례를 꼭 넣은 해설."""
        today = now()
        try:
            obs = fetch_today_obs(stn, today.date()) or {}
        except RuntimeError:
            obs = {}
        base = get_baseline(self.deps.db, stn, today.strftime("%m%d")) or {}
        rows = []
        for v in VARIABLES:
            value, mean = obs.get(v), base.get(v)
            rows.append({"항목": LABELS[v][0], "오늘 관측(지금까지)": value, "최근 10년 기준값": mean,
                         "차이": round(value - mean, 1) if value is not None and mean is not None else None,
                         "판정": classify(value, mean, base.get(f"{v}_sd"))})
        return rows, self.ask(stn, REPORT_QUESTION, [], on_step, force_cases=True)

    def explore(self, condition: str) -> list[str]:
        """조건 기반 지점 탐색(F2011): 지점 프로필 유사도 상위 15개 → 프롬프트2가 조건에 맞는 지점만 고른다."""
        docs = self.deps.station_meta.similarity_search(condition, k=EXPLORE_K)
        items = [(i, d.metadata.get("name", d.id), " ".join(d.page_content.splitlines()[:2]))
                 for i, d in enumerate(docs, 1)]
        picked = ask_json(self.deps.llm, select_messages("stations", items, condition),
                          lambda text: parse_selected(text, set(range(1, len(docs) + 1))))
        return [docs[i - 1].id for i in picked or []]

    def resolve_location(self, text: str) -> list[str]:
        return match_stations(text, self.deps.stations)


def create() -> Service:
    """실제 LLM(GMS)·Chroma·SQLite·지점 정보로 Service를 만든다."""
    llm = ChatOpenAI(model=CONFIG["llm"]["chat_model"], api_key=require_env("GMS_KEY"),
                     base_url=CONFIG["llm"]["base_url"])
    return Service(Deps(llm=llm, station_meta=get_store("station_meta"), forecast_texts=get_store("forecast_texts"),
                        climate_docs=get_store("climate_docs"), live_forecasts=get_store("live_forecasts"),
                        db=connect(), cache=connect_cache(), stations=fetch_stations(), on_step=lambda s: None))
