"""유사 사례: 오늘 개황과 오늘 문단이 비슷했던 과거 날짜 + 그날 선택한 지점의 관측. (ADR 0001)"""
from dataclasses import dataclass

from domain.prompts import ask_json, parse_selected, select_messages
from domain.stations import anomaly_sentence
from domain.weather_db import get_baseline, get_obs
from rag.cache import get_selection, put_selection


@dataclass
class Case:
    doc_id: str
    date: str
    title: str
    url: str
    forecast: str   # 그날 개황의 오늘 문단
    obs: dict       # 그날 선택한 지점의 관측
    sentence: str   # 근거로 넘길 문장: 개황 + 기준값과 비교한 관측


def case_candidates(store, conn_db, stn: str, office: str, summary: str, n: int,
                    exclude_dates: frozenset[str] = frozenset()) -> list[Case]:
    """같은 관할 지방청 개황 가운데 유사도 순으로, 선택 지점의 관측이 있는 날만 n건까지 채운다."""
    cases = []
    for doc in store.similarity_search(summary, k=n * 3, filter={"office": office}):
        day = doc.metadata["date"]
        if day in exclude_dates:
            continue
        obs = get_obs(conn_db, stn, [day])
        base = get_baseline(conn_db, stn, day[4:8])
        if not obs or not base:
            continue  # 지점 개설 전이거나 결측인 날은 다음 순위로 채운다
        y, m, d = day[:4], day[4:6], day[6:8]
        sentence = f"{y}-{m}-{d} 개황: {doc.page_content} → 그날 실제 관측: {anomaly_sentence(obs[0], base)}"
        cases.append(Case(doc.id, day, doc.metadata["title"], doc.metadata["url"], doc.page_content, obs[0], sentence))
        if len(cases) == n:
            break
    return cases


def select_cases(llm, cache_conn, stn: str, tmfc: str, summary: str, candidates: list[Case], max_n: int) -> list[Case]:
    """프롬프트2로 오늘 개황과 현상·시간대가 맞는 사례만 고른다. 같은 지점·같은 개황은 캐시를 쓴다."""
    cached = get_selection(cache_conn, stn, tmfc)
    if cached is not None:
        by_id = {c.doc_id: c for c in candidates}
        return [by_id[i] for i in cached if i in by_id]
    if not candidates:
        return []
    items = [(i, c.title, c.sentence) for i, c in enumerate(candidates, 1)]
    picked = ask_json(llm, select_messages("cases", items, summary),
                      lambda text: parse_selected(text, set(range(1, len(candidates) + 1))))
    if picked is None:
        return []  # 파싱 실패는 캐시하지 않는다. 다음 질문에서 다시 시도한다
    chosen = [candidates[i - 1] for i in picked[:max_n]]
    put_selection(cache_conn, stn, tmfc, [c.doc_id for c in chosen])
    return chosen
