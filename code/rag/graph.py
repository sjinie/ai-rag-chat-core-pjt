"""LangGraph RAG 파이프라인: retrieve → generate 두 노드. (F2007)

retrieve: 지점 정보·오늘 개황은 항상, 유사 사례·외부 문서는 프롬프트1이 필요하다고 할 때만 모은다.
generate: 프롬프트3으로 근거만 써서 답한다.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from config import CONFIG
from domain.cases import case_candidates, select_cases
from domain.kma import fetch_latest_forecast, fetch_today_obs, live_forecast_doc
from domain.prompts import SOURCES, Plan, answer_messages, ask_json, parse_plan, plan_messages
from domain.stations import OFFICES, anomaly_sentence, office_for
from domain.weather_db import get_baseline
from rag.collect import collect, search_docs, select_stations
from rag.evidence import SOURCE_KIND, Evidence, evidence_block, merge
from rag.store import upsert_changed


@dataclass
class Deps:
    llm: object
    station_meta: object
    forecast_texts: object
    climate_docs: object
    live_forecasts: object
    db: object
    cache: object
    stations: dict
    on_step: Callable[[str], None]


class GraphState(TypedDict):
    stn: str
    question: str
    history: list[dict]
    now: datetime
    force_cases: bool   # "오늘 날씨 리포트"는 질문과 상관없이 유사 사례를 넣는다 (F2010)
    place_resolved: bool  # 지점 후보를 이미 골랐으면 다시 묻지 않는다
    candidates: list[str]  # 지역을 특징으로만 말한 질문이면 답 대신 지점 후보를 돌려준다
    evidence: list[Evidence]
    steps: list[str]
    answer: str


def build_graph(deps: Deps):
    def retrieve(state: GraphState) -> dict:
        steps = []

        def step(message: str) -> None:
            steps.append(message)
            deps.on_step(message)

        stn, now = state["stn"], state["now"]
        info = deps.stations[stn]
        office = office_for(info["fct_id"])

        # (1) 지점 정보: 지점 프로필 + 오늘 관측을 최근 10년 기준값과 비교한 문장
        meta = deps.station_meta.get(ids=[stn], include=["documents", "metadatas"])
        base = get_baseline(deps.db, stn, now.strftime("%m%d")) or {}
        try:  # 기상청 API가 늦거나 실패해도 DB에 있는 근거로 답한다
            obs = fetch_today_obs(stn, now.date()) or {}
        except RuntimeError:
            obs = {}
            step("오늘 관측을 받지 못했습니다")
        station = [Evidence("지점 정보", f"station:{stn}", meta["metadatas"][0]["title"], meta["metadatas"][0]["url"],
                            f"{meta['documents'][0]}\n오늘({now:%Y-%m-%d}, 지금까지) 관측: {anomaly_sentence(obs, base)}")]

        # (2) 오늘 개황: 항목 자체 문서. 항상 넣고 live_forecasts에 색인한다 (F2003·F2004)
        try:
            forecast = fetch_latest_forecast(office, now)
        except RuntimeError:
            forecast = None
        today = []
        if forecast:
            doc_id, text, live_meta = live_forecast_doc(forecast, OFFICES[office])
            upsert_changed(deps.live_forecasts, [doc_id], [text], [live_meta])
            today = [Evidence("오늘 개황", doc_id, live_meta["title"], live_meta["url"], forecast["body"])]
            step(f"{live_meta['title']} 확인")
        else:
            step("오늘 개황을 받지 못했습니다")

        # (3) 프롬프트1: 어떤 근거를 더 찾을지
        plan = ask_json(deps.llm, plan_messages(f"{info['name']}({stn})", f"{now:%Y-%m-%d %H시}",
                                                forecast["summary"] if forecast else "없음",
                                                state["question"], state["history"]), parse_plan)
        if plan is None:
            step("질문 분석에 실패해 지점 정보와 오늘 개황만으로 답합니다")
            plan = Plan(False, {s: [] for s in SOURCES})
        # 지명 없이 "산이 많은 곳"처럼 말했으면 답하기 전에 어느 지점인지 고르게 한다 (사이드바 조건 탐색과 같은 방법)
        if plan.place and not state.get("place_resolved"):
            found = select_stations(deps.llm, deps.station_meta, plan.place)
            if found and found != [stn]:
                step(f"'{plan.place}'에 맞는 지점 {len(found)}곳을 찾았습니다")
                return {"evidence": merge(station, today), "steps": state["steps"] + steps, "candidates": found}
        need_cases = plan.need_cases or state.get("force_cases", False)

        # (4) 유사 사례: 같은 관할 지방청 개황 유사도 → 관측 → 프롬프트2 선별 (ADR 0001)
        cases = []
        if need_cases and forecast:
            step("오늘 개황과 비슷했던 과거 예보를 찾는 중")
            rag = CONFIG["rag"]
            candidates = case_candidates(deps.forecast_texts, deps.db, stn, office, forecast["summary"],
                                         rag["case_candidates"])
            chosen = select_cases(deps.llm, deps.cache, stn, forecast["tmfc"], forecast["summary"],
                                  candidates, rag["case_max"])
            cases = [Evidence("유사 사례", c.doc_id, c.title, c.url, c.sentence) for c in chosen]
            step(f"유사 사례 {len(cases)}건 선택 (후보 {len(candidates)}건)")

        # (5) 외부 문서: 질문 시 수집 + 미리 색인된 용어집 검색
        external = []
        if any(plan.queries.values()):
            step("외부 문서를 찾는 중")
            new_titles = collect(deps.llm, deps.climate_docs, deps.cache, stn, state["question"], plan, step)
            if new_titles:
                step("새로 수집한 문서: " + ", ".join(new_titles))
            external = [Evidence(SOURCE_KIND[d.metadata["source_type"]], d.id, d.metadata["title"],
                                 d.metadata["url"], d.page_content) for d in search_docs(deps.climate_docs, stn, plan)]
            if not external:
                step("외부 문서에서 관련 내용을 찾지 못했습니다")

        return {"evidence": merge(station, today, cases, external), "steps": state["steps"] + steps, "candidates": []}

    def generate(state: GraphState) -> dict:
        if state.get("candidates"):
            return {"answer": ""}  # 지점을 고른 뒤 다시 묻는다
        reply = deps.llm.invoke(answer_messages(state["question"], evidence_block(state["evidence"]), state["history"]))
        return {"answer": reply.content}

    graph = StateGraph(GraphState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
